"""
Tests for the Social Bot team setting up the shared Meta App and the accounts of the businesses
from the Django admin.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from wanps.messaging.models import Account, App

from apps.channels.models import ChannelAccount, SharedMetaApp
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

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


def add_loose_account(app, external_id="111", **extra):
    """An account made in the admin of its channel, not yet linked to any business."""
    return Account.objects.create(
        app=app,
        channel="whatsapp",
        name="Front desk",
        external_id=external_id,
        business_id="998877",
        access_token="EAAG-secret-token",
        **extra,
    )


@pytest.fixture
def business(db):
    return Tenant.objects.create(name="Acme Dental")


def link_in_the_admin(client, business, account):
    return client.post(
        reverse("admin:channels_channelaccount_add"),
        {"tenant": str(business.pk), "account": str(account.pk)},
    )


def test_admin_links_an_account_to_a_business_and_the_business_sees_it(staff_client, business):
    app = App.objects.create(name="Acme's app", app_secret="s", verify_token="v")
    business.meta_app = app
    business.save()
    account = add_loose_account(app)

    response = link_in_the_admin(staff_client, business, account)

    assert response.status_code == 302
    assert ChannelAccount.objects.get().tenant == business
    member = client_for(add_member(business, "agent@acme.test", Membership.Role.AGENT))
    listed = member.get("/api/v1/channels/accounts/").data["data"]
    assert [item["external_id"] for item in listed] == ["111"]


def test_admin_refuses_an_account_of_another_meta_app_than_the_business(staff_client, business):
    business.meta_app = App.objects.create(name="Acme's app", app_secret="s", verify_token="v")
    business.save()
    account = add_loose_account(App.objects.create(name="Other", app_secret="s", verify_token="v"))

    response = link_in_the_admin(staff_client, business, account)

    assert response.status_code == 200
    assert "Meta App" in response.content.decode()
    assert not ChannelAccount.objects.exists()


def test_admin_does_not_offer_an_account_that_is_already_linked(staff_client, business):
    app = App.objects.create(name="Acme's app", app_secret="s", verify_token="v")
    business.meta_app = app
    business.save()
    taken = add_loose_account(app, "111")
    free = add_loose_account(app, "222")
    ChannelAccount.objects.create(tenant=business, account=taken)

    page = staff_client.get(reverse("admin:channels_channelaccount_add"))

    offered = page.context["adminform"].form.fields["account"].queryset
    assert list(offered) == [free]


def test_admin_disconnects_an_account_like_the_api_does(staff_client, business):
    app = App.objects.create(name="Acme's app", app_secret="s", verify_token="v")
    account = add_loose_account(app, is_active=True)
    link = ChannelAccount.objects.create(tenant=business, account=account)

    response = staff_client.post(
        reverse("admin:channels_channelaccount_changelist"),
        {"action": "disconnect", "_selected_action": [str(link.pk)]},
        follow=True,
    )

    assert response.status_code == 200
    account.refresh_from_db()
    assert account.is_active is False
    assert account.access_token == ""
    assert account.external_id == f"111#disconnected-{account.pk}"
    assert not ChannelAccount.objects.filter(pk=link.pk).exists()
    assert ChannelAccount.all_objects.get(pk=link.pk).is_deleted is True


def test_admin_cannot_delete_a_link_for_good(staff_client, business):
    app = App.objects.create(name="Acme's app", app_secret="s", verify_token="v")
    link = ChannelAccount.objects.create(tenant=business, account=add_loose_account(app))

    response = staff_client.post(
        reverse("admin:channels_channelaccount_delete", args=[link.pk]), {"post": "yes"}
    )

    assert response.status_code == 403
    assert ChannelAccount.objects.filter(pk=link.pk).exists()
