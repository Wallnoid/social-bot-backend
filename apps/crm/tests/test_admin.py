"""
The Social Bot team sees the contacts of the businesses in the Django admin, without changing them.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from wanps.messaging.models import App

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.crm.models import Contact
from apps.tenants.models import Tenant

User = get_user_model()


@pytest.fixture
def staff_client(client, db):
    superuser = User.objects.create_superuser(
        email="staff@example.com", password="staffpass123", first_name="Staff", last_name="User"
    )
    client.force_login(superuser)
    return client


@pytest.fixture
def contact(db):
    meta_app = App.objects.create(name="Social Bot", app_secret="s", verify_token="v")
    link = add_account(Tenant.objects.create(name="Acme Dental"), meta_app, "111")
    add_message(link, "593990000001", "Hola")
    return Contact.objects.get()


def test_the_team_sees_the_contacts_of_the_businesses(staff_client, contact):
    response = staff_client.get(reverse("admin:crm_contact_changelist"))

    assert response.status_code == 200
    assert "593990000001" in response.content.decode()
    assert "Acme Dental" in response.content.decode()


def test_the_team_cannot_add_change_or_delete_contacts(staff_client, contact):
    assert staff_client.get(reverse("admin:crm_contact_add")).status_code == 403
    assert (
        staff_client.post(
            reverse("admin:crm_contact_delete", args=[contact.pk]), {"post": "yes"}
        ).status_code
        == 403
    )
    page = staff_client.get(reverse("admin:crm_contact_change", args=[contact.pk])).content.decode()
    assert 'name="_save"' not in page
