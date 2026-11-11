"""
Tests for the files that clients send: marking them in the messages, opening them, and
the cleanup of what was saved.

Only the HTTP call to Meta is replaced; wanps-core and the storage run for real.
"""

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import App, Message

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.models import MessageFile
from apps.conversations.tasks import delete_expired_message_files
from apps.conversations.tests.test_inbox import messages_url
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

CLIENT = "593990000001"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture(autouse=True)
def saved_files_go_to_a_temporary_folder(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def admin(tenant):
    return client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))


def add_file_message(
    link, raw, text="", message_type="image", contact_id=CLIENT, direction=Message.DIRECTION_IN
):
    """An incoming message whose stored payload is what Meta sent."""
    return Message.objects.create(
        channel=link.account.channel,
        account_id=link.account_id,
        external_id=f"ext.{link.account_id}.{contact_id}.{Message.objects.count()}",
        contact_id=contact_id,
        direction=direction,
        message_type=message_type,
        text=text,
        raw=raw,
    )


def whatsapp_file(kind, **media):
    return {"type": kind, kind: {"id": f"media-{kind}", **media}}


def messages_of(api, link, contact_id=CLIENT, **params):
    channel = link.account.channel
    response = api.get(messages_url(channel, contact_id), {"account": str(link.id), **params})
    assert response.status_code == 200
    return response.data["data"]["messages"]


def test_the_messages_of_a_chat_say_which_ones_carry_a_file(admin, tenant, meta_app):
    whatsapp = add_account(tenant, meta_app, "111", channel="whatsapp")
    add_file_message(whatsapp, whatsapp_file("image", mime_type="image/jpeg"), text="[image]")
    add_file_message(
        whatsapp,
        whatsapp_file("document", mime_type="application/pdf", filename="invoice.pdf"),
        text="[document]",
        message_type="document",
    )
    add_file_message(
        whatsapp, {"type": "text", "text": {"body": "Hola"}}, text="Hola", message_type="text"
    )
    messenger = add_account(tenant, meta_app, "222", channel="messenger")
    event = {
        "message": {
            "mid": "m1",
            "attachments": [{"type": "video", "payload": {"url": "https://cdn.test/v"}}],
        }
    }
    add_file_message(messenger, event, text="[video]", message_type="video")

    on_whatsapp = messages_of(admin, whatsapp)
    on_messenger = messages_of(admin, messenger)

    assert [m["file"] for m in on_whatsapp] == [
        {"kind": "image", "mime_type": "image/jpeg", "filename": ""},
        {"kind": "document", "mime_type": "application/pdf", "filename": "invoice.pdf"},
        None,
    ]
    assert on_messenger[0]["file"] == {"kind": "video", "mime_type": "", "filename": ""}


def file_url(channel, message, contact_id=CLIENT):
    return messages_url(channel, contact_id) + f"{message.pk}/file/"


def open_file(api, link, message, contact_id=CLIENT):
    return api.get(file_url(link.account.channel, message, contact_id), {"account": str(link.id)})


def meta_answer(json_body=None, content=b"", status=200):
    response = MagicMock(ok=status < 400, status_code=status, content=content, text="meta said no")
    response.json.return_value = json_body or {}
    return response


def meta_gives(content=b"JPEG", mime_type="image/jpeg"):
    """What Meta answers for a WhatsApp file: its address first, then the bytes."""
    address = {
        "url": "https://lookaside.test/file",
        "mime_type": mime_type,
        "file_size": len(content),
    }
    return [meta_answer(address), meta_answer(content=content)]


def test_opening_a_file_downloads_it_from_meta_saves_it_and_returns_the_bytes(
    admin, tenant, meta_app
):
    link = add_account(tenant, meta_app, "111")
    message = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))

    with patch("requests.get", side_effect=meta_gives(b"JPEG")) as meta:
        response = open_file(admin, link, message)

    assert response.status_code == 200
    assert response.content == b"JPEG"
    assert response["Content-Type"] == "image/jpeg"
    assert meta.call_count == 2


def test_opening_it_again_serves_the_saved_file_without_calling_meta(admin, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    message = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))
    with patch("requests.get", side_effect=meta_gives(b"JPEG")):
        open_file(admin, link, message)

    with patch("requests.get") as meta:
        again = open_file(admin, link, message)

    assert (again.status_code, again.content, again["Content-Type"]) == (200, b"JPEG", "image/jpeg")
    meta.assert_not_called()


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_role_of_the_business_can_open_a_file(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111")
    message = add_file_message(
        link, whatsapp_file("audio", mime_type="audio/ogg"), message_type="audio"
    )
    member = client_for(add_member(tenant, "member@acme.test", role))

    with patch("requests.get", side_effect=meta_gives(b"OGG", "audio/ogg")):
        response = open_file(member, link, message)

    assert (response.status_code, response.content) == (200, b"OGG")


def test_a_message_without_a_file_does_not_exist(admin, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    text = add_file_message(
        link, {"type": "text", "text": {"body": "Hola"}}, text="Hola", message_type="text"
    )

    with patch("requests.get") as meta:
        response = open_file(admin, link, text)

    assert response.status_code == 404
    meta.assert_not_called()


def test_a_file_of_another_business_does_not_exist(admin, tenant, meta_app):
    mine = add_account(tenant, meta_app, "111")
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "333")
    secret = add_file_message(rival, whatsapp_file("image", mime_type="image/jpeg"))
    other_chat = add_file_message(mine, whatsapp_file("image"), contact_id="593990000009")

    with patch("requests.get") as meta:
        # Its own account id, a message that is not in the chat, and the rival's account id
        assert open_file(admin, mine, secret).status_code == 404
        assert open_file(admin, mine, other_chat).status_code == 404
        assert open_file(admin, rival, secret).status_code == 404

    meta.assert_not_called()


def test_a_file_bigger_than_16_mb_is_rejected_and_not_saved(admin, tenant, meta_app, tmp_path):
    link = add_account(tenant, meta_app, "111")
    message = add_file_message(
        link, whatsapp_file("video", mime_type="video/mp4"), message_type="video"
    )
    too_big = b"x" * (16 * 1024 * 1024 + 1)

    with patch("requests.get", side_effect=meta_gives(too_big, "video/mp4")):
        response = open_file(admin, link, message)

    assert response.status_code == 413
    assert response.data["success"] is False
    assert "16 MB" in response.data["message"]
    assert list(tmp_path.iterdir()) == []
    assert not MessageFile.objects.exists()


@pytest.mark.parametrize("refusal", [404, 410])
def test_a_file_that_meta_no_longer_has_gives_a_clear_error_and_saves_nothing(
    admin, tenant, meta_app, tmp_path, refusal
):
    link = add_account(tenant, meta_app, "111")
    message = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))

    with patch("requests.get", return_value=meta_answer(status=refusal)):
        response = open_file(admin, link, message)

    assert response.status_code == 410
    assert response.data["success"] is False
    assert "no longer" in response.data["message"]
    assert list(tmp_path.iterdir()) == []
    assert not MessageFile.objects.exists()


@pytest.mark.parametrize("failure", [requests.Timeout("slow"), requests.ConnectionError("down")])
def test_when_meta_cannot_be_reached_the_error_says_to_try_again(admin, tenant, meta_app, failure):
    link = add_account(tenant, meta_app, "111")
    message = add_file_message(link, whatsapp_file("image"))

    with patch("requests.get", side_effect=failure):
        unreachable = open_file(admin, link, message)
    with patch("requests.get", return_value=meta_answer(status=500)):
        failing = open_file(admin, link, message)

    for response in (unreachable, failing):
        assert response.status_code == 502
        assert "try again" in response.data["message"]


def save_file_aged(admin, link, message, days, content=b"JPEG"):
    """Open a file, then make it look as if it had been saved `days` days ago."""
    with patch("requests.get", side_effect=meta_gives(content)):
        assert open_file(admin, link, message).status_code == 200
    MessageFile.objects.filter(message=message).update(
        created_at=timezone.now() - timedelta(days=days)
    )


def test_the_cleanup_deletes_the_files_saved_more_than_30_days_ago(
    admin, tenant, meta_app, tmp_path
):
    link = add_account(tenant, meta_app, "111")
    old = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))
    recent = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))
    save_file_aged(admin, link, old, days=31)
    save_file_aged(admin, link, recent, days=29)

    deleted = delete_expired_message_files()

    assert deleted == 1
    assert list(MessageFile.objects.values_list("message_id", flat=True)) == [recent.pk]
    assert len(list((tmp_path / "message-files").iterdir())) == 1


def test_opening_a_deleted_file_asks_meta_again(admin, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    message = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))
    save_file_aged(admin, link, message, days=31)
    delete_expired_message_files()

    with patch("requests.get", side_effect=meta_gives(b"JPEG2")) as meta:
        response = open_file(admin, link, message)

    assert (response.status_code, response.content) == (200, b"JPEG2")
    assert meta.call_count == 2


def test_the_cleanup_is_scheduled_every_day(settings):
    [entry] = [
        entry
        for entry in settings.CELERY_BEAT_SCHEDULE.values()
        if entry["task"] == "apps.conversations.tasks.delete_expired_message_files"
    ]

    assert entry["schedule"] == 24 * 60 * 60


def test_api_docs_describe_the_file_in_messages_and_the_file_endpoint():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    def named(ref):
        return components[ref["$ref"].rsplit("/", 1)[1]]

    reading = schema["paths"]["/api/v1/inbox/{channel}/conversations/{contact_id}/messages/"]["get"]
    response = reading["responses"]["200"]["content"]["application/json"]["schema"]
    messages = named(
        named(named(response)["properties"]["data"])["properties"]["messages"]["items"]
    )
    file = named(messages["properties"]["file"]["allOf"][0])
    assert set(file["properties"]) == {"kind", "mime_type", "filename"}

    path = "/api/v1/inbox/{channel}/conversations/{contact_id}/messages/{message_id}/file/"
    opening = schema["paths"][path]["get"]
    assert {p["name"] for p in opening["parameters"] if p["in"] == "query"} == {"account"}
    assert {"200", "404", "410", "413", "502"} <= set(opening["responses"])


@pytest.mark.parametrize("refusal", [400, 401, 403, 429])
def test_a_refusal_that_is_not_about_the_file_is_not_reported_as_gone(
    admin, tenant, meta_app, refusal
):
    link = add_account(tenant, meta_app, "111")
    message = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))

    with patch("requests.get", return_value=meta_answer(status=refusal)):
        response = open_file(admin, link, message)

    assert response.status_code == 502
    assert "try again" in response.data["message"]


def test_a_document_is_a_download_with_its_name_and_every_file_has_nosniff(admin, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    page = add_file_message(
        link,
        whatsapp_file("document", mime_type="text/html", filename="page.html"),
        message_type="document",
    )
    picture = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))

    with patch("requests.get", side_effect=meta_gives(b"<script>x()</script>", "text/html")):
        document = open_file(admin, link, page)
    with patch("requests.get", side_effect=meta_gives(b"JPEG", "image/jpeg")):
        image = open_file(admin, link, picture)

    assert document["Content-Disposition"] == 'attachment; filename="page.html"'
    assert "attachment" not in image.get("Content-Disposition", "")
    assert document["X-Content-Type-Options"] == image["X-Content-Type-Options"] == "nosniff"


def test_a_file_without_a_known_type_is_served_as_plain_bytes(admin, tenant, meta_app):
    link = add_account(tenant, meta_app, "111", channel="messenger")
    event = {
        "message": {"attachments": [{"type": "image", "payload": {"url": "https://cdn.test/i"}}]}
    }
    message = add_file_message(link, event)
    cdn = meta_answer(content=b"PNG")
    cdn.headers = {}

    with patch("requests.get", return_value=cdn):
        first = open_file(admin, link, message, CLIENT)
    with patch("requests.get") as meta:
        again = open_file(admin, link, message, CLIENT)

    assert first["Content-Type"] == again["Content-Type"] == "application/octet-stream"
    meta.assert_not_called()


def test_opening_a_file_over_a_leftover_of_the_same_name_leaves_nothing_behind(
    admin, tenant, meta_app, tmp_path
):
    link = add_account(tenant, meta_app, "111")
    message = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))
    default_storage.save(f"message-files/{message.pk}", ContentFile(b"leftover"))

    save_file_aged(admin, link, message, days=31)
    delete_expired_message_files()

    assert list((tmp_path / "message-files").iterdir()) == []


def test_a_file_that_cannot_be_deleted_does_not_stop_the_cleanup(admin, tenant, meta_app, tmp_path):
    link = add_account(tenant, meta_app, "111")
    stuck = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))
    other = add_file_message(link, whatsapp_file("image", mime_type="image/jpeg"))
    save_file_aged(admin, link, stuck, days=40)
    save_file_aged(admin, link, other, days=35)

    with patch(
        "apps.conversations.tasks.default_storage.delete", side_effect=[OSError("locked"), None]
    ):
        deleted = delete_expired_message_files()

    # The first (oldest) one fails; the other is still deleted, and the failed one is tried again later
    assert deleted == 1
    assert list(MessageFile.objects.values_list("message_id", flat=True)) == [stuck.pk]


def test_only_incoming_messages_can_have_a_file(admin, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    ours = add_file_message(
        link, whatsapp_file("image", mime_type="image/jpeg"), direction=Message.DIRECTION_OUT
    )

    with patch("requests.get") as meta:
        response = open_file(admin, link, ours)

    assert response.status_code == 404
    meta.assert_not_called()
    assert [m["file"] for m in messages_of(admin, link)] == [None]


def test_the_empty_fields_of_a_file_are_valid_in_the_api_docs():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    file = schema["components"]["schemas"]["MessageFile"]["properties"]

    assert "minLength" not in file["mime_type"]
    assert "minLength" not in file["filename"]


def test_an_svg_sent_as_a_picture_is_still_a_download(admin, tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    message = add_file_message(link, whatsapp_file("image", mime_type="image/svg+xml"))

    with patch("requests.get", side_effect=meta_gives(b"<svg onload='x()'/>", "image/svg+xml")):
        response = open_file(admin, link, message)

    assert response["Content-Disposition"].startswith("attachment")


def test_the_folder_of_the_saved_files_comes_from_the_environment(tmp_path):
    # Settings load once per process, so they are read again in a fresh one
    def media_root(**extra):
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.local", **extra}
        result = subprocess.run(
            [sys.executable, "-c", "from django.conf import settings; print(settings.MEDIA_ROOT)"],
            cwd=settings.BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return Path(result.stdout.strip().splitlines()[-1])

    assert media_root(MEDIA_ROOT=str(tmp_path / "files")) == tmp_path / "files"
    assert media_root(MEDIA_ROOT="") == Path(settings.BASE_DIR) / "media"


def test_the_tests_never_reach_the_redis_of_a_developer():
    # A message saved for a connected account announces itself and asks for permits through these
    from channels.layers import get_channel_layer
    from django.core.cache import caches

    assert caches["ws_tickets"].__class__.__name__ == "LocMemCache"
    assert get_channel_layer().__class__.__name__ == "InMemoryChannelLayer"
