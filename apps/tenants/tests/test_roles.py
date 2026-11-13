"""
Tests for what each role (agent, supervisor, admin) can do in a business.
"""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.views import APIView

from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

MEMBERS_URL = "/api/v1/tenants/members/"
SOME_ID = "11111111-1111-1111-1111-111111111111"

AGENT, SUPERVISOR, ADMIN = Membership.Role.AGENT, Membership.Role.SUPERVISOR, Membership.Role.ADMIN

# (method, url, roles that may call it). The roles left out must get 403; the ones listed
# must get past the permission (the body or the id may still be refused with 400 or 404)
TABLE = [
    ("get", "/api/v1/inbox/whatsapp/", [AGENT, SUPERVISOR, ADMIN]),
    ("post", "/api/v1/inbox/ws-ticket/", [AGENT, SUPERVISOR, ADMIN]),
    ("post", f"/api/v1/inbox/whatsapp/conversations/{SOME_ID}/unblock/", [SUPERVISOR, ADMIN]),
    ("get", "/api/v1/channels/accounts/", [AGENT, SUPERVISOR, ADMIN]),
    ("post", "/api/v1/channels/accounts/", [ADMIN]),
    ("patch", f"/api/v1/channels/accounts/{SOME_ID}/", [ADMIN]),
    ("delete", f"/api/v1/channels/accounts/{SOME_ID}/", [ADMIN]),
    ("get", MEMBERS_URL, [SUPERVISOR, ADMIN]),
    ("patch", f"{MEMBERS_URL}{SOME_ID}/", [ADMIN]),
    ("delete", f"{MEMBERS_URL}{SOME_ID}/", [ADMIN]),
    ("get", "/api/v1/tenants/invitations/", [ADMIN]),
    ("post", "/api/v1/tenants/invitations/", [ADMIN]),
    ("delete", f"/api/v1/tenants/invitations/{SOME_ID}/", [ADMIN]),
]


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


def client_with_role(tenant, role):
    return client_for(add_member(tenant, f"{role}@acme.test", role))


def test_a_supervisor_lists_the_members(tenant):
    add_member(tenant, "agent@acme.test", Membership.Role.AGENT, first_name="Ana", last_name="Vera")
    supervisor = client_with_role(tenant, Membership.Role.SUPERVISOR)

    response = supervisor.get(MEMBERS_URL)

    assert response.status_code == 200
    assert [member["email"] for member in response.data["data"]] == ["agent@acme.test"]


@pytest.mark.parametrize("role", Membership.Role.values)
@pytest.mark.parametrize(("method", "url", "allowed"), TABLE)
def test_each_role_can_only_reach_what_the_table_allows(tenant, role, method, url, allowed):
    api = client_with_role(tenant, role)

    response = getattr(api, method)(url, {}, format="json")

    if role in allowed:
        assert response.status_code != 403
    else:
        assert response.status_code == 403


# The index page that the accounts router adds by itself. It only lists the `users` route, and
# the default (signed-in users only) is what we want for it
ROUTER_INDEX = ("api/v1/accounts/", "api/v1/accounts/<drf_format_suffix:format>")


def api_views(patterns=None, prefix=""):
    """Every view class mounted under /api/v1/, with its route."""
    if patterns is None:
        patterns = get_resolver().url_patterns
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from api_views(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern) and route.startswith("api/v1/"):
            yield route, pattern.callback.cls


def test_every_api_view_declares_its_permissions():
    views = list(api_views())
    assert views

    # DRF's default (any signed-in user) must be a decision, never an oversight
    undeclared = [
        route
        for route, view in views
        if view.permission_classes is APIView.permission_classes
        and view.get_permissions is APIView.get_permissions
        and route not in ROUTER_INDEX
    ]

    assert undeclared == []
