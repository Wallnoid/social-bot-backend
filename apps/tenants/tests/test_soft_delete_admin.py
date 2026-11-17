"""
Deleting businesses from the Django admin is a soft delete the team can undo: nothing is removed
from the database, the team and the history stay, and a deleted business can be found and restored.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.tenants.models import Invitation, Membership, Tenant
from apps.tenants.tests.helpers import PASSWORD, add_member

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
def businesses(db):
    dental = Tenant.objects.create(name="Acme Dental")
    gym = Tenant.objects.create(name="Acme Gym")
    for tenant in (dental, gym):
        add_member(tenant, f"admin@{tenant.name.split()[1].lower()}.test", Membership.Role.ADMIN)
    return dental, gym


def run_action(staff_client, action, *tenants, confirm=False, state=None):
    """An action from the list, filtered by `state` as the admin keeps it in the address."""
    data = {"action": action, "_selected_action": [str(tenant.pk) for tenant in tenants]}
    if confirm:
        data["post"] = "yes"
    url = reverse("admin:tenants_tenant_changelist") + (f"?state={state}" if state else "")
    return staff_client.post(url, data, follow=True)


def listed(staff_client, state=None):
    query = {"state": state} if state else {}
    page = staff_client.get(reverse("admin:tenants_tenant_changelist"), query)
    return sorted(tenant.name for tenant in page.context["cl"].result_list)


def test_deleting_several_businesses_in_bulk_is_a_soft_delete_that_keeps_their_data(
    staff_client, businesses
):
    dental, gym = businesses
    inviter = User.objects.create_user(email="boss@acme.test", password=PASSWORD)
    Invitation.objects.create(
        tenant=dental, email="new@acme.test", role=Membership.Role.AGENT, invited_by=inviter
    )

    run_action(staff_client, "delete_selected", dental, gym, confirm=True)

    assert Tenant.all_objects.filter(pk__in=[dental.pk, gym.pk], is_deleted=True).count() == 2
    assert Tenant.all_objects.get(pk=dental.pk).deleted_at is not None
    assert Membership.all_objects.filter(tenant__in=[dental, gym], is_deleted=False).count() == 2
    assert Invitation.all_objects.filter(tenant=dental, is_deleted=False).count() == 1


def test_a_deleted_business_is_found_with_the_filter_and_restored_with_its_action(
    staff_client, businesses
):
    dental, gym = businesses
    run_action(staff_client, "delete_selected", dental, confirm=True)

    shown, deleted, everything = (
        listed(staff_client),
        listed(staff_client, "deleted"),
        listed(staff_client, "all"),
    )
    run_action(staff_client, "restore", dental, state="deleted")

    assert shown == ["Acme Gym"]
    assert deleted == ["Acme Dental"]
    assert everything == ["Acme Dental", "Acme Gym"]
    restored = Tenant.objects.get(pk=dental.pk)
    assert (restored.is_deleted, restored.deleted_at) == (False, None)


def test_a_member_cannot_work_in_a_deleted_business_and_can_after_restoring_it(
    staff_client, businesses
):
    from apps.tenants.tests.helpers import log_in

    dental, _ = businesses
    api = log_in(APIClient(), "admin@dental.test")

    run_action(staff_client, "delete_selected", dental, confirm=True)
    deleted = api.get(CURRENT_URL, HTTP_X_TENANT_ID=str(dental.pk))
    run_action(staff_client, "restore", dental, state="deleted")
    restored = api.get(CURRENT_URL, HTTP_X_TENANT_ID=str(dental.pk))

    assert deleted.status_code == 404
    assert restored.status_code == 200
    assert restored.json()["data"]["name"] == "Acme Dental"


def test_a_business_with_connected_accounts_and_ai_usage_is_deleted_in_bulk(
    staff_client, businesses
):
    from datetime import date

    from wanps.messaging.models import App

    from apps.channels.models import AIUsage, ChannelAccount
    from apps.channels.tests.test_manage_accounts import add_account

    dental, _ = businesses
    app = App.objects.create(name="Social Bot", app_secret="secret", verify_token="verify")
    link = add_account(dental, app, "111")
    AIUsage.objects.create(tenant=dental, day=date(2026, 11, 1), model="gemini", paid_by="platform")

    run_action(staff_client, "delete_selected", dental, confirm=True)

    assert Tenant.all_objects.get(pk=dental.pk).is_deleted is True
    assert ChannelAccount.objects.filter(pk=link.pk).exists()
    assert AIUsage.objects.filter(tenant=dental).count() == 1


def test_deleting_again_a_deleted_business_keeps_its_deletion_date(staff_client, businesses):
    dental, _ = businesses
    run_action(staff_client, "delete_selected", dental, confirm=True)
    first = Tenant.all_objects.get(pk=dental.pk).deleted_at

    run_action(staff_client, "delete_selected", dental, confirm=True, state="all")

    assert Tenant.all_objects.get(pk=dental.pk).deleted_at == first


def test_restoring_a_business_changes_its_last_update(staff_client, businesses):
    dental, _ = businesses
    run_action(staff_client, "delete_selected", dental, confirm=True)
    deleted = Tenant.all_objects.get(pk=dental.pk).updated_at

    run_action(staff_client, "restore", dental, state="deleted")

    assert Tenant.objects.get(pk=dental.pk).updated_at > deleted


def test_the_page_of_a_business_shows_the_deletion_state_read_only(staff_client, businesses):
    dental, _ = businesses
    run_action(staff_client, "delete_selected", dental, confirm=True)

    page = staff_client.get(reverse("admin:tenants_tenant_change", args=[dental.pk]))

    fields = page.context["adminform"].form.fields
    assert "is_deleted" not in fields and "deleted_at" not in fields
    assert "Is deleted" in page.content.decode()


def test_suspending_or_reactivating_leaves_the_deleted_businesses_alone(staff_client, businesses):
    dental, gym = businesses
    run_action(staff_client, "delete_selected", dental, confirm=True)

    page = run_action(staff_client, "suspend", dental, gym, state="all")

    assert Tenant.all_objects.get(pk=dental.pk).suspended_at is None
    assert Tenant.objects.get(pk=gym.pk).suspended_at is not None
    assert "1 business(es) suspended." in page.content.decode()


def test_a_staff_member_who_can_only_view_businesses_cannot_restore_them(client, businesses):
    from django.contrib.auth.models import Permission

    dental, _ = businesses
    dental.delete()
    viewer = User.objects.create_user(email="viewer@socialbot.test", password=PASSWORD)
    viewer.is_staff = True
    viewer.save()
    viewer.user_permissions.add(Permission.objects.get(codename="view_tenant"))
    client.force_login(viewer)

    page = client.get(reverse("admin:tenants_tenant_changelist"), {"state": "deleted"})
    run_action(client, "restore", dental, state="deleted")

    assert "restore" not in [
        name for name, _ in page.context["action_form"].fields["action"].choices
    ]
    assert Tenant.all_objects.get(pk=dental.pk).is_deleted is True


def test_deleting_again_a_deleted_business_from_its_page_keeps_its_deletion_date(
    staff_client, businesses
):
    dental, _ = businesses
    dental.delete()
    first = Tenant.all_objects.get(pk=dental.pk).deleted_at

    staff_client.post(reverse("admin:tenants_tenant_delete", args=[dental.pk]), {"post": "yes"})

    assert Tenant.all_objects.get(pk=dental.pk).deleted_at == first
