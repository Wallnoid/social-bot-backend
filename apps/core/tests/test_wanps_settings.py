"""
The channel library (wanps-core) reads its switches from the Django settings, so each one that
the project wants to control from `.env` has to be wired in the settings.
"""

import json
import os
import subprocess
import sys

import pytest
from django.conf import settings as project_settings


def wanps_async_seen_by_the_library(value):
    """What wanps-core decides about Celery in a fresh process whose environment says `value`."""
    script = (
        "import django; django.setup();"
        "from wanps.messaging import conf;"
        "print(conf.get('WANPS_ASYNC', False))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_settings.BASE_DIR,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.local", "WANPS_ASYNC": value},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-800:]
    return result.stdout.strip()


@pytest.mark.parametrize(("value", "expected"), [("true", "True"), ("false", "False")])
def test_the_env_decides_whether_messages_are_processed_by_celery(value, expected):
    assert wanps_async_seen_by_the_library(value) == expected


def test_the_ai_of_the_platform_is_read_from_the_env():
    script = (
        "import django, json; django.setup();"
        "from django.conf import settings;"
        "print(json.dumps(settings.WANPS_AI, sort_keys=True))"
    )
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings.local",
        "WANPS_AI_PROVIDER": "gemini",
        "WANPS_AI_API_KEY": "key-from-the-env",
        "WANPS_AI_MODEL": "a-model",
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr[-800:]
    ai = json.loads(result.stdout)
    assert (ai["PROVIDER"], ai["API_KEY"], ai["MODEL"]) == ("gemini", "key-from-the-env", "a-model")
    assert ai["TIMEOUT"] > 0


@pytest.mark.django_db
def test_every_account_uses_the_handler_of_this_project():
    from wanps.messaging.dispatch import get_message_handler
    from wanps.messaging.models import Account, App

    from apps.channels.handler import ChannelAIHandler

    app = App.objects.create(name="Social Bot", app_secret="s", verify_token="v")
    account = Account.objects.create(
        app=app, channel="messenger", name="Page", external_id="1", access_token="t"
    )

    assert isinstance(get_message_handler(account), ChannelAIHandler)
