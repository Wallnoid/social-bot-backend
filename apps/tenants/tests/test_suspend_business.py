"""
Suspending and reactivating a business from the Django admin: its members cannot work in it and
its bot stays silent, and everything comes back when it is reactivated.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for, log_in

User = get_user_model()
CURRENT_URL = "/api/v1/tenants/current/"


@pytest.fixture
def staff_client(client, db):
    client.force_login(
        User.objects.create_superuser(
            email="staff@example.com", password="staffpass123", first_name="S", last_name="U"
        )
    )
    return client


@pytest.fixture
def dental(db):
    return Tenant.objects.create(name="Acme Dental")


def run_action(staff_client, action, *tenants):
    return staff_client.post(
        reverse("admin:tenants_tenant_changelist"),
        {"action": action, "_selected_action": [str(tenant.pk) for tenant in tenants]},
        follow=True,
    )


def test_the_admin_suspends_and_reactivates_a_business_with_its_actions(staff_client, dental):
    run_action(staff_client, "suspend", dental)
    dental.refresh_from_db()
    assert dental.suspended_at is not None

    run_action(staff_client, "reactivate", dental)
    dental.refresh_from_db()
    assert dental.suspended_at is None


def suspend(tenant):
    from django.utils import timezone

    Tenant.objects.filter(pk=tenant.pk).update(suspended_at=timezone.now())


def test_a_member_of_a_suspended_business_is_refused_with_business_suspended(dental):
    api = client_for(add_member(dental, "ana@acme.test", Membership.Role.ADMIN))
    suspend(dental)

    response = api.get(CURRENT_URL, HTTP_X_TENANT_ID=str(dental.pk))

    assert response.status_code == 403
    assert response.json()["code"] == "business_suspended"


def test_without_header_an_only_business_that_is_suspended_is_refused_too(dental):
    log_in(
        api := APIClient(), add_member(dental, "ana@acme.test", Membership.Role.AGENT).user.email
    )
    suspend(dental)

    response = api.get(CURRENT_URL)

    assert response.status_code == 403
    assert response.json()["code"] == "business_suspended"


def test_the_other_businesses_of_the_same_user_keep_working(dental):
    gym = Tenant.objects.create(name="Acme Gym")
    member = add_member(dental, "ana@acme.test", Membership.Role.ADMIN)
    Membership.objects.create(tenant=gym, user=member.user, role=Membership.Role.AGENT)
    log_in(api := APIClient(), member.user.email)
    suspend(dental)

    response = api.get(CURRENT_URL, HTTP_X_TENANT_ID=str(gym.pk))

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Acme Gym"


def test_the_profile_lists_the_suspended_business_marked_as_suspended(dental):
    gym = Tenant.objects.create(name="Acme Gym")
    member = add_member(dental, "ana@acme.test", Membership.Role.ADMIN)
    Membership.objects.create(tenant=gym, user=member.user, role=Membership.Role.AGENT)
    log_in(api := APIClient(), member.user.email)
    suspend(dental)

    tenants = api.get("/api/v1/accounts/users/me/").json()["data"]["tenants"]

    assert {tenant["name"]: tenant["suspended"] for tenant in tenants} == {
        "Acme Dental": True,
        "Acme Gym": False,
    }


def test_an_invitation_to_a_suspended_business_cannot_be_looked_up_or_accepted(dental):
    from apps.tenants.models import Invitation
    from apps.tenants.tests.helpers import PASSWORD

    inviter = User.objects.create_user(email="boss@acme.test", password=PASSWORD)
    invitation = Invitation.objects.create(
        tenant=dental, email="new@acme.test", role=Membership.Role.AGENT, invited_by=inviter
    )
    suspend(dental)
    api = APIClient()

    lookup = api.post(
        "/api/v1/tenants/invitations/lookup/", {"token": invitation.token}, format="json"
    )
    accept = api.post(
        "/api/v1/tenants/invitations/accept/",
        {
            "token": invitation.token,
            "first_name": "Ana",
            "last_name": "Vera",
            "new_password": PASSWORD,
            "new_password_confirm": PASSWORD,
        },
        format="json",
    )

    assert lookup.status_code == 400
    assert lookup.data["error_codes"]["token"] == ["business_suspended"]
    assert accept.status_code == 400
    assert accept.data["error_codes"]["token"] == ["business_suspended"]
    assert not Membership.objects.filter(user__email="new@acme.test").exists()


def test_the_page_of_a_business_shows_since_when_it_is_suspended(staff_client, dental):
    suspend(dental)

    page = staff_client.get(reverse("admin:tenants_tenant_change", args=[dental.pk]))

    assert "suspended_at" not in page.context["adminform"].form.fields  # it is not editable
    assert "Suspended at" in page.content.decode()
