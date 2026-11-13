"""
The calls the bot makes to the endpoint of a tool: only to public https addresses, with limits on
time and size, never carrying the keys anywhere else, and always recorded. The network is replaced
by a fake one, so no test reaches the internet.
"""

import contextlib
import io
import itertools
import socket
from contextlib import contextmanager
from datetime import timedelta
from unittest import mock
from urllib.parse import urlsplit

import pytest
import requests
from django.utils import timezone
from requests.structures import CaseInsensitiveDict
from wanps.messaging.models import Account, App

from apps.channels.models import ToolCall
from apps.channels.safe_http import ToolCallError, safe_get
from apps.channels.tasks import delete_old_tool_calls

PUBLIC = "93.184.216.34"
URL = "https://example.com/data"


@pytest.fixture
def account(db):
    app = App.objects.create(name="Social Bot", app_secret="s", verify_token="v")
    return Account.objects.create(
        app=app, channel="whatsapp", name="Front desk", external_id="111", access_token="t"
    )


@pytest.fixture(autouse=True)
def small_limits(settings):
    settings.TOOL_CALL_TIMEOUT = 5
    settings.TOOL_CALL_MAX_BYTES = 1000


def resolving(mapping):
    """The names that exist, and the addresses each one resolves to."""

    def fake(host, port, *args, **kwargs):
        if host not in mapping:
            raise socket.gaierror("unknown name")
        return [
            (
                socket.AF_INET6 if ":" in ip else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (ip, port),
            )
            for ip in mapping[host]
        ]

    return mock.patch("apps.channels.safe_http.socket.getaddrinfo", side_effect=fake)


def answer(status=200, body=b"", headers=None, raw=None):
    response = requests.Response()
    response.status_code = status
    response.headers = CaseInsensitiveDict(headers or {})
    response.raw = raw if raw is not None else io.BytesIO(body)
    response.encoding = "utf-8"
    return response


def redirect(to, status=302):
    return answer(status, headers={"Location": to})


class Wire:
    """Stands for the network: gives each request the next answer and remembers what was asked."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, request, **kwargs):
        self.requests.append(request)
        given = self.answers.pop(0)
        if isinstance(given, Exception):
            raise given
        # requests reads both when it meets a redirect, and a real adapter sets them
        given.url, given.request = request.url, request
        return given


@contextmanager
def network(*answers, names=None):
    wire = Wire(answers)
    with (
        resolving({"example.com": [PUBLIC], **(names or {})}),
        mock.patch("apps.channels.safe_http.PinnedAdapter.send", new=wire),
    ):
        yield wire


def get(account, url=URL, **kwargs):
    return safe_get(url, account=account, tool="lookup", **kwargs)


def fails_with(account, reason, url=URL, **kwargs):
    with pytest.raises(ToolCallError) as caught:
        get(account, url, **kwargs)
    assert caught.value.reason == reason
    return caught.value


@pytest.mark.parametrize(
    "url",
    ["http://example.com/x", "ftp://example.com/x", "file:///etc/passwd", "gopher://example.com"],
)
def test_only_https_is_accepted(account, url):
    with network() as net:
        fails_with(account, "blocked", url)

    assert net.requests == []


@pytest.mark.parametrize(
    ("url", "names"),
    [
        ("https://localhost/x", {"localhost": ["127.0.0.1"]}),
        ("https://127.0.0.1/x", {"127.0.0.1": ["127.0.0.1"]}),
        ("https://10.0.0.5/x", {"10.0.0.5": ["10.0.0.5"]}),
        ("https://172.16.0.9/x", {"172.16.0.9": ["172.16.0.9"]}),
        ("https://172.31.255.1/x", {"172.31.255.1": ["172.31.255.1"]}),
        ("https://192.168.1.10/x", {"192.168.1.10": ["192.168.1.10"]}),
        ("https://169.254.169.254/latest", {"169.254.169.254": ["169.254.169.254"]}),
        ("https://100.64.0.1/x", {"100.64.0.1": ["100.64.0.1"]}),
        ("https://0.0.0.0/x", {"0.0.0.0": ["0.0.0.0"]}),
        ("https://[::1]/x", {"::1": ["::1"]}),
        ("https://[fc00::1]/x", {"fc00::1": ["fc00::1"]}),
        ("https://[::ffff:127.0.0.1]/x", {"::ffff:127.0.0.1": ["::ffff:127.0.0.1"]}),
        ("https://2130706433/x", {"2130706433": ["127.0.0.1"]}),
    ],
)
def test_addresses_that_are_not_public_are_blocked(account, url, names):
    with network(names=names) as net:
        fails_with(account, "blocked", url)

    assert net.requests == []


@pytest.mark.parametrize(
    ("url", "names"),
    [
        ("https://db/x", {"db": ["172.19.0.2"]}),
        ("https://redis:6379/x", {"redis": ["172.19.0.3"]}),
    ],
)
def test_a_service_of_the_docker_network_is_blocked(account, url, names):
    with network(names=names) as net:
        fails_with(account, "blocked", url)

    assert net.requests == []


def test_a_name_with_public_and_private_addresses_is_blocked(account):
    with network(names={"mixed.example": [PUBLIC, "10.0.0.1"]}) as net:
        fails_with(account, "blocked", "https://mixed.example/x")

    assert net.requests == []


@pytest.mark.parametrize("target", ["https://internal.example/x", "http://example.com/x"])
def test_a_redirect_to_a_non_public_address_or_to_http_is_blocked(account, target):
    with network(redirect(target), names={"internal.example": ["10.0.0.7"]}) as net:
        fails_with(account, "blocked")

    assert len(net.requests) == 1


def test_at_most_three_redirects_are_followed(account):
    hops = [redirect(f"https://example.com/{n}") for n in range(5)]

    with network(*hops) as net:
        fails_with(account, "redirects")

    assert len(net.requests) == 4


def test_a_redirect_that_ends_well_gives_the_final_answer(account):
    with network(redirect("https://example.com/final"), answer(body=b"final")) as net:
        text = get(account)

    assert text == "final"
    assert len(net.requests) == 2


def test_an_endpoint_that_does_not_answer_in_time_is_cut_with_a_clear_error(account):
    with network(requests.Timeout("slow")):
        error = fails_with(account, "timeout")

    assert "too long" in str(error)


def test_an_endpoint_that_drips_its_answer_is_cut_at_the_total_time_limit(account, settings):
    settings.TOOL_CALL_MAX_BYTES = 10**9  # only the clock can stop it
    drip = io.BytesIO(b"x" * 40000)
    clock = itertools.count(0, 3)  # each look at the clock is 3 seconds later

    with (
        network(answer(raw=drip)),
        mock.patch("apps.channels.safe_http.time.monotonic", side_effect=lambda: next(clock)),
    ):
        fails_with(account, "timeout")


def test_an_answer_over_the_limit_is_cut_with_a_clear_error(account, settings):
    with network(answer(body=b"x" * 5000)):
        error = fails_with(account, "too_large")

    assert "too large" in str(error)


def test_an_endless_answer_is_never_read_whole(account):
    class Endless:
        read_bytes = 0

        def read(self, amount=-1, *args, **kwargs):
            amount = 8192 if amount is None or amount < 0 else amount
            Endless.read_bytes += amount
            return b"x" * amount

        def close(self):
            pass

    with network(answer(raw=Endless())):
        fails_with(account, "too_large")

    assert Endless.read_bytes <= 1000 + 2 * 8192


def test_an_answer_that_announces_a_size_over_the_limit_is_refused_without_reading_it(account):
    class Unreadable:
        def read(self, *args, **kwargs):
            raise AssertionError("the body must not be read")

        def close(self):
            pass

    with network(answer(headers={"Content-Length": "999999"}, raw=Unreadable())):
        fails_with(account, "too_large")


def test_a_normal_answer_is_returned_and_the_checked_address_is_the_one_used(account):
    with network(answer(body='{"open": true, "name": "Clínica"}'.encode())) as net:
        text = get(account, params={"q": "today"})

    assert text == '{"open": true, "name": "Clínica"}'
    (sent,) = net.requests
    parts = urlsplit(sent.url)
    assert (parts.hostname, parts.path) == (PUBLIC, "/data")
    assert "q=today" in parts.query
    assert sent.headers["Host"] == "example.com"


def test_an_answer_that_is_not_2xx_gives_only_its_status_not_its_body(account):
    with network(answer(500, body=b"Traceback: internal secret detail")):
        error = fails_with(account, "http_error")

    assert "500" in str(error)
    assert "secret detail" not in str(error)


def test_the_keys_of_a_tool_never_reach_an_error_a_log_or_the_record(account, caplog):
    headers = {"Authorization": "Bearer SECRET-KEY"}
    failures = [
        answer(401, body=b"bad key SECRET-KEY"),
        requests.ConnectionError("https://example.com/?key=SECRET-KEY unreachable"),
    ]
    caplog.set_level("DEBUG")

    for failure in failures:
        with network(failure):
            error = fails_with(account, error_reason(failure), headers=headers)
        assert "SECRET-KEY" not in str(error)

    assert "SECRET-KEY" not in caplog.text
    for call in ToolCall.objects.values():
        assert "SECRET-KEY" not in str(call)


def error_reason(failure):
    return "http_error" if isinstance(failure, requests.Response) else "unreachable"


def test_the_keys_travel_on_the_same_host_but_not_to_another_one(account):
    headers = {"Authorization": "Bearer SECRET-KEY"}
    names = {"other.example": ["8.8.8.8"]}

    with network(redirect("https://example.com/again"), answer(body=b"ok"), names=names) as same:
        get(account, headers=headers)
    with network(redirect("https://other.example/x"), answer(body=b"ok"), names=names) as other:
        get(account, headers=headers)

    assert same.requests[1].headers.get("Authorization") == "Bearer SECRET-KEY"
    assert "Authorization" not in other.requests[1].headers


@pytest.mark.parametrize(
    ("given", "reason", "http_status"),
    [
        (answer(body=b"fine"), "ok", 200),
        (answer(503, body=b"down"), "http_error", 503),
        (requests.Timeout("slow"), "timeout", None),
        (requests.ConnectionError("down"), "unreachable", None),
    ],
)
def test_every_call_is_recorded_with_account_tool_status_and_duration(
    account, given, reason, http_status
):
    with network(given), contextlib.suppress(ToolCallError):
        get(account, "https://example.com/private/path?key=SECRET")

    (call,) = ToolCall.objects.all()
    assert (call.account, call.tool, call.status, call.http_status) == (
        account,
        "lookup",
        reason,
        http_status,
    )
    assert call.host == "example.com"
    assert call.duration_ms >= 0
    # Neither the path, nor the query, nor the answer are kept
    assert "SECRET" not in str(call.__dict__) and "private" not in str(call.__dict__)


def test_a_blocked_call_is_recorded_too(account):
    with network(names={"localhost": ["127.0.0.1"]}):
        fails_with(account, "blocked", "https://localhost/x")

    (call,) = ToolCall.objects.all()
    assert (call.status, call.host) == ("blocked", "localhost")


def test_the_daily_job_deletes_the_records_older_than_the_retention_time(account, settings):
    settings.TOOL_CALL_RETENTION_DAYS = 30
    old = ToolCall.objects.create(
        account=account, tool="lookup", host="example.com", status="ok", duration_ms=5
    )
    recent = ToolCall.objects.create(
        account=account, tool="lookup", host="example.com", status="ok", duration_ms=5
    )
    ToolCall.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))

    deleted = delete_old_tool_calls()

    assert deleted == 1
    assert list(ToolCall.objects.all()) == [recent]


def test_a_header_value_the_http_library_cannot_encode_is_a_safe_error_not_a_crash(account):
    bad_header = UnicodeEncodeError("latin-1", chr(8217), 0, 1, "ordinal not in range")

    with network(bad_header):
        fails_with(account, "unreachable", headers={"Authorization": "Bearer key"})
