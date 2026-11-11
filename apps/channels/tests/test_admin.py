"""
Tests for setting up the shared Meta App from the Django admin.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from wanps.messaging.models import App

from apps.channels.models import SharedMetaApp

User = get_user_model()


@pytest.fixture
def staff_client(client, db):
    superuser = User.objects.create_superuser(
        email="staff@example.com", password="staffpass123", first_name="Staff", last_name="User"
    )
    client.force_login(superuser)
    return client


def test_admin_marks_the_shared_meta_app(staff_client):
    app = App.objects.create(name="Social Bot", app_secret="s", verify_token="v")

    response = staff_client.post(reverse("admin:channels_sharedmetaapp_add"), {"app": str(app.pk)})

    assert response.status_code == 302
    assert SharedMetaApp.objects.get().app == app


def test_admin_marks_again_a_shared_meta_app_that_was_deleted(staff_client):
    app = App.objects.create(name="Social Bot", app_secret="s", verify_token="v")
    SharedMetaApp.objects.create(app=app).delete()

    response = staff_client.post(reverse("admin:channels_sharedmetaapp_add"), {"app": str(app.pk)})

    assert response.status_code == 302
    assert SharedMetaApp.objects.get().app == app
