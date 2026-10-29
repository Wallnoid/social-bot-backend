"""
Tests for creating businesses (tenants) from the Django admin.
"""

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
