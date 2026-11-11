"""
Tests for the tenants models.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.tenants.models import Membership, Tenant

User = get_user_model()


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def member():
    return User.objects.create_user(
        email="agent@acme.test", first_name="Ana", last_name="Agent"
    )


@pytest.mark.django_db
def test_membership_is_unique_per_user_and_business(tenant, member):
    Membership.objects.create(tenant=tenant, user=member, role=Membership.Role.ADMIN)

    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(tenant=tenant, user=member, role=Membership.Role.AGENT)


@pytest.mark.django_db
def test_membership_can_be_added_again_after_soft_delete(tenant, member):
    first = Membership.objects.create(
        tenant=tenant, user=member, role=Membership.Role.AGENT
    )
    first.soft_delete()

    second = Membership.objects.create(
        tenant=tenant, user=member, role=Membership.Role.SUPERVISOR
    )

    assert list(Membership.objects.filter(tenant=tenant, user=member)) == [second]
    assert Membership.all_objects.filter(tenant=tenant, user=member).count() == 2
