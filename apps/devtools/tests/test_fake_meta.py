"""
The fake Meta: in development, sending a message needs no real Meta account.
"""

import os
import subprocess
import sys
from unittest import mock

import pytest
import requests
from django.apps import apps
from django.conf import settings as django_settings
from wanps.messaging.models import App, Message

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.conversations.tests.test_send import CLIENT, send_url
from apps.devtools import fake_meta
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def real_post():
    """The real `requests.post`, replaced by a mock that fails the test if Meta is reached."""
    original = mock.Mock(name="real requests.post")
    with mock.patch.object(requests, "post", original):
        fake_meta.install()
        yield original
        fake_meta.uninstall()


@pytest.mark.parametrize("channel", ["whatsapp", "messenger", "instagram"])
def test_with_the_fake_a_message_is_saved_and_shown_as_sent_without_calling_meta(
    tenant, meta_app, real_post, channel
):
    link = add_account(tenant, meta_app, "111", channel=channel)
    add_message(link, CLIENT, "Hola")
    agent = client_for(add_member(tenant, "agent@acme.test", Membership.Role.AGENT))

    response = agent.post(
        send_url(channel), {"account": str(link.id), "text": "Buenas tardes"}, format="json"
    )

    assert response.status_code == 201
    sent = response.data["data"]
    assert (sent["direction"], sent["text"]) == ("out", "Buenas tardes")
    assert Message.objects.filter(
        account=link.account, direction="out", text="Buenas tardes"
    ).exists()
    real_post.assert_not_called()


def test_a_text_with_fail_answers_the_delivery_error_and_saves_nothing(tenant, meta_app, real_post):
    link = add_account(tenant, meta_app, "111")
    add_message(link, CLIENT, "Hola")
    agent = client_for(add_member(tenant, "agent@acme.test", Membership.Role.AGENT))

    response = agent.post(
        send_url("whatsapp"), {"account": str(link.id), "text": "Esto falla #fail"}, format="json"
    )

    assert response.status_code == 502
    assert not Message.objects.filter(direction="out").exists()
    real_post.assert_not_called()


def test_calls_to_other_hosts_still_reach_the_real_post(real_post):
    requests.post("https://example.com/hook", json={"a": 1})

    real_post.assert_called_once_with("https://example.com/hook", data=None, json={"a": 1})


def test_it_installs_only_when_the_setting_is_on_and_debug_is_on(settings):
    config = apps.get_app_config("devtools")
    fake_meta.uninstall()
    clean = requests.post
    try:
        for meta_fake, debug, installed in [
            (False, True, False),
            (True, False, False),
            (True, True, True),
        ]:
            settings.META_FAKE = meta_fake
            settings.DEBUG = debug
            fake_meta.uninstall()
            config.ready()
            assert (requests.post is not clean) is installed, (meta_fake, debug)
    finally:
        fake_meta.uninstall()


def test_production_has_no_devtools_app_and_no_fake_setting():
    # Settings load once per process, so the production ones are loaded in a fresh one
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        "DJANGO_SECRET_KEY": "x" * 50,
        "ALLOWED_HOSTS": "api.example.com",
        "DATABASE_URL": "postgres://u:p@localhost:5432/db",
        "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        "WANPS_ENCRYPTION_KEY": "a-key-for-this-test",
        "META_FAKE": "true",
    }
    code = (
        "from django.conf import settings; "
        "print('apps.devtools' in settings.INSTALLED_APPS, hasattr(settings, 'META_FAKE'))"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=django_settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False"


def test_graph_calls_that_are_not_sends_reach_the_real_post(real_post):
    url = "https://graph.facebook.com/v23.0/123/something_else"

    requests.post(url, json={"a": 1})

    real_post.assert_called_once_with(url, data=None, json={"a": 1})


def test_it_warns_loudly_when_the_fake_is_installed(caplog):
    with caplog.at_level("WARNING", logger="apps.devtools.fake_meta"):
        fake_meta.install()
    fake_meta.uninstall()

    assert any("META_FAKE" in r.getMessage() and "NOT" in r.getMessage() for r in caplog.records)
