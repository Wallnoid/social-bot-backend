"""
Tests for accepting an invitation to join a business.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.tenants.models import Invitation, Membership, Tenant

User = get_user_model()

LOOKUP_URL = "/api/v1/tenants/invitations/lookup/"
ACCEPT_URL = "/api/v1/tenants/invitations/accept/"
PASSWORD = "StrongPass123!"
INVALID_LINK_MESSAGE = "The invitation is invalid or has expired."


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Throttle counters live in the cache; start every test from zero."""
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def invitation(tenant):
    inviter = User.objects.create_user(email="boss@acme.test", password=PASSWORD)
    return Invitation.objects.create(
        tenant=tenant,
        email="new@acme.test",
        role=Membership.Role.SUPERVISOR,
        invited_by=inviter,
    )


def test_lookup_shows_the_invitation_to_a_new_person(api, invitation):
    response = api.post(LOOKUP_URL, {"token": invitation.token}, format="json")

    assert response.status_code == 200
    assert response.data["data"] == {
        "tenant": "Acme Dental",
        "email": "new@acme.test",
        "role": "supervisor",
        "next_step": "create_account",
    }


def test_lookup_asks_an_existing_user_to_log_in(api, invitation):
    User.objects.create_user(email="new@acme.test", password=PASSWORD)

    response = api.post(LOOKUP_URL, {"token": invitation.token}, format="json")

    assert response.data["data"]["next_step"] == "log_in"


def test_lookup_asks_a_user_without_password_to_create_it(api, invitation):
    User.objects.create_user(email="new@acme.test")

    response = api.post(LOOKUP_URL, {"token": invitation.token}, format="json")

    assert response.data["data"]["next_step"] == "create_password"


def expire(invitation):
    Invitation.objects.filter(pk=invitation.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )


def use(invitation):
    invitation.soft_delete()


def change_token(invitation):
    Invitation.objects.filter(pk=invitation.pk).update(token="another-token")


def delete_business(invitation):
    invitation.tenant.soft_delete()


def deactivate_invited_user(invitation):
    User.objects.create_user(email=invitation.email, password=PASSWORD, is_active=False)


INVALID_LINKS = [expire, use, change_token, delete_business, deactivate_invited_user]


@pytest.mark.parametrize("invalidate", INVALID_LINKS)
def test_lookup_rejects_an_invalid_link(api, invitation, invalidate):
    token = invitation.token
    invalidate(invitation)

    response = api.post(LOOKUP_URL, {"token": token}, format="json")

    assert response.status_code == 400
    assert response.data["errors"]["token"] == [INVALID_LINK_MESSAGE]


def test_new_person_joins_with_the_invited_role_and_can_log_in(api, invitation, tenant):
    response = api.post(
        ACCEPT_URL,
        {
            "token": invitation.token,
            "first_name": "Ana",
            "last_name": "Vera",
            "new_password": PASSWORD,
            "new_password_confirm": PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["data"] == {"tenant": "Acme Dental", "role": "supervisor"}
    user = User.objects.get(email="new@acme.test")
    assert (user.first_name, user.last_name) == ("Ana", "Vera")
    assert Membership.objects.get(tenant=tenant, user=user).role == "supervisor"
    login = api.post(
        "/api/v1/accounts/token/",
        {"email": "new@acme.test", "password": PASSWORD},
        format="json",
    )
    assert login.status_code == 200


@pytest.mark.parametrize(
    ("change", "invalid_field"),
    [
        ({"first_name": ""}, "first_name"),
        ({"last_name": ""}, "last_name"),
        ({"new_password_confirm": "OtherPass123!"}, "new_password_confirm"),
        ({"new_password": "12345", "new_password_confirm": "12345"}, "new_password"),
    ],
)
def test_new_person_needs_a_name_and_a_valid_password(api, invitation, change, invalid_field):
    payload = {
        "token": invitation.token,
        "first_name": "Ana",
        "last_name": "Vera",
        "new_password": PASSWORD,
        "new_password_confirm": PASSWORD,
    }

    response = api.post(ACCEPT_URL, {**payload, **change}, format="json")

    assert response.status_code == 400
    assert invalid_field in response.data["errors"]
    assert not User.objects.filter(email="new@acme.test").exists()
    assert Invitation.objects.filter(pk=invitation.pk).exists()


def test_new_person_cannot_omit_the_name_or_the_password(api, invitation):
    response = api.post(ACCEPT_URL, {"token": invitation.token}, format="json")

    assert response.status_code == 400
    assert {"first_name", "last_name", "new_password"} <= set(response.data["errors"])
    assert not User.objects.filter(email="new@acme.test").exists()


def log_in(api, email, **headers):
    response = api.post(
        "/api/v1/accounts/token/",
        {"email": email, "password": PASSWORD},
        format="json",
    )
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}", **headers)


def test_existing_user_logged_in_with_the_invited_email_joins(api, invitation, tenant):
    user = User.objects.create_user(
        email="new@acme.test", password=PASSWORD, first_name="Ana", last_name="Vera"
    )
    log_in(api, "new@acme.test")

    response = api.post(
        ACCEPT_URL,
        {
            "token": invitation.token,
            "first_name": "Other",
            "new_password": "OtherPass123!",
            "new_password_confirm": "OtherPass123!",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["data"] == {"tenant": "Acme Dental", "role": "supervisor"}
    assert Membership.objects.get(tenant=tenant, user=user).role == "supervisor"
    assert User.objects.filter(email__iexact="new@acme.test").count() == 1
    user.refresh_from_db()
    assert user.first_name == "Ana"
    assert user.check_password(PASSWORD)


def test_existing_user_must_be_logged_in(api, invitation, tenant):
    User.objects.create_user(email="new@acme.test", password=PASSWORD)

    response = api.post(ACCEPT_URL, {"token": invitation.token}, format="json")

    assert response.status_code == 401
    assert not Membership.objects.filter(tenant=tenant).exists()
    assert Invitation.objects.filter(pk=invitation.pk).exists()


@pytest.mark.parametrize("invited_has_an_account", [True, False])
def test_logged_in_with_another_account_is_rejected(
    api, invitation, tenant, invited_has_an_account
):
    if invited_has_an_account:
        User.objects.create_user(email="new@acme.test", password=PASSWORD)
    User.objects.create_user(email="someone-else@acme.test", password=PASSWORD)
    log_in(api, "someone-else@acme.test")

    response = api.post(
        ACCEPT_URL,
        {
            "token": invitation.token,
            "first_name": "Ana",
            "last_name": "Vera",
            "new_password": PASSWORD,
            "new_password_confirm": PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 403
    assert not Membership.objects.filter(tenant=tenant).exists()
    assert Invitation.objects.filter(pk=invitation.pk).exists()


def test_user_without_password_creates_it_and_keeps_their_name(api, invitation, tenant):
    user = User.objects.create_user(email="new@acme.test", first_name="Ana", last_name="Vera")

    response = api.post(
        ACCEPT_URL,
        {
            "token": invitation.token,
            "first_name": "Other",
            "last_name": "Name",
            "new_password": PASSWORD,
            "new_password_confirm": PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 201
    assert Membership.objects.get(tenant=tenant, user=user).role == "supervisor"
    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Ana", "Vera")
    assert user.check_password(PASSWORD)


@pytest.mark.parametrize("invalidate", INVALID_LINKS)
def test_accept_rejects_an_invalid_link_with_the_same_message(api, invitation, tenant, invalidate):
    token = invitation.token
    invalidate(invitation)

    response = api.post(
        ACCEPT_URL,
        {
            "token": token,
            "first_name": "Ana",
            "last_name": "Vera",
            "new_password": PASSWORD,
            "new_password_confirm": PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["errors"]["token"] == [INVALID_LINK_MESSAGE]
    assert not Membership.all_objects.filter(tenant=tenant).exists()


def test_accepted_invitation_cannot_be_used_twice(api, invitation, tenant):
    payload = {
        "token": invitation.token,
        "first_name": "Ana",
        "last_name": "Vera",
        "new_password": PASSWORD,
        "new_password_confirm": PASSWORD,
    }
    api.post(ACCEPT_URL, payload, format="json")

    response = api.post(ACCEPT_URL, payload, format="json")

    assert response.status_code == 400
    assert response.data["errors"]["token"] == [INVALID_LINK_MESSAGE]
    assert Membership.objects.filter(tenant=tenant).count() == 1


def test_accepting_cancels_other_invitations_of_that_email_in_that_business(
    api, invitation, tenant
):
    duplicate = Invitation.objects.create(
        tenant=tenant,
        email="NEW@acme.test",
        role=Membership.Role.ADMIN,
        invited_by=invitation.invited_by,
    )
    other_business = Invitation.objects.create(
        tenant=Tenant.objects.create(name="Other Clinic"),
        email="new@acme.test",
        role=Membership.Role.AGENT,
        invited_by=invitation.invited_by,
    )
    api.post(
        ACCEPT_URL,
        {
            "token": invitation.token,
            "first_name": "Ana",
            "last_name": "Vera",
            "new_password": PASSWORD,
            "new_password_confirm": PASSWORD,
        },
        format="json",
    )

    duplicate_lookup = api.post(LOOKUP_URL, {"token": duplicate.token}, format="json")
    other_lookup = api.post(LOOKUP_URL, {"token": other_business.token}, format="json")

    assert duplicate_lookup.status_code == 400
    assert other_lookup.status_code == 200


def test_removed_member_can_be_invited_again_after_accepting(api, invitation, tenant):
    Membership.objects.create(tenant=tenant, user=invitation.invited_by, role=Membership.Role.ADMIN)
    api.post(
        ACCEPT_URL,
        {
            "token": invitation.token,
            "first_name": "Ana",
            "last_name": "Vera",
            "new_password": PASSWORD,
            "new_password_confirm": PASSWORD,
        },
        format="json",
    )
    Membership.objects.get(tenant=tenant, user__email="new@acme.test").soft_delete()
    log_in(api, "boss@acme.test", HTTP_X_TENANT_ID=str(tenant.id))

    response = api.post(
        "/api/v1/tenants/invitations/",
        {"email": "new@acme.test", "role": "agent"},
        format="json",
    )

    assert response.status_code == 201


def test_accepting_when_already_a_member_is_rejected(api, invitation, tenant):
    user = User.objects.create_user(email="new@acme.test", password=PASSWORD)
    Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.AGENT)
    log_in(api, "new@acme.test")

    response = api.post(ACCEPT_URL, {"token": invitation.token}, format="json")

    assert response.status_code == 400
    assert "already a member" in str(response.data["errors"])
    assert Membership.objects.get(tenant=tenant, user=user).role == "agent"


def test_accept_is_rate_limited_when_logged_in(api, invitation):
    User.objects.create_user(email="new@acme.test", password=PASSWORD)
    log_in(api, "new@acme.test")
    for _ in range(10):
        response = api.post(ACCEPT_URL, {"token": "unknown"}, format="json")
        assert response.status_code == 400

    response = api.post(ACCEPT_URL, {"token": "unknown"}, format="json")

    assert response.status_code == 429


def test_invalid_link_with_blank_fields_gets_the_link_message(api, invitation):
    token = invitation.token
    expire(invitation)

    response = api.post(
        ACCEPT_URL,
        {
            "token": token,
            "first_name": "",
            "last_name": "",
            "new_password": "",
            "new_password_confirm": "",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["errors"] == {"token": [INVALID_LINK_MESSAGE]}


def test_logged_in_user_can_send_blank_fields(api, invitation, tenant):
    user = User.objects.create_user(email="new@acme.test", password=PASSWORD)
    log_in(api, "new@acme.test")

    response = api.post(
        ACCEPT_URL,
        {
            "token": invitation.token,
            "first_name": "",
            "last_name": "",
            "new_password": "",
            "new_password_confirm": "",
        },
        format="json",
    )

    assert response.status_code == 201
    assert Membership.objects.filter(tenant=tenant, user=user).exists()


def test_lookup_ignores_a_stale_session_token(api, invitation):
    api.credentials(HTTP_AUTHORIZATION="Bearer expired-or-invalid")

    response = api.post(LOOKUP_URL, {"token": invitation.token}, format="json")

    assert response.status_code == 200


@pytest.mark.parametrize("url", [LOOKUP_URL, ACCEPT_URL])
def test_lookup_and_accept_are_rate_limited(api, db, url):
    for _ in range(5):
        response = api.post(url, {"token": "unknown"}, format="json")
        assert response.status_code == 400

    response = api.post(url, {"token": "unknown"}, format="json")

    assert response.status_code == 429
