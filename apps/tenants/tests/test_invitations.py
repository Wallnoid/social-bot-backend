"""
Tests for inviting a person by email to a business with a role.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.mail.backends.smtp import EmailBackend
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from apps.tenants.models import Invitation, Membership, Tenant

User = get_user_model()

INVITATIONS_URL = "/api/v1/tenants/invitations/"
PASSWORD = "StrongPass123!"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


def member_client(tenant, role, email="member@acme.test"):
    """Return an API client logged in as a member of the tenant with that role."""
    user = User.objects.create_user(email=email, password=PASSWORD)
    Membership.objects.create(tenant=tenant, user=user, role=role)
    api = APIClient()
    response = api.post(
        "/api/v1/accounts/token/",
        {"email": email, "password": PASSWORD},
        format="json",
    )
    api.credentials(
        HTTP_AUTHORIZATION=f"Bearer {response.data['access']}",
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    return api


@pytest.fixture
def admin_client(tenant):
    return member_client(tenant, Membership.Role.ADMIN)


def invite(api, email="new@acme.test", role="agent"):
    return api.post(INVITATIONS_URL, {"email": email, "role": role}, format="json")


def test_admin_invites_a_person_with_a_role(admin_client):
    response = invite(admin_client, email="new@acme.test", role="supervisor")

    assert response.status_code == 201
    data = response.data["data"]
    assert data["email"] == "new@acme.test"
    assert data["role"] == "supervisor"
    assert "token" not in data
    expires_in = parse_datetime(data["expires_at"]) - timezone.now()
    assert timedelta(days=6, hours=23) < expires_in <= timedelta(days=7)


def test_invitation_email_has_the_link_and_the_expiry(admin_client, settings, mailoutbox):
    settings.FRONTEND_URL = "https://app.example.test"

    invite(admin_client, email="new@acme.test", role="supervisor")

    assert len(mailoutbox) == 1
    email = mailoutbox[0]
    assert email.to == ["new@acme.test"]
    token = Invitation.objects.get(email="new@acme.test").token
    assert f"https://app.example.test/accept-invitation?token={token}" in email.body
    assert "Acme Dental" in email.body
    assert "Supervisor" in email.body
    assert "válido por 7 días" in email.body


def test_invitation_expiry_comes_from_the_env_setting(admin_client, settings, mailoutbox):
    settings.INVITATION_TIMEOUT = 2 * 24 * 60 * 60

    response = invite(admin_client)

    expires_in = parse_datetime(response.data["data"]["expires_at"]) - timezone.now()
    assert timedelta(days=1, hours=23) < expires_in <= timedelta(days=2)
    assert "válido por 2 días" in mailoutbox[0].body


def test_agent_cannot_invite(tenant, mailoutbox):
    api = member_client(tenant, Membership.Role.AGENT)

    response = invite(api)

    assert response.status_code == 403
    assert not Invitation.objects.exists()
    assert mailoutbox == []


def test_supervisor_cannot_invite(tenant, mailoutbox):
    api = member_client(tenant, Membership.Role.SUPERVISOR)

    response = invite(api)

    assert response.status_code == 403
    assert not Invitation.objects.exists()
    assert mailoutbox == []


def test_cannot_invite_a_current_member(admin_client, tenant, mailoutbox):
    member = User.objects.create_user(email="agent@acme.test", password=PASSWORD)
    Membership.objects.create(tenant=tenant, user=member, role=Membership.Role.AGENT)

    response = invite(admin_client, email="AGENT@acme.test")

    assert response.status_code == 400
    assert "already a member" in str(response.data)
    assert not Invitation.objects.exists()
    assert mailoutbox == []


def test_cannot_invite_an_email_with_a_pending_invitation(admin_client, mailoutbox):
    invite(admin_client, email="new@acme.test")
    mailoutbox.clear()

    response = invite(admin_client, email="NEW@acme.test")

    assert response.status_code == 400
    assert "pending invitation" in str(response.data)
    assert Invitation.objects.count() == 1
    assert mailoutbox == []


def test_can_invite_again_after_the_previous_invitation_expired(admin_client, mailoutbox):
    invite(admin_client, email="new@acme.test")
    Invitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    mailoutbox.clear()

    response = invite(admin_client, email="new@acme.test")

    assert response.status_code == 201
    assert Invitation.objects.count() == 2
    assert mailoutbox[0].to == ["new@acme.test"]


def test_can_invite_a_member_of_another_business(admin_client, mailoutbox):
    other_tenant = Tenant.objects.create(name="Other Clinic")
    other_member = User.objects.create_user(email="other@acme.test", password=PASSWORD)
    Membership.objects.create(tenant=other_tenant, user=other_member, role=Membership.Role.ADMIN)

    response = invite(admin_client, email="other@acme.test")

    assert response.status_code == 201
    assert mailoutbox[0].to == ["other@acme.test"]


def test_can_invite_an_email_with_a_pending_invitation_in_another_business(
    admin_client, mailoutbox
):
    other_tenant = Tenant.objects.create(name="Other Clinic")
    other_admin = User.objects.create_user(email="boss@other.test", password=PASSWORD)
    Invitation.objects.create(
        tenant=other_tenant,
        email="new@acme.test",
        role=Membership.Role.AGENT,
        invited_by=other_admin,
    )

    response = invite(admin_client, email="new@acme.test")

    assert response.status_code == 201
    assert mailoutbox[0].to == ["new@acme.test"]


def test_invitation_is_not_saved_when_the_email_cannot_be_sent(admin_client):
    with mock.patch(
        "apps.tenants.views.send_invitation_email",
        side_effect=OSError("SMTP down"),
    ):
        response = invite(admin_client)

    assert response.status_code == 503
    assert "could not be sent" in response.data["message"]
    assert not Invitation.all_objects.exists()


@pytest.mark.parametrize(
    ("email", "role", "invalid_field"),
    [
        ("not-an-email", "agent", "email"),
        ("new@acme.test", "owner", "role"),
    ],
)
def test_invitation_rejects_an_invalid_email_or_role(
    admin_client, mailoutbox, email, role, invalid_field
):
    response = invite(admin_client, email=email, role=role)

    assert response.status_code == 400
    assert invalid_field in response.data["errors"]
    assert not Invitation.objects.exists()
    assert mailoutbox == []


def test_cannot_invite_a_member_stored_with_capitals(admin_client, tenant, mailoutbox):
    member = User.objects.create_user(email="agent@acme.test", password=PASSWORD)
    Membership.objects.create(tenant=tenant, user=member, role=Membership.Role.AGENT)
    User.objects.filter(pk=member.pk).update(email="Agent@acme.test")

    response = invite(admin_client, email="agent@acme.test")

    assert response.status_code == 400
    assert "already a member" in str(response.data)
    assert mailoutbox == []


def test_cannot_invite_a_pending_email_stored_with_capitals(admin_client, mailoutbox):
    invite(admin_client, email="new@acme.test")
    Invitation.objects.update(email="New@acme.test")
    mailoutbox.clear()

    response = invite(admin_client, email="new@acme.test")

    assert response.status_code == 400
    assert "pending invitation" in str(response.data)
    assert mailoutbox == []


def test_invitations_are_rate_limited_per_user(admin_client, mailoutbox):
    for number in range(10):
        response = invite(admin_client, email=f"new{number}@acme.test")
        assert response.status_code == 201

    response = invite(admin_client, email="one-too-many@acme.test")

    assert response.status_code == 429
    assert len(mailoutbox) == 10


def test_smtp_connection_has_a_timeout():
    assert EmailBackend().timeout == 10


def test_api_docs_describe_the_invitation_request():
    schema = SchemaGenerator().get_schema(request=None, public=True)

    operation = schema["paths"][INVITATIONS_URL]["post"]
    body = operation["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref": "#/components/schemas/InvitationRequest"}
