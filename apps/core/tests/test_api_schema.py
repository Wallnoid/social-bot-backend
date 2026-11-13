"""
The OpenAPI schema the frontend generates its types from.
"""

import json
import re

import pytest
from django.conf import settings
from django.core.management import call_command
from drf_spectacular.generators import SchemaGenerator
from rest_framework.schemas.generators import EndpointEnumerator

from apps.tenants.permissions import HasActiveTenant


def test_the_schema_is_served_as_json_at_openapi_json(client):
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.oai.openapi+json")
    schema = json.loads(response.content)
    assert schema["openapi"].startswith("3.")
    assert "/api/v1/inbox/{channel}/conversations/" in schema["paths"]


def test_the_schema_is_still_served_at_api_schema(client):
    response = client.get("/api/schema/")

    assert response.status_code == 200


# The types the frontend generates come from this schema: every value and shape
# checked below is what the API really answers.

INBOX = "/api/v1/inbox/{channel}/conversations/"
CHAT = INBOX + "{contact_id}/messages/"
FILE = CHAT + "{message_id}/file/"
SEND = INBOX + "{contact_id}/send/"
CHANNELS = ["whatsapp", "messenger", "instagram"]


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def component(schema, name):
    return schema["components"]["schemas"][name]


def resolve(schema, node):
    """Follow a `$ref` (alone or inside `allOf`) to the component it points to."""
    ref = node.get("$ref") or next((part["$ref"] for part in node.get("allOf", [])), None)
    return component(schema, ref.rsplit("/", 1)[1]) if ref else node


def enum_of(schema, node):
    node = resolve(schema, node)
    return node.get("enum")


def response_data(schema, operation, status="200"):
    content = operation["responses"][status]["content"]["application/json"]["schema"]
    return resolve(schema, resolve(schema, content)["properties"]["data"])


@pytest.mark.parametrize("name", ["InboxMessage", "ChatMessage"])
def test_the_direction_of_a_message_is_in_or_out(schema, name):
    direction = component(schema, name)["properties"]["direction"]

    assert enum_of(schema, direction) == ["in", "out"]


def test_the_kind_of_a_file_is_one_of_the_five_the_api_knows(schema):
    kind = component(schema, "MessageFile")["properties"]["kind"]

    assert set(enum_of(schema, kind)) == {"image", "audio", "video", "document", "sticker"}


@pytest.mark.parametrize(
    ("field", "values"),
    [
        ("type", ["text", "image", "audio", "video", "document", "sticker", "location"]),
        ("status", ["sent", "delivered", "read", "failed"]),
    ],
)
def test_type_and_status_list_what_is_known_and_stay_open_because_meta_may_send_others(
    schema, field, values
):
    prop = component(schema, "InboxMessage")["properties"][field]

    assert prop["type"] == "string" and "enum" not in prop
    assert all(value in prop["description"] for value in values)
    assert "other" in prop["description"].lower()


@pytest.mark.parametrize(
    "name", ["Conversation", "ChatMessages", "BotState", "InboxAccount", "ChannelAccount"]
)
def test_every_channel_field_uses_the_channel_enum(schema, name):
    prop = component(schema, name)["properties"]["channel"]

    ref = prop.get("$ref") or prop["allOf"][0]["$ref"]
    assert ref == "#/components/schemas/ChannelEnum"
    assert enum_of(schema, prop) == CHANNELS


@pytest.mark.parametrize("method", ["get", "put", "patch"])
def test_users_me_declares_the_envelope_like_the_other_endpoints(schema, method):
    operation = schema["paths"]["/api/v1/accounts/users/me/"][method]

    envelope = resolve(
        schema, operation["responses"]["200"]["content"]["application/json"]["schema"]
    )
    assert envelope["properties"]["success"]["type"] == "boolean"
    assert "UserProfile" in str(envelope["properties"]["data"])


def test_the_businesses_of_a_user_are_a_list_of_id_name_and_role(schema):
    tenants = component(schema, "UserProfile")["properties"]["tenants"]

    assert tenants["type"] == "array"
    item = resolve(schema, tenants["items"])
    assert set(item["properties"]) == {"id", "name", "role"}
    assert enum_of(schema, item["properties"]["role"]) == ["agent", "supervisor", "admin"]


def test_the_current_business_is_in_the_schema_with_its_envelope(schema):
    operation = schema["paths"]["/api/v1/tenants/current/"]["get"]

    data = response_data(schema, operation)
    assert set(data["properties"]) == {"id", "name", "role", "bot_daily_limit_until"}


def tenant_aware_routes():
    """The (route, method) of every view that works inside a business, from the code."""
    for route, method, view in EndpointEnumerator().get_api_endpoints():
        route = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", route)
        route = re.sub(r"\{format\}$", "", route)
        needs_business = HasActiveTenant in getattr(view.cls, "permission_classes", [])
        yield route, method.lower(), needs_business


def test_the_business_header_is_declared_exactly_where_a_business_is_needed(schema):
    checked = []
    for route, method, needs_business in tenant_aware_routes():
        operation = schema["paths"].get(route, {}).get(method)
        if operation is None:
            continue
        headers = [p["name"] for p in operation.get("parameters", []) if p["in"] == "header"]
        assert ("X-Tenant-ID" in headers) == needs_business, (method, route)
        checked.append((route, method))

    assert (INBOX, "get") in checked and ("/api/v1/channels/accounts/", "get") in checked
    assert len(checked) > 20


def test_the_file_answers_any_bytes_and_says_where_and_how_it_is_kept(schema):
    operation = schema["paths"][FILE]["get"]

    ok = operation["responses"]["200"]
    assert ok["content"]["*/*"]["schema"] == {"type": "string", "format": "binary"}
    text = operation["description"]
    assert "no public address" in text and "X-Tenant-ID" in text and "blob" in text
    assert f"{settings.MESSAGE_FILE_RETENTION_DAYS} days" in text
    assert f"{settings.MESSAGE_FILE_MAX_BYTES // (1024 * 1024)} MB" in text


def test_the_conflict_of_a_send_names_its_stable_codes(schema):
    conflict = schema["paths"][SEND]["post"]["responses"]["409"]["description"]

    assert "window_closed" in conflict and "human_agent_expired" in conflict


def test_generating_the_schema_gives_no_warning_and_no_error(tmp_path):
    # --fail-on-warn makes the command raise on any warning or error
    call_command("spectacular", "--fail-on-warn", file=str(tmp_path / "schema.yml"))
