"""
Tests for the static files (the styles of the Django admin) served by the app itself.
"""

import os
import subprocess
import sys

from django.conf import settings as project_settings
from django.core.management import call_command


def test_the_app_serves_the_styles_of_the_admin_as_in_production(client, settings, tmp_path):
    # As in production: no debug mode, and the files collected in the folder for them
    settings.DEBUG = False
    settings.STATIC_ROOT = tmp_path
    call_command("collectstatic", interactive=False, verbosity=0)

    response = client.get("/static/admin/css/base.css")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/css")


def test_a_file_that_was_not_collected_is_not_found(client, settings, tmp_path):
    settings.DEBUG = False
    settings.STATIC_ROOT = tmp_path

    assert client.get("/static/admin/css/base.css").status_code == 404


def test_production_gives_the_static_files_a_hash_and_keeps_the_default_storage(tmp_path):
    # Settings load once per process, so production settings are read in a fresh one
    script = (
        "import django, sys; django.setup();"
        "from django.conf import settings;"
        "from django.core.management import call_command;"
        "from django.test.utils import override_settings;"
        "from django.contrib.staticfiles.storage import staticfiles_storage as files;"
        "ctx = override_settings(STATIC_ROOT=sys.argv[1]); ctx.enable();"
        "call_command('collectstatic', interactive=False, verbosity=0);"
        "print(settings.STORAGES['default']['BACKEND'], files.url('admin/css/base.css'))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=project_settings.BASE_DIR,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.production"},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr[-800:]
    storage, url = result.stdout.split()
    assert storage == "django.core.files.storage.FileSystemStorage"
    # The name carries a hash of the content, so a new version is never served from the cache
    assert url.startswith("/static/admin/css/base.") and url != "/static/admin/css/base.css"
