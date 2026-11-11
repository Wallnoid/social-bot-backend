"""
Tests for creating businesses (tenants) from the Django admin.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from wanps.messaging.models import App

from apps.tenants.models import Invitation, Membership, Tenant

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
            "description": "Dental clinic in Quito",
            "admin_email": "owner@acme.test",
            "admin_first_name": "Olivia",
            "admin_last_name": "Owner",
        },
    )

    assert response.status_code == 302
    tenant = Tenant.objects.get(name="Acme Dental")
    assert tenant.industry == "health"
    assert tenant.description == "Dental clinic in Quito"


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
        "meta_app",
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


@pytest.mark.django_db
def test_admin_sets_the_business_own_meta_app(staff_client):
    tenant = Tenant.objects.create(name="Acme Dental")
    app = App.objects.create(name="Acme's own app", app_secret="s", verify_token="v")

    response = staff_client.post(
        reverse("admin:tenants_tenant_change", args=[tenant.pk]),
        {
            "name": "Acme Dental",
            "industry": "",
            "description": "",
            "meta_app": str(app.pk),
            "memberships-TOTAL_FORMS": "0",
            "memberships-INITIAL_FORMS": "0",
            "invitations-TOTAL_FORMS": "0",
            "invitations-INITIAL_FORMS": "0",
        },
    )

    assert response.status_code == 302
    tenant.refresh_from_db()
    assert tenant.meta_app == app


def edit_business(client, tenant, new=(), cancel=()):
    """Save the business edit page, inviting `new` (email, role) and cancelling `cancel`."""
    pending = list(Invitation.pending().filter(tenant=tenant).order_by("created_at"))
    data = {
        "name": tenant.name,
        "industry": tenant.industry,
        "description": tenant.description,
        "memberships-TOTAL_FORMS": "0",
        "memberships-INITIAL_FORMS": "0",
        "invitations-TOTAL_FORMS": str(len(pending) + len(new)),
        "invitations-INITIAL_FORMS": str(len(pending)),
    }
    for index, invitation in enumerate(pending):
        data[f"invitations-{index}-id"] = str(invitation.pk)
        data[f"invitations-{index}-tenant"] = str(tenant.pk)
        if invitation in cancel:
            data[f"invitations-{index}-DELETE"] = "on"
    for index, (email, role) in enumerate(new, start=len(pending)):
        data[f"invitations-{index}-tenant"] = str(tenant.pk)
        data[f"invitations-{index}-email"] = email
        data[f"invitations-{index}-role"] = role
    return client.post(reverse("admin:tenants_tenant_change", args=[tenant.pk]), data, follow=True)


@pytest.fixture
def business():
    return Tenant.objects.create(name="Acme Dental")


def invite(tenant, email, **fields):
    return Invitation.objects.create(
        tenant=tenant, email=email, role="agent", invited_by=User.objects.get(), **fields
    )


@pytest.mark.django_db
def test_admin_invites_a_person_to_an_existing_business(staff_client, business, mailoutbox):
    response = edit_business(staff_client, business, new=[("New.Agent@Acme.test", "agent")])

    assert response.status_code == 200
    invitation = Invitation.objects.get(tenant=business)
    assert (invitation.email, invitation.role) == ("new.agent@acme.test", "agent")
    assert invitation.invited_by.email == "staff@example.com"
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["new.agent@acme.test"]
    assert invitation.token in mailoutbox[0].body


@pytest.mark.django_db
def test_admin_rejects_inviting_a_member(staff_client, business, mailoutbox):
    member = User.objects.create_user(email="agent@acme.test", password="x-pass-123")
    Membership.objects.create(tenant=business, user=member, role="agent")

    response = edit_business(staff_client, business, new=[("AGENT@acme.test", "admin")])

    assert "already a member of this business" in response.content.decode()
    assert not Invitation.objects.exists()
    assert mailoutbox == []


@pytest.mark.django_db
def test_admin_rejects_a_second_pending_invitation(staff_client, business, mailoutbox):
    invite(business, "agent@acme.test")

    response = edit_business(staff_client, business, new=[("agent@acme.test", "agent")])

    assert "already has a pending invitation" in response.content.decode()
    assert Invitation.objects.count() == 1
    assert mailoutbox == []


@pytest.mark.django_db
def test_admin_rejects_inviting_a_deactivated_user(staff_client, business, mailoutbox):
    User.objects.create_user(email="gone@acme.test", is_active=False)

    response = edit_business(staff_client, business, new=[("gone@acme.test", "agent")])

    assert "deactivated" in response.content.decode()
    assert not Invitation.objects.exists()
    assert mailoutbox == []


@pytest.mark.django_db
def test_admin_rejects_the_same_email_twice_in_one_save(staff_client, business, mailoutbox):
    response = edit_business(
        staff_client,
        business,
        new=[("agent@acme.test", "agent"), ("Agent@acme.test", "admin")],
    )

    assert "invited more than once" in response.content.decode()
    assert not Invitation.objects.exists()
    assert mailoutbox == []


@pytest.mark.django_db
def test_admin_cancels_a_pending_invitation(staff_client, business):
    invitation = invite(business, "agent@acme.test")

    edit_business(staff_client, business, cancel=[invitation])

    assert not Invitation.pending().exists()
    assert Invitation.all_objects.get(pk=invitation.pk).is_deleted


@pytest.mark.django_db
def test_admin_cancels_the_invitation_when_its_email_cannot_be_sent(staff_client, business):
    with mock.patch("apps.tenants.admin.send_invitation_email", side_effect=OSError("SMTP down")):
        response = edit_business(staff_client, business, new=[("agent@acme.test", "agent")])

    assert "could not be sent" in response.content.decode()
    assert not Invitation.pending().exists()


@pytest.mark.django_db
def test_admin_lists_only_pending_invitations(staff_client, business):
    invite(business, "pending@acme.test")
    invite(business, "expired@acme.test", expires_at=timezone.now() - timedelta(minutes=1))

    response = staff_client.get(reverse("admin:tenants_tenant_change", args=[business.pk]))

    page = response.content.decode()
    assert "pending@acme.test" in page
    assert "expired@acme.test" not in page
