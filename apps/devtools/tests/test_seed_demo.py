"""
The seed_demo command: realistic test data, only for development.
"""

import secrets
from collections import Counter
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.utils import timezone
from rest_framework.test import APIClient
from wanps.messaging.models import Account, App, Conversation, Message

from apps.channels.models import ChannelAccount
from apps.devtools import fake_meta
from apps.tenants.models import Membership, Tenant

User = get_user_model()


@pytest.fixture
def password(monkeypatch):
    value = secrets.token_urlsafe(12)
    monkeypatch.setenv("SEED_DEMO_PASSWORD", value)
    return value


@pytest.fixture
def seed(db, settings, password):
    """Run the command in development, with the test password defined."""
    settings.DEBUG = True

    def run(*args):
        out = StringIO()
        call_command("seed_demo", *args, stdout=out)
        return out.getvalue()

    return run


def api_for(email, password, tenant=None):
    """An API client logged in as that user, working in that business."""
    api = APIClient()
    answer = api.post(
        "/api/v1/accounts/token/", {"email": email, "password": password}, format="json"
    )
    headers = {"HTTP_AUTHORIZATION": f"Bearer {answer.data['access']}"}
    if tenant is not None:
        headers["HTTP_X_TENANT_ID"] = str(tenant.id)
    api.credentials(**headers)
    return api


def test_it_creates_two_demo_businesses_with_a_user_per_role_and_one_in_both(seed, password):
    seed()

    acme = Tenant.objects.get(name="demo-Acme Dental")
    rival = Tenant.objects.get(name="demo-Rival Clinic")
    roles = {
        m.user.email: m.role for m in Membership.objects.filter(tenant=acme).select_related("user")
    }
    assert roles["demo-admin@demo.test"] == "admin"
    assert roles["demo-supervisor@demo.test"] == "supervisor"
    assert roles["demo-agent@demo.test"] == "agent"
    multi = User.objects.get(email="demo-multi@demo.test")
    assert {(m.tenant.name, m.role) for m in multi.memberships.all()} == {
        ("demo-Acme Dental", "admin"),
        ("demo-Rival Clinic", "agent"),
    }
    # They log in with the password of the environment, in each of their businesses
    for tenant in (acme, rival):
        current = api_for("demo-multi@demo.test", password, tenant).get("/api/v1/tenants/current/")
        assert current.status_code == 200
        assert current.data["data"]["name"] == tenant.name


def test_it_refuses_to_run_without_debug_and_touches_nothing(seed, settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG"):
        seed()

    assert not Tenant.objects.exists()
    assert not User.objects.exists()


def test_it_refuses_to_run_without_the_password(seed, monkeypatch):
    monkeypatch.delenv("SEED_DEMO_PASSWORD")

    with pytest.raises(CommandError, match="SEED_DEMO_PASSWORD"):
        seed()

    assert not Tenant.objects.exists()
    assert not User.objects.exists()


def test_it_creates_the_accounts_with_fake_tokens_and_one_inactive(seed, password):
    seed()

    acme = Tenant.objects.get(name="demo-Acme Dental")
    rival = Tenant.objects.get(name="demo-Rival Clinic")
    listed = (
        api_for("demo-admin@demo.test", password, acme)
        .get("/api/v1/channels/accounts/")
        .data["data"]
    )
    channels = sorted(account["channel"] for account in listed)
    assert channels == ["instagram", "messenger", "messenger", "whatsapp", "whatsapp"]
    inactive = [account for account in listed if not account["is_active"]]
    assert [account["channel"] for account in inactive] == ["messenger"]
    # Each business has its own accounts, with fake tokens, on a demo Meta App
    rival_listed = api_for("demo-rival-admin@demo.test", password, rival).get(
        "/api/v1/channels/accounts/"
    )
    assert {a["id"] for a in rival_listed.data["data"]}.isdisjoint({a["id"] for a in listed})
    assert rival_listed.data["data"]
    accounts = Account.objects.filter(channel_account__isnull=False)
    assert accounts.count() == 5 + len(rival_listed.data["data"])
    assert all(
        a.external_id.startswith("demo-") and a.access_token.startswith("demo-fake")
        for a in accounts
    )
    app = App.objects.get()
    assert app.name == "demo-meta-app"
    assert {a.app_id for a in accounts} == {app.id}
    assert Tenant.objects.get(pk=acme.pk).meta_app == app
    assert Tenant.objects.get(pk=rival.pk).meta_app == app
    assert ChannelAccount.objects.filter(tenant=acme).count() == 5


def all_chats(api, channel):
    """Every chat of a channel, going through the pages like the frontend does."""
    chats, offset = [], 0
    while True:
        page = api.get(
            f"/api/v1/inbox/{channel}/conversations/", {"limit": 100, "offset": offset}
        ).data["data"]
        chats += page["conversations"]
        if not page["has_more"]:
            return chats
        offset += 100


def test_each_channel_gets_about_eight_conversations_with_the_mixes(seed, password):
    seed()
    acme = Tenant.objects.get(name="demo-Acme Dental")
    api = api_for("demo-admin@demo.test", password, acme)

    for channel in ("whatsapp", "messenger", "instagram"):
        chats = all_chats(api, channel)
        assert len(chats) >= 8, channel
        assert {chat["window_open"] for chat in chats} == {True, False}, channel
        # The bot: active, paused until someone resumes it, and paused until a date
        states = {(chat["bot_paused"], chat["bot_paused_until"] is not None) for chat in chats}
        assert {(False, False), (True, False), (True, True)} <= states, channel
        assert all(chat["paused_by"] for chat in chats if chat["bot_paused"]), channel

    # The same client writing to two accounts of the same channel
    for channel in ("whatsapp", "messenger"):
        by_client = Counter(chat["contact_id"] for chat in all_chats(api, channel))
        assert max(by_client.values()) == 2, channel

    # Messenger and Instagram: some client wrote more than 7 days ago (to try human_agent)
    now = timezone.now()
    for channel in ("messenger", "instagram"):
        last_written = {}
        for message in Message.objects.filter(
            channel=channel, direction="in", account__external_id__startswith="demo-"
        ):
            key = (message.account_id, message.contact_id)
            last_written[key] = max(last_written.get(key, message.created_at), message.created_at)
        assert any(now - at > timedelta(days=7) for at in last_written.values()), channel


def whatsapp_chat(seed, password, contact):
    """The messages of a chat of the first WhatsApp account, oldest first."""
    seed()
    acme = Tenant.objects.get(name="demo-Acme Dental")
    api = api_for("demo-admin@demo.test", password, acme)
    accounts = api.get("/api/v1/channels/accounts/").data["data"]
    account = next(a["id"] for a in accounts if a["external_id"] == "demo-wa-1")
    messages, before = [], None
    while True:
        params = {"account": account, "limit": 100, **({"before": before} if before else {})}
        page = api.get(f"/api/v1/inbox/whatsapp/conversations/{contact}/messages/", params).data[
            "data"
        ]
        messages = page["messages"] + messages
        if not page["has_more"]:
            return messages
        before = page["messages"][0]["id"]


def test_one_chat_has_more_than_120_messages_with_long_texts_line_breaks_emojis_and_a_long_link(
    seed, password
):
    messages = whatsapp_chat(seed, password, "demo-elena")

    texts = [m["text"] for m in messages]
    assert len(messages) > 120
    assert any(len(text) >= 400 for text in texts)
    assert any("\n" in text for text in texts)
    assert any(any(ord(char) > 0x1F000 for char in text) for text in texts)
    assert any(
        len(word) >= 150 and word.startswith("http") for text in texts for word in text.split()
    )


def test_the_messages_cover_every_direction_type_status_and_sender(seed, password):
    messages = whatsapp_chat(seed, password, "demo-tomas")

    assert {m["direction"] for m in messages} == {"in", "out"}
    assert {"text", "image", "document", "audio"} <= {m["type"] for m in messages}
    assert {"sent", "delivered", "read", "failed"} <= {m["status"] for m in messages}
    outgoing = [m for m in messages if m["direction"] == "out"]
    assert any(m["sent_by"] == "" for m in outgoing), "bot"
    assert any(m["sent_by"] != "" for m in outgoing), "person"
    # The bot writes again after a person has answered
    kinds = ["person" if m["sent_by"] else "bot" for m in outgoing]
    first_person = kinds.index("person")
    assert kinds[first_person:].count("bot") >= 2


def test_one_channel_has_more_than_150_conversations(seed, password):
    seed()
    acme = Tenant.objects.get(name="demo-Acme Dental")
    api = api_for("demo-admin@demo.test", password, acme)

    first_page = api.get("/api/v1/inbox/whatsapp/conversations/").data["data"]

    assert first_page["has_more"] is True
    assert len(all_chats(api, "whatsapp")) > 150


@pytest.fixture
def fake():
    fake_meta.install()
    yield
    fake_meta.uninstall()


def test_a_closed_window_chat_of_the_seed_answers_conflict_when_sending(seed, password, fake):
    seed()
    acme = Tenant.objects.get(name="demo-Acme Dental")
    api = api_for("demo-agent@demo.test", password, acme)
    accounts = api.get("/api/v1/channels/accounts/").data["data"]
    account = next(a["id"] for a in accounts if a["external_id"] == "demo-wa-1")

    def send(contact):
        return api.post(
            f"/api/v1/inbox/whatsapp/conversations/{contact}/send/",
            {"account": account, "text": "Hola de nuevo"},
            format="json",
        )

    assert send("demo-pablo").status_code == 409  # wrote 30 hours ago
    assert send("demo-ana").status_code == 201  # wrote 5 minutes ago; sent by the fake Meta


def counts():
    return {
        "tenants": Tenant.objects.count(),
        "users": User.objects.count(),
        "accounts": Account.objects.count(),
        "messages": Message.objects.count(),
        "conversations": Conversation.objects.count(),
    }


def test_the_summary_says_what_was_created_without_the_password(seed, password):
    out = seed()

    assert "demo-Acme Dental" in out and "demo-Rival Clinic" in out
    assert "demo-admin@demo.test" in out and "demo-multi@demo.test" in out
    assert f"Messages: {Message.objects.count()}" in out
    assert "SEED_DEMO_PASSWORD" in out
    assert password not in out


def test_running_it_twice_does_not_duplicate_anything(seed):
    seed()
    first = counts()

    second_run = seed()

    assert counts() == first
    assert "already" in second_run


def test_reset_deletes_only_what_was_seeded_and_creates_it_again(seed):
    real_tenant = Tenant.objects.create(name="Real Clinic")
    real_app = App.objects.create(name="Real app", app_secret="s", verify_token="v")
    real_account = Account.objects.create(
        channel="whatsapp",
        app=real_app,
        name="Real",
        external_id="5551234",
        access_token="real-token",
    )
    ChannelAccount.objects.create(tenant=real_tenant, account=real_account)
    real_message = Message.objects.create(
        channel="whatsapp",
        account=real_account,
        external_id="real-1",
        contact_id="593990000000",
        direction="in",
        message_type="text",
        text="Hola",
    )
    real_user = User.objects.create_user(email="real@example.com", password="Another-pass-1")
    seed()
    seeded = counts()

    seed("--reset")

    after = counts()
    assert after == seeded
    assert Tenant.objects.filter(pk=real_tenant.pk).exists()
    assert Message.objects.filter(pk=real_message.pk, text="Hola").exists()
    assert User.objects.filter(pk=real_user.pk).exists()
    assert Tenant.objects.filter(name__startswith="demo-").count() == 2
    assert Account.objects.filter(external_id__startswith="demo-").count() == 6


def test_member_option_adds_a_user_as_admin_of_both_businesses(seed):
    me = User.objects.create_user(email="me@example.com", password="Another-pass-1")

    seed("--member", "me@example.com")

    memberships = Membership.objects.filter(user=me)
    assert {(m.tenant.name, m.role) for m in memberships} == {
        ("demo-Acme Dental", "admin"),
        ("demo-Rival Clinic", "admin"),
    }


def test_member_option_with_an_unknown_user_stops_before_creating_anything(seed):
    with pytest.raises(CommandError, match="nobody@example.com"):
        seed("--member", "nobody@example.com")

    assert not Tenant.objects.exists()
    assert not User.objects.exists()


def test_a_real_business_named_like_a_demo_one_is_neither_touched_nor_taken_for_seeded_data(seed):
    real_tenant = Tenant.objects.create(name="demo-clinic")
    real_user = User.objects.create_user(email="demo-ana@demo.test", password="Another-pass-1")

    seed()

    assert Tenant.objects.filter(name="demo-Acme Dental").exists()
    seed("--reset")
    assert Tenant.objects.filter(pk=real_tenant.pk).exists()
    assert User.objects.filter(pk=real_user.pk).exists()


def test_the_people_who_answered_are_members_of_the_business_and_match_who_paused_the_bot(seed):
    seed()
    members = {}
    for membership in Membership.objects.select_related("user"):
        members.setdefault(membership.tenant_id, set()).add(membership.user.full_name)

    def tenant_of(account):
        return account.channel_account.tenant_id

    by_hand = (
        Message.objects.filter(direction="out")
        .exclude(sent_by="")
        .select_related("account__channel_account")
    )
    for message in by_hand:
        assert message.sent_by in members[tenant_of(message.account)], (
            message.sent_by,
            message.account.name,
        )
    # In a chat paused by someone, the person who answered is who paused it
    for conversation in Conversation.objects.exclude(paused_by="").select_related("account"):
        signed = by_hand.filter(account=conversation.account, contact_id=conversation.contact_id)
        assert signed.exists()
        assert {m.sent_by for m in signed} == {conversation.paused_by}
