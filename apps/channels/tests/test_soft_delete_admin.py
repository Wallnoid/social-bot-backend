"""
Deleting the shared Meta App from the Django admin is a soft delete too.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from wanps.messaging.models import App

from apps.channels.models import SharedMetaApp

User = get_user_model()


@pytest.fixture
def staff_client(client, db):
    client.force_login(
        User.objects.create_superuser(
            email="staff@example.com", password="staffpass123", first_name="S", last_name="U"
        )
    )
    return client


def test_the_shared_meta_app_is_deleted_in_bulk_with_a_soft_delete(staff_client):
    app = App.objects.create(name="Social Bot", app_secret="secret", verify_token="verify")
    shared = SharedMetaApp.objects.create(app=app)

    staff_client.post(
        reverse("admin:channels_sharedmetaapp_changelist"),
        {"action": "delete_selected", "_selected_action": [str(shared.pk)], "post": "yes"},
        follow=True,
    )

    row = SharedMetaApp.all_objects.get(pk=shared.pk)
    assert row.is_deleted is True and row.deleted_at is not None
    assert App.objects.filter(pk=app.pk).exists()
