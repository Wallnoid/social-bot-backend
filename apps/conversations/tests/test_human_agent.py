"""
Replying as a person on Messenger and Instagram after the 24-hour window, with the
human-agent option, up to 7 days after the client's last message.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import Account, App, Message

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message, messages_url
from apps.conversations.tests.test_send import (
    CLIENT,
    meta_replies,
    recipient_and_text,
    send_url,
)
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


def chat_last_written(link, days_ago):
    """A chat whose client wrote that many days ago."""
    message = add_message(link, CLIENT, "Hola")
    Message.objects.filter(pk=message.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )


def reply_as_agent(api, link, channel, text="Seguimos aquí", **extra):
    body = {"account": str(link.id), "text": text, "human_agent": True, **extra}
    return api.post(send_url(channel), body, format="json")


@pytest.mark.parametrize("channel", ["messenger", "instagram"])
def test_a_member_replies_as_a_person_within_7_days_with_the_human_agent_option(
    tenant, meta_app, channel
):
    link = add_account(tenant, meta_app, "111", channel=channel)
    Account.objects.filter(pk=link.account_id).update(access_token="EAAG-this-account")
    chat_last_written(link, days_ago=2)
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_replies(channel) as post:
        response = reply_as_agent(member, link, channel)

    assert response.status_code == 201
    post.assert_called_once()
    payload = post.call_args.kwargs["json"]
    assert payload["tag"] == "HUMAN_AGENT"
    assert recipient_and_text(channel, payload) == (CLIENT, "Seguimos aquí")
    assert "EAAG-this-account" in str(post.call_args)


def test_the_human_agent_reply_appears_in_the_chat_as_outgoing_with_the_members_name_and_pauses_the_bot(
    tenant, meta_app
):
    link = add_account(tenant, meta_app, "111", channel="messenger")
    chat_last_written(link, days_ago=3)
    member = client_for(
        add_member(
            tenant, "member@acme.test", Membership.Role.AGENT, first_name="Rosa", last_name="Vega"
        )
    )

    with meta_replies("messenger"):
        response = reply_as_agent(member, link, "messenger", text="Seguimos aquí")

    sent = response.data["data"]
    assert (sent["direction"], sent["text"], sent["sent_by"]) == (
        "out",
        "Seguimos aquí",
        "Rosa Vega",
    )
    chat = member.get(messages_url("messenger", CLIENT), {"account": str(link.id)}).data["data"]
    assert chat["messages"][-1]["text"] == "Seguimos aquí"
    assert chat["messages"][-1]["sent_by"] == "Rosa Vega"
    assert (chat["bot_paused"], chat["paused_by"]) == (True, "Rosa Vega")


@pytest.mark.parametrize("channel", ["messenger", "instagram"])
def test_a_closed_window_without_the_option_answers_conflict_and_says_to_use_it(
    tenant, meta_app, channel
):
    link = add_account(tenant, meta_app, "111", channel=channel)
    chat_last_written(link, days_ago=2)
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_replies(channel) as post:
        response = member.post(
            send_url(channel), {"account": str(link.id), "text": "Hola de nuevo"}, format="json"
        )

    assert response.status_code == 409
    assert "human-agent option" in response.data["message"]
    post.assert_not_called()
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()


@pytest.mark.parametrize("channel", ["messenger", "instagram"])
def test_after_7_days_the_option_cannot_help_and_nothing_is_sent(tenant, meta_app, channel):
    link = add_account(tenant, meta_app, "111", channel=channel)
    chat_last_written(link, days_ago=8)
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_replies(channel) as post:
        response = reply_as_agent(member, link, channel)

    assert response.status_code == 409
    assert "7 days" in response.data["message"]
    assert "human-agent option" not in response.data["message"]
    post.assert_not_called()
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()


def test_the_option_is_rejected_on_whatsapp(tenant, meta_app):
    link = add_account(tenant, meta_app, "111", channel="whatsapp")
    add_message(link, CLIENT, "Hola")  # the window is open: only the option is wrong
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_replies("whatsapp") as post:
        response = reply_as_agent(member, link, "whatsapp")

    assert response.status_code == 400
    assert "human_agent" in response.data["errors"]
    post.assert_not_called()
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()


def test_an_account_of_another_business_or_a_disconnected_one_is_not_found_with_the_option(
    tenant, meta_app
):
    gone = add_account(tenant, meta_app, "222", channel="messenger")
    rival = add_account(
        Tenant.objects.create(name="Rival Clinic"), meta_app, "333", channel="messenger"
    )
    for link in (gone, rival):
        chat_last_written(link, days_ago=2)
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))
    admin.delete(f"/api/v1/channels/accounts/{gone.id}/")

    for not_available in (rival, gone):
        with meta_replies("messenger") as post:
            response = reply_as_agent(admin, not_available, "messenger")
        assert response.status_code == 404
        post.assert_not_called()
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()


def test_api_docs_describe_the_human_agent_option():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]
    operation = schema["paths"]["/api/v1/inbox/{channel}/conversations/{contact_id}/send/"]["post"]

    ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    option = components[ref.rsplit("/", 1)[1]]["properties"]["human_agent"]
    assert option["type"] == "boolean"
    assert option["default"] is False
    assert "Messenger and Instagram" in option["description"]
    conflict = operation["responses"]["409"]["description"]
    assert "human-agent" in conflict and "7 days" in conflict
    assert "no effect" in option["description"]


@pytest.mark.parametrize("channel", ["messenger", "instagram"])
def test_a_contact_that_never_wrote_cannot_be_answered_even_with_the_option(
    tenant, meta_app, channel
):
    link = add_account(tenant, meta_app, "111", channel=channel)
    chat_last_written(link, days_ago=1)  # another client wrote; this contact never did
    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))

    with meta_replies(channel) as post:
        response = member.post(
            send_url(channel, "999000999"),
            {"account": str(link.id), "text": "Hola", "human_agent": True},
            format="json",
        )

    assert response.status_code == 409
    assert "no message from the client" in response.data["message"]
    post.assert_not_called()
    assert not Message.objects.filter(direction=Message.DIRECTION_OUT).exists()
