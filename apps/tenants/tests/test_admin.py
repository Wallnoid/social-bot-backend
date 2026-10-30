"""
Tests for creating businesses (tenants) from the Django admin.
"""

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.tenants.models import Membership, Tenant

User = get_user_model()


@pytest.fixture
def staff_client(client):
    """Return a Django test client logged in as a superuser."""
    superuser = User.objects.create_superuser(
        email="staff@example.com",
        password="staffpass123",
        first_name="Staff",
        last_name="User",
    )
    client.force_login(superuser)
    return client


@pytest.mark.django_db
def test_admin_creates_business_with_new_first_admin(staff_client):
    response = staff_client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "name": "Acme Dental",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )

    assert response.status_code == 302
    tenant = Tenant.objects.get(name="Acme Dental")
    owner = User.objects.get(email="owner@acme.test")
    assert (owner.first_name, owner.last_name) == ("Olivia", "Owner")
    assert not owner.has_usable_password()
    assert Membership.objects.get(tenant=tenant, user=owner).role == "admin"


@pytest.mark.django_db
def test_admin_creates_business_with_existing_user_reuses_account(staff_client):
    existing = User.objects.create_user(
        email="owner@acme.test",
        password="ownerpass123",
        first_name="Olivia",
        last_name="Owner",
    )

    response = staff_client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "name": "Acme Dental",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )

    assert response.status_code == 302
    assert User.objects.filter(email__iexact="owner@acme.test").count() == 1
    tenant = Tenant.objects.get(name="Acme Dental")
    assert Membership.objects.get(tenant=tenant, user=existing).role == "admin"


@pytest.mark.django_db
def test_admin_creates_business_with_industry_and_description(staff_client):
    response = staff_client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "name": "Acme Dental",
            "industry": "health",
            "description": "Clínica dental en Quito",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )

    assert response.status_code == 302
    tenant = Tenant.objects.get(name="Acme Dental")
    assert tenant.industry == "health"
    assert tenant.description == "Clínica dental en Quito"


@pytest.mark.django_db
def test_admin_rejects_inactive_existing_user_as_first_admin(staff_client):
    User.objects.create_user(
        email="owner@acme.test",
        password="ownerpass123",
        first_name="Olivia",
        last_name="Owner",
        is_active=False,
    )

    response = staff_client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "name": "Acme Dental",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )

    assert response.status_code == 200
    assert "admin_email" in response.context["adminform"].form.errors
    assert not Tenant.objects.filter(name="Acme Dental").exists()
    assert not Membership.objects.exists()


@pytest.mark.django_db
def test_admin_edit_form_shows_soft_delete_fields_last(staff_client):
    tenant = Tenant.objects.create(name="Acme Dental")

    response = staff_client.get(reverse("admin:tenants_tenant_change", args=[tenant.pk]))

    assert list(response.context["adminform"].form.fields) == [
        "name",
        "industry",
        "description",
        "is_deleted",
        "deleted_at",
    ]


@pytest.mark.django_db
def test_admin_sends_set_password_email_to_new_first_admin(
    staff_client, settings, mailoutbox
):
    settings.FRONTEND_URL = "https://app.example.test"

    staff_client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "name": "Acme Dental",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["owner@acme.test"]
    assert "https://app.example.test/set-password?uid=" in mailoutbox[0].body
    assert "&token=" in mailoutbox[0].body


@pytest.mark.django_db
def test_admin_sends_set_password_email_to_existing_user_without_password(
    staff_client, settings, mailoutbox
):
    settings.FRONTEND_URL = "https://app.example.test"
    User.objects.create_user(
        email="owner@acme.test", first_name="Olivia", last_name="Owner"
    )

    staff_client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "name": "Acme Dental",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["owner@acme.test"]
    assert "https://app.example.test/set-password?uid=" in mailoutbox[0].body


@pytest.mark.django_db
def test_admin_does_not_send_email_when_first_admin_already_has_password(
    staff_client, mailoutbox
):
    User.objects.create_user(
        email="owner@acme.test",
        password="ownerpass123",
        first_name="Olivia",
        last_name="Owner",
    )

    staff_client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "name": "Acme Dental",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )

    assert Membership.objects.filter(user__email="owner@acme.test").exists()
    assert mailoutbox == []


@pytest.mark.django_db
def test_set_password_email_states_how_many_days_the_link_lasts(
    staff_client, settings, mailoutbox
):
    settings.FRONTEND_URL = "https://app.example.test"
    settings.PASSWORD_RESET_TIMEOUT = 3 * 24 * 60 * 60

    staff_client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "name": "Acme Dental",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )

    assert "válido por 3 días" in mailoutbox[0].body


@pytest.mark.django_db
def test_admin_still_creates_business_when_email_cannot_be_sent(
    staff_client, mailoutbox
):
    with mock.patch(
        "apps.tenants.admin.send_set_password_email",
        side_effect=OSError("SMTP down"),
    ):
        response = staff_client.post(
            reverse("admin:tenants_tenant_add"),
            {
                "name": "Acme Dental",
                "admin_email": "owner@acme.test",
                "admin_first_name": "Olivia",
                "admin_last_name": "Owner",
            },
            follow=True,
        )

    assert response.status_code == 200
    assert Tenant.objects.filter(name="Acme Dental").exists()
    assert "could not be sent" in response.content.decode()


@pytest.mark.django_db
def test_set_password_email_states_hours_when_link_lasts_less_than_a_day(
    staff_client, settings, mailoutbox
):
    settings.PASSWORD_RESET_TIMEOUT = 12 * 60 * 60

    staff_client.post(
        reverse("admin:tenants_tenant_add"),
        {
            "name": "Acme Dental",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )

    assert "válido por 12 horas" in mailoutbox[0].body
