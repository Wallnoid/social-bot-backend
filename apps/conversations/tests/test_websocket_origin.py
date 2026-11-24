"""
The origin of the permanent connection of the inbox: only the pages of the frontend (the origins
CORS allows) can open it from a browser.
"""

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from asgiref.testing import ApplicationCommunicator

from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for
from config.asgi import application

# The connection closes its old database connections when it is done, as in test_realtime.py
pytestmark = pytest.mark.django_db(transaction=True)

TICKET_URL = "/api/v1/inbox/ws-ticket/"
FRONTEND = "https://app.example.com"
FOREIGN = "https://evil.example.com"


@pytest.fixture
def member(db):
    tenant = Tenant.objects.create(name="Acme Dental")
    return client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))


@pytest.fixture
def frontend_only(settings):
    """CORS as in production: only the frontend is allowed."""
    settings.CORS_ALLOW_ALL_ORIGINS = False
    settings.CORS_ALLOWED_ORIGINS = [FRONTEND]


async def ticket_of(member):
    answer = await sync_to_async(member.post)(TICKET_URL)
    return answer.data["data"]["ticket"]


async def open_from(origin, ticket):
    """Open the connection as a browser on `origin` (None: a client that sends no origin)."""
    headers = [(b"origin", origin.encode())] if origin else []
    scope = {
        "type": "websocket",
        "path": "/ws/inbox/",
        "raw_path": b"/ws/inbox/",
        "query_string": f"ticket={ticket}".encode(),
        "headers": headers,
        "subprotocols": [],
        "scheme": "ws",
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    connection = ApplicationCommunicator(application, scope)
    await connection.send_input({"type": "websocket.connect"})
    answer = await connection.receive_output(timeout=2)
    accepted = answer["type"] == "websocket.accept"
    if accepted:
        await connection.send_input({"type": "websocket.disconnect", "code": 1000})
        await connection.wait(timeout=2)
    return accepted


def test_a_page_of_another_origin_cannot_open_the_connection(member, frontend_only):
    async def scenario():
        return await open_from(FOREIGN, await ticket_of(member))

    assert async_to_sync(scenario)() is False


def test_the_frontend_opens_the_connection(member, frontend_only):
    async def scenario():
        return await open_from(FRONTEND, await ticket_of(member))

    assert async_to_sync(scenario)() is True


def test_with_every_origin_allowed_any_page_and_client_connects(member, settings):
    settings.CORS_ALLOW_ALL_ORIGINS = True

    async def scenario():
        return [
            await open_from(origin, await ticket_of(member)) for origin in (FOREIGN, FRONTEND, None)
        ]

    assert async_to_sync(scenario)() == [True, True, True]


def test_a_client_that_sends_no_origin_cannot_open_the_connection(member, frontend_only):
    async def scenario():
        return await open_from(None, await ticket_of(member))

    assert async_to_sync(scenario)() is False


def test_a_rejected_origin_does_not_spend_the_permit(member, frontend_only):
    async def scenario():
        ticket = await ticket_of(member)
        return [await open_from(FOREIGN, ticket), await open_from(FRONTEND, ticket)]

    assert async_to_sync(scenario)() == [False, True]


def test_settings_that_do_not_define_open_cors_work_as_closed_cors(member, frontend_only, settings):
    # As in production, which never defines the setting
    del settings.CORS_ALLOW_ALL_ORIGINS

    async def scenario():
        return [
            await open_from(origin, await ticket_of(member)) for origin in (FOREIGN, None, FRONTEND)
        ]

    assert async_to_sync(scenario)() == [False, False, True]
