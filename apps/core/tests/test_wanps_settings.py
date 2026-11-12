"""
The channel library (wanps-core) reads its switches from the Django settings, so each one that
the project wants to control from `.env` has to be wired in the settings.
"""

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
