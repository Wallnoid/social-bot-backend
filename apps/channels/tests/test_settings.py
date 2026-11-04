"""
Tests for the settings wanps-core needs.
"""

import os
import subprocess
import sys

from django.conf import settings


def test_the_app_does_not_start_with_an_empty_encryption_key():
    # Settings load once per process, so they are loaded again in a fresh one
    env = {
        **os.environ,
        "WANPS_ENCRYPTION_KEY": "",
        "DJANGO_SETTINGS_MODULE": "config.settings.local",
    }

    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode != 0
    assert "WANPS_ENCRYPTION_KEY" in result.stderr
