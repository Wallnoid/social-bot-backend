"""
The calls the bot makes to the endpoint of a tool.

The address of a tool is typed by a business, so it cannot be trusted: a call could reach the
database or the Redis of this deployment, the metadata service of the cloud, or any internal
system. Every call here goes only to public addresses over https, and the address that was checked
is the one that is connected to. It also has limits of time and size, never sends the keys of the
tool to another host, and is recorded without the path, the query, the keys or the answer.
"""

import contextlib
import ipaddress
import logging
import socket
import time
from urllib.parse import urljoin, urlsplit

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter

from .models import ToolCall

logger = logging.getLogger(__name__)

MAX_REDIRECTS = 3
CHUNK = 8192

# What the bot (and the AI) is told when a call fails: short, and never with the address or the
# answer of the endpoint, which can carry the keys
MESSAGES = {
    "blocked": "The address of this tool is not allowed.",
    "timeout": "The service took too long to answer.",
    "too_large": "The answer of the service is too large.",
    "http_error": "The service answered with an error (status {status}).",
    "unreachable": "The service could not be reached.",
    "redirects": "The service redirected too many times.",
}


class ToolCallError(Exception):
    """A call that failed. Its text is safe to show to the bot and to the AI."""

    def __init__(self, reason, http_status=None):
        self.reason = reason
        self.http_status = http_status
        super().__init__(MESSAGES[reason].format(status=http_status))


class PinnedAdapter(HTTPAdapter):
    """Connects to the address that was already checked but still speaks to the name: the TLS
    server name and the certificate check use the host, so https keeps working."""

    def __init__(self, host):
        self.host = host
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        super().init_poolmanager(
            connections,
            maxsize,
            block,
            server_hostname=self.host,
            assert_hostname=self.host,
            **pool_kwargs,
        )


def is_public(address):
    ip = ipaddress.ip_address(address)
    if getattr(ip, "ipv4_mapped", None) is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def public_address(host, port):
    """The address to connect to, only if every address the name resolves to is public."""
    try:
        found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise ToolCallError("unreachable") from None
    addresses = [item[4][0] for item in found]
    if not addresses or not all(is_public(address) for address in addresses):
        raise ToolCallError("blocked")
    return addresses[0]


def checked(url):
    """The parts of a url that may be called, or a ToolCallError."""
    parts = urlsplit(url)
    try:
        host, port = parts.hostname, parts.port or 443
    except ValueError:
        raise ToolCallError("blocked") from None
    if parts.scheme != "https" or not host or parts.username or parts.password:
        raise ToolCallError("blocked")
    return parts, host, port, public_address(host, port)


def pinned_url(parts, address, port):
    shown = f"[{address}]" if ":" in address else address
    path = parts.path or "/"
    return f"https://{shown}:{port}{path}" + (f"?{parts.query}" if parts.query else "")


def fetch(url, headers, params):
    """Follow the redirects by hand, checking every hop, and read the answer within the limits."""
    deadline = time.monotonic() + settings.TOOL_CALL_TIMEOUT
    current_host, status = None, None
    for _ in range(MAX_REDIRECTS + 1):
        parts, host, port, address = checked(url)
        if current_host is not None and host.lower() != current_host:
            headers, params = {}, None  # the keys of the tool never go to another host
        current_host = host.lower()
        session = requests.Session()
        session.trust_env = False  # a proxy of the environment would skip the checks
        session.mount("https://", PinnedAdapter(host))
        host_header = host if port == 443 else f"{host}:{port}"
        try:
            response = session.get(
                pinned_url(parts, address, port),
                headers={**(headers or {}), "Host": host_header},
                params=params,
                timeout=(settings.TOOL_CALL_TIMEOUT, settings.TOOL_CALL_TIMEOUT),
                allow_redirects=False,
                stream=True,
            )
        except requests.Timeout:
            raise ToolCallError("timeout") from None
        except requests.RequestException:
            raise ToolCallError("unreachable") from None
        with response:
            status = response.status_code
            if response.is_redirect:
                url, params = urljoin(url, response.headers["Location"]), None
                continue
            return read_limited(response, deadline), status, host
    raise ToolCallError("redirects", status)


def read_limited(response, deadline):
    if not 200 <= response.status_code < 300:
        raise ToolCallError("http_error", response.status_code)
    limit = settings.TOOL_CALL_MAX_BYTES
    announced = response.headers.get("Content-Length", "")
    if announced.isdigit() and int(announced) > limit:
        raise ToolCallError("too_large")
    body = bytearray()
    try:
        for chunk in response.iter_content(chunk_size=CHUNK):
            body.extend(chunk)
            if len(body) > limit:
                raise ToolCallError("too_large")
            if time.monotonic() > deadline:
                raise ToolCallError("timeout")
    except requests.Timeout:
        raise ToolCallError("timeout") from None
    except requests.RequestException:
        raise ToolCallError("unreachable") from None
    return bytes(body).decode(response.encoding or "utf-8", errors="replace")


def safe_get(url, *, account, tool, headers=None, params=None):
    """
    GET the endpoint of a tool and return the text of the answer, or raise a ToolCallError.
    Every call is recorded, also the ones that fail or are blocked.
    """
    started = time.perf_counter()
    status, http_status, host = "ok", None, ""
    with contextlib.suppress(ValueError):
        host = (urlsplit(url).hostname or "")[:255]
    try:
        text, http_status, host = fetch(url, headers, params)
        return text
    except ToolCallError as error:
        status, http_status = error.reason, error.http_status
        logger.warning("Tool call of account %s: %s (host %s)", account.pk, error.reason, host)
        raise
    finally:
        record(account, tool, host, status, http_status, started)


def record(account, tool, host, status, http_status, started):
    """Keep the call. A record that cannot be saved never breaks the call."""
    try:
        ToolCall.objects.create(
            account=account,
            tool=tool[:100],
            host=host,
            status=status,
            http_status=http_status,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        logger.warning("Could not record a tool call (%s)", type(exc).__name__)
