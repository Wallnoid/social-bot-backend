"""
Fixtures shared by the tests of the channels. A test file that needs another version of one of them
defines its own with the same name.
"""

from unittest import mock

import pytest
import requests
from wanps.messaging.models import App

from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def admin_client(tenant):
    return client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def inline_processing_and_platform_ai(settings, monkeypatch):
    """The bot answers inside the request, so a test can see it, with the AI of the platform."""
    settings.WANPS_ASYNC = False
    # Only the Gemini SDK is installed in the image, whatever the machine running the tests has
    monkeypatch.setattr(
        "apps.channels.serializers.provider_is_installed",
        lambda provider: provider == "gemini",
        raising=False,
    )
    settings.WANPS_AI = {"PROVIDER": "gemini", "API_KEY": "platform-key"}


@pytest.fixture
def no_real_meta_profiles():
    """Messenger and Instagram ask Meta for the name of the client: never for real in a test."""
    with mock.patch("requests.get", side_effect=requests.ConnectionError("no network in tests")):
        yield
