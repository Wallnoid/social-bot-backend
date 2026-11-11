"""
Helpers shared by the tenants tests.
"""

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.tenants.models import Membership

User = get_user_model()

PASSWORD = "StrongPass123!"


def log_in(api, email, **headers):
    """Log the API client in through the real login endpoint and return it."""
    response = api.post(
        "/api/v1/accounts/token/",
        {"email": email, "password": PASSWORD},
        format="json",
    )
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}", **headers)
    return api


def add_member(tenant, email, role, **names):
    """Create a user who is a member of the tenant with that role."""
    user = User.objects.create_user(email=email, password=PASSWORD, **names)
    return Membership.objects.create(tenant=tenant, user=user, role=role)


def client_for(membership):
    """Return an API client logged in as that member, working in that business."""
    return log_in(APIClient(), membership.user.email, HTTP_X_TENANT_ID=str(membership.tenant_id))
