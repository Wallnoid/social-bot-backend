"""
Replying to a WhatsApp client with an approved template: listing the ones that can be sent
and sending one. Only Meta is simulated.
"""

from datetime import timedelta
from unittest import mock

import pytest
import requests
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import Account, App, Message

from apps.channels.tests.test_manage_accounts import TOKEN, add_account
from apps.conversations.tests.test_inbox import add_message, messages_url
from apps.conversations.tests.test_send import CLIENT, meta_replies, send_url
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

TEMPLATES_URL = "/api/v1/inbox/whatsapp/templates/"
BODY = {"type": "BODY", "text": "Hola {{1}}, tu cita es el {{2}}."}


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


def meta_template(
    name="cita", language="es", category="UTILITY", status="APPROVED", components=None
):
    """A template as Meta lists it."""
    return {
        "name": name,
        "language": language,
        "category": category,
        "status": status,
        "components": [BODY] if components is None else components,
    }


def meta_lists(*templates):
    """Meta answers the list of templates of the WhatsApp Business account."""
    response = mock.Mock(ok=True, status_code=200)
    response.json.return_value = {"data": list(templates)}
    return mock.patch("requests.get", return_value=response)


@pytest.mark.parametrize("role", Membership.Role.values)
def test_a_member_lists_the_sendable_templates_of_a_whatsapp_account(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111", channel="whatsapp")
    member = client_for(add_member(tenant, "member@acme.test", role))

    with meta_lists(
        meta_template(),
        meta_template(name="con_imagen", components=[{"type": "HEADER", "format": "IMAGE"}, BODY]),
        meta_template(name="pendiente", status="PENDING"),
    ) as get:
        response = member.get(TEMPLATES_URL, {"account": str(link.id)})

    assert response.status_code == 200
    assert response.data["data"] == [
        {
            "name": "cita",
            "language": "es",
            "category": "UTILITY",
            "body": "Hola {{1}}, tu cita es el {{2}}.",
            "variables": 2,
        }
    ]
    # Asked of Meta with the business account id (WABA) and the token of that account
    assert "/998877/message_templates" in get.call_args.args[0]
    assert get.call_args.kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"


def send_template_to(
    api, link, contact=CLIENT, name="cita", language="es", params=("Ana", "martes")
):
    body = {
        "account": str(link.id),
        "template": {"name": name, "language": language, "params": list(params)},
    }
    return api.post(send_url("whatsapp", contact), body, format="json")


def chat_with_a_client(tenant, meta_app, days_ago=0):
    """A WhatsApp account of the business whose client wrote that many days ago."""
    link = add_account(tenant, meta_app, "111", channel="whatsapp")
    message = add_message(link, CLIENT, "Hola")
    Message.objects.filter(pk=message.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )
    return link


def nothing_went_out(post):
    post.assert_not_called()
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()


def test_a_member_sends_a_template_with_its_values(tenant, meta_app):
    link = chat_with_a_client(tenant, meta_app)
    member = client_for(
        add_member(
            tenant, "member@acme.test", Membership.Role.AGENT, first_name="Rosa", last_name="Vega"
        )
    )

    with meta_lists(meta_template()), meta_replies("whatsapp") as post:
        response = send_template_to(member, link)

    assert response.status_code == 201
    payload = post.call_args.kwargs["json"]
    assert (payload["type"], payload["to"]) == ("template", CLIENT)
    assert payload["template"]["name"] == "cita"
    assert payload["template"]["language"]["code"] == "es"
    values = [p["text"] for p in payload["template"]["components"][0]["parameters"]]
    assert values == ["Ana", "martes"]
    sent = response.data["data"]
    assert (sent["direction"], sent["sent_by"]) == ("out", "Rosa Vega")
    chat = member.get(messages_url("whatsapp", CLIENT), {"account": str(link.id)}).data["data"]
    assert (chat["bot_paused"], chat["paused_by"]) == (True, "Rosa Vega")


def test_a_template_can_be_sent_when_the_window_is_closed(tenant, meta_app):
    link = chat_with_a_client(tenant, meta_app, days_ago=3)
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_lists(meta_template()), meta_replies("whatsapp"):
        response = send_template_to(member, link)

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("name", "language"),
    [("no_existe", "es"), ("cita", "en")],
    ids=["unknown name", "unknown language"],
)
def test_an_unknown_template_or_language_is_rejected_and_nothing_is_sent(
    tenant, meta_app, name, language
):
    link = chat_with_a_client(tenant, meta_app)
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_lists(meta_template()), meta_replies("whatsapp") as post:
        response = send_template_to(member, link, name=name, language=language)

    assert response.status_code == 400
    assert "template" in response.data["errors"]
    nothing_went_out(post)


@pytest.mark.parametrize(
    "params", [(), ("Ana",), ("Ana", "martes", "extra")], ids=["none", "too few", "too many"]
)
def test_a_wrong_number_of_values_is_rejected_and_nothing_is_sent(tenant, meta_app, params):
    link = chat_with_a_client(tenant, meta_app)
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_lists(meta_template()), meta_replies("whatsapp") as post:
        response = send_template_to(member, link, params=params)

    assert response.status_code == 400
    assert "2" in str(response.data["errors"]["template"])
    nothing_went_out(post)


def test_a_contact_that_never_wrote_cannot_receive_a_template(tenant, meta_app):
    link = chat_with_a_client(tenant, meta_app)
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_lists(meta_template()) as get, meta_replies("whatsapp") as post:
        response = send_template_to(member, link, contact="593999999999")

    assert response.status_code == 404
    get.assert_not_called()
    nothing_went_out(post)


@pytest.mark.parametrize("channel", ["messenger", "instagram"])
def test_templates_are_only_for_whatsapp(tenant, meta_app, channel):
    link = add_account(tenant, meta_app, "111", channel=channel)
    add_message(link, CLIENT, "Hola")
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    body = {
        "account": str(link.id),
        "template": {"name": "cita", "language": "es", "params": ["Ana", "martes"]},
    }

    with meta_replies(channel) as post:
        sent = member.post(send_url(channel), body, format="json")
    listed = member.get(f"/api/v1/inbox/{channel}/templates/", {"account": str(link.id)})

    assert sent.status_code == 400
    assert "template" in sent.data["errors"]
    nothing_went_out(post)
    assert listed.status_code == 404


def test_an_account_of_another_business_a_disconnected_one_or_without_a_waba_id_is_rejected(
    tenant, meta_app
):
    gone = add_account(tenant, meta_app, "222", channel="whatsapp")
    rival = add_account(
        Tenant.objects.create(name="Rival Clinic"), meta_app, "333", channel="whatsapp"
    )
    no_waba = chat_with_a_client(tenant, meta_app)
    Account.objects.filter(pk=no_waba.account_id).update(business_id="")
    for link in (gone, rival):
        add_message(link, CLIENT, "Hola")
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))
    admin.delete(f"/api/v1/channels/accounts/{gone.id}/")

    with meta_lists(meta_template()), meta_replies("whatsapp") as post:
        for not_available in (rival, gone):
            assert admin.get(TEMPLATES_URL, {"account": str(not_available.id)}).status_code == 404
            assert send_template_to(admin, not_available).status_code == 404
        listed = admin.get(TEMPLATES_URL, {"account": str(no_waba.id)})
        sent = send_template_to(admin, no_waba)

    assert (listed.status_code, sent.status_code) == (400, 400)
    assert "WhatsApp Business account id" in str(listed.data["errors"]["account"])
    assert "WhatsApp Business account id" in str(sent.data["errors"]["account"])
    nothing_went_out(post)


def test_meta_rejecting_the_list_or_the_send_answers_bad_gateway_and_stores_nothing(
    tenant, meta_app
):
    link = chat_with_a_client(tenant, meta_app)
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    refusal = mock.Mock(ok=False, status_code=401, text='{"error": "secret-meta-detail"}')

    with mock.patch("requests.get", return_value=refusal):
        listed = member.get(TEMPLATES_URL, {"account": str(link.id)})
        before_sending = send_template_to(member, link)
    with mock.patch("requests.get", side_effect=requests.ConnectionError("down")):
        network_down = member.get(TEMPLATES_URL, {"account": str(link.id)})
    with meta_lists(meta_template()), mock.patch("requests.post", return_value=refusal):
        at_sending = send_template_to(member, link)

    for answer in (listed, before_sending, network_down, at_sending):
        assert answer.status_code == 502
        assert "secret-meta-detail" not in str(answer.data)
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()
    chat = member.get(messages_url("whatsapp", CLIENT), {"account": str(link.id)}).data["data"]
    assert chat["bot_paused"] is False


def test_text_or_template_is_required_but_not_both(tenant, meta_app):
    link = chat_with_a_client(tenant, meta_app)
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    template = {"name": "cita", "language": "es", "params": ["Ana", "martes"]}

    with meta_lists(meta_template()), meta_replies("whatsapp") as post:
        both = member.post(
            send_url("whatsapp"),
            {"account": str(link.id), "text": "Hola", "template": template},
            format="json",
        )
        neither = member.post(send_url("whatsapp"), {"account": str(link.id)}, format="json")

    assert (both.status_code, neither.status_code) == (400, 400)
    nothing_went_out(post)


def test_api_docs_describe_the_templates():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    def named(part):
        # A field with its own description is wrapped: {"allOf": [{"$ref": ...}]}
        ref = part.get("$ref") or part["allOf"][0]["$ref"]
        return components[ref.rsplit("/", 1)[1]]

    listing = schema["paths"][TEMPLATES_URL]["get"]
    (account,) = [p for p in listing["parameters"] if p["name"] == "account"]
    assert account["required"] is True
    answer = named(listing["responses"]["200"]["content"]["application/json"]["schema"])
    template = named(answer["properties"]["data"]["items"])
    assert set(template["properties"]) == {"name", "language", "category", "body", "variables"}

    sending = schema["paths"]["/api/v1/inbox/{channel}/conversations/{contact_id}/send/"]["post"]
    request = named(sending["requestBody"]["content"]["application/json"]["schema"])
    values = named(request["properties"]["template"])
    assert set(values["properties"]) == {"name", "language", "params"}
    assert "template" in sending["responses"]["400"]["description"]
    assert {"404", "502"} <= set(sending["responses"])


def test_the_log_of_a_failed_listing_or_send_says_the_status_without_the_text_or_the_token(
    tenant, meta_app, caplog
):
    link = chat_with_a_client(tenant, meta_app)
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    refusal = mock.Mock(ok=False, status_code=401, text='{"error": "secret-meta-detail"}')

    with caplog.at_level("WARNING", logger="apps.conversations.views"):
        with mock.patch("requests.get", return_value=refusal):
            member.get(TEMPLATES_URL, {"account": str(link.id)})
        with meta_lists(meta_template()), mock.patch("requests.post", return_value=refusal):
            send_template_to(member, link)

    ours = [r.getMessage() for r in caplog.records if r.name == "apps.conversations.views"]
    assert len(ours) == 2
    assert all("401" in line for line in ours)
    # What wanps-core logs on its own is not ours; our lines carry no text of Meta nor the token
    assert all("secret-meta-detail" not in line and TOKEN not in line for line in ours)
