"""
Tests for a business admin creating, editing and deleting the tools of the bot of an account.
"""

import json
import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from drf_spectacular.generators import SchemaGenerator
from wanps.messaging.models import App

from apps.channels.models import ChannelTool
from apps.channels.tests.test_manage_accounts import add_account
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

SECRET = "tool-secret-never-shown"
TOOL = {
    "name": "opening_hours",
    "description": "Gives the opening hours of the clinic for a day.",
    "url": "https://api.acme.example/hours",
    "parameters": [
        {"name": "day", "type": "string", "description": "Day of the week", "required": True}
    ],
    "auth_type": "bearer",
    "auth_secret": SECRET,
}


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def admin_client(tenant):
    return client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def link(tenant, meta_app):
    return add_account(tenant, meta_app, "111")


def tools_url(link):
    return f"/api/v1/channels/accounts/{link.id}/tools/"


def tool_url(link, tool_id):
    return f"{tools_url(link)}{tool_id}/"


def create(api, link, **overrides):
    return api.post(tools_url(link), {**TOOL, **overrides}, format="json")


def test_admin_creates_a_tool_and_it_appears_in_the_list(admin_client, link):
    response = create(admin_client, link)

    assert response.status_code == 201
    created = response.data["data"]
    assert {key: value for key, value in created.items() if key != "id"} == {
        "name": "opening_hours",
        "description": "Gives the opening hours of the clinic for a day.",
        "url": "https://api.acme.example/hours",
        "parameters": [
            {"name": "day", "type": "string", "description": "Day of the week", "required": True}
        ],
        "auth_type": "bearer",
        "auth_header": "",
        "has_secret": True,
        "is_active": True,
    }
    listed = admin_client.get(tools_url(link))
    assert listed.status_code == 200
    assert listed.data["data"] == [created]


def test_the_secret_never_comes_back_and_is_stored_encrypted(admin_client, link):
    created = create(admin_client, link)
    tool_id = created.data["data"]["id"]

    responses = [
        created,
        admin_client.get(tools_url(link)),
        admin_client.get(tool_url(link, tool_id)),
        admin_client.patch(tool_url(link, tool_id), {"description": "New"}, format="json"),
    ]

    for response in responses:
        assert response.status_code in (200, 201)
        text = response.content.decode()
        assert SECRET not in text and "auth_secret" not in text
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT auth_secret FROM {ChannelTool._meta.db_table}")
        (stored,) = cursor.fetchone()
    assert stored and SECRET not in stored


def test_admin_reads_one_tool(admin_client, link):
    tool_id = create(admin_client, link).data["data"]["id"]

    response = admin_client.get(tool_url(link, tool_id))

    assert response.status_code == 200
    assert response.data["data"]["name"] == "opening_hours"


def test_editing_a_tool_changes_what_was_sent_and_keeps_the_secret_when_it_is_not_sent(
    admin_client, link
):
    tool_id = create(admin_client, link).data["data"]["id"]

    edited = admin_client.patch(
        tool_url(link, tool_id),
        {"description": "New description", "is_active": False},
        format="json",
    )

    assert edited.status_code == 200
    assert edited.data["data"]["description"] == "New description"
    assert edited.data["data"]["is_active"] is False
    assert edited.data["data"]["has_secret"] is True
    assert ChannelTool.objects.get(pk=tool_id).auth_secret == SECRET

    admin_client.patch(tool_url(link, tool_id), {"auth_secret": "rotated"}, format="json")

    assert ChannelTool.objects.get(pk=tool_id).auth_secret == "rotated"


def test_admin_deletes_a_tool_and_it_leaves_the_list(admin_client, link):
    tool_id = create(admin_client, link).data["data"]["id"]

    deleted = admin_client.delete(tool_url(link, tool_id))
    again = admin_client.delete(tool_url(link, tool_id))

    assert deleted.status_code == 200
    assert again.status_code == 404
    assert admin_client.get(tools_url(link)).data["data"] == []


@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
@pytest.mark.parametrize("method", ["list", "create", "read", "edit", "delete"])
def test_agents_and_supervisors_get_403_on_every_operation(
    tenant, link, admin_client, role, method
):
    tool_id = create(admin_client, link).data["data"]["id"]
    member = client_for(add_member(tenant, "member@acme.test", role))
    calls = {
        "list": lambda: member.get(tools_url(link)),
        "create": lambda: create(member, link, name="another"),
        "read": lambda: member.get(tool_url(link, tool_id)),
        "edit": lambda: member.patch(tool_url(link, tool_id), {"description": "x"}, format="json"),
        "delete": lambda: member.delete(tool_url(link, tool_id)),
    }

    response = calls[method]()

    assert response.status_code == 403
    assert ChannelTool.objects.count() == 1
    assert ChannelTool.objects.get().description == TOOL["description"]


def test_an_account_or_a_tool_of_another_business_is_not_found(admin_client, link, meta_app):
    rival = add_account(Tenant.objects.create(name="Rival Clinic"), meta_app, "222")
    rival_tool = ChannelTool.objects.create(
        account=rival.account, name="secret_tool", description="d", url="https://r.example/x"
    )

    assert admin_client.get(tools_url(rival)).status_code == 404
    assert create(admin_client, rival).status_code == 404
    assert admin_client.get(tool_url(rival, rival_tool.pk)).status_code == 404
    # Nor under the id of an account of the own business
    assert admin_client.get(tool_url(link, rival_tool.pk)).status_code == 404
    assert (
        admin_client.patch(tool_url(link, rival_tool.pk), {"name": "x"}, format="json").status_code
        == 404
    )
    assert admin_client.delete(tool_url(link, rival_tool.pk)).status_code == 404
    assert ChannelTool.objects.get(pk=rival_tool.pk).name == "secret_tool"
    assert (
        admin_client.get(tools_url(link).replace(str(link.id), str(uuid.uuid4()))).status_code
        == 404
    )


@pytest.mark.parametrize(
    "name", ["Opening", "1hours", "has space", "with-dash", "a" * 65, "", "áccent"]
)
def test_a_name_must_be_lowercase_letters_digits_and_underscores_starting_with_a_letter(
    admin_client, link, name
):
    response = create(admin_client, link, name=name)

    assert response.status_code == 400
    assert "name" in response.data["errors"]
    assert not ChannelTool.objects.exists()


@pytest.mark.parametrize("name", ["a", "a" * 64, "hours_2"])
def test_valid_names_are_accepted(admin_client, link, name):
    assert create(admin_client, link, name=name).status_code == 201


def test_a_name_is_unique_in_an_account_but_not_between_accounts(
    admin_client, tenant, meta_app, link
):
    other = add_account(tenant, meta_app, "333")
    create(admin_client, link)

    same_account = create(admin_client, link)
    other_account = create(admin_client, other)

    assert same_account.status_code == 400
    assert "name" in same_account.data["errors"]
    assert other_account.status_code == 201


def test_an_account_has_at_most_ten_tools(admin_client, link):
    for number in range(10):
        assert create(admin_client, link, name=f"tool_{number}").status_code == 201

    response = create(admin_client, link, name="one_too_many")

    assert response.status_code == 400
    assert ChannelTool.objects.count() == 10


@pytest.mark.parametrize(
    "url",
    [
        "http://api.acme.example/hours",
        "ftp://api.acme.example/hours",
        "https://user:password@api.acme.example/hours",
        "api.acme.example/hours",
        "https://",
        "",
    ],
)
def test_the_address_must_be_https_without_credentials(admin_client, link, url):
    response = create(admin_client, link, url=url)

    assert response.status_code == 400
    assert "url" in response.data["errors"]


@pytest.mark.parametrize(
    "parameters",
    [
        "day",
        [{"type": "string", "description": "d", "required": True}],
        [{"name": "Day", "type": "string", "description": "d", "required": True}],
        [{"name": "day", "type": "date", "description": "d", "required": True}],
        [
            {"name": "day", "type": "string", "description": "d", "required": True},
            {"name": "day", "type": "number", "description": "e", "required": False},
        ],
        [{"name": "day", "type": "string", "description": "d", "required": "yes"}],
    ],
)
def test_the_parameters_must_be_a_valid_list(admin_client, link, parameters):
    response = create(admin_client, link, parameters=parameters)

    assert response.status_code == 400
    assert "parameters" in response.data["errors"]


def test_a_tool_may_have_no_parameters_and_the_types_are_text_number_and_yes_no(admin_client, link):
    assert create(admin_client, link, name="none", parameters=[]).status_code == 201
    typed = [
        {"name": "a", "type": "string", "description": "d", "required": False},
        {"name": "b", "type": "number", "description": "d", "required": False},
        {"name": "c", "type": "boolean", "description": "d", "required": True},
    ]
    assert create(admin_client, link, name="typed", parameters=typed).status_code == 201


@pytest.mark.parametrize(
    ("auth", "field"),
    [
        ({"auth_type": "bearer", "auth_secret": ""}, "auth_secret"),
        ({"auth_type": "header", "auth_header": "X-Api-Key", "auth_secret": ""}, "auth_secret"),
        ({"auth_type": "header", "auth_header": "", "auth_secret": SECRET}, "auth_header"),
        ({"auth_type": "header", "auth_header": "Host", "auth_secret": SECRET}, "auth_header"),
        (
            {"auth_type": "header", "auth_header": "bad header", "auth_secret": SECRET},
            "auth_header",
        ),
        ({"auth_type": "none", "auth_secret": SECRET}, "auth_secret"),
        ({"auth_type": "digest", "auth_secret": SECRET}, "auth_type"),
    ],
)
def test_the_authentication_must_be_consistent(admin_client, link, auth, field):
    response = create(admin_client, link, **auth)

    assert response.status_code == 400
    assert field in response.data["errors"]


def test_a_tool_may_have_no_authentication_or_a_key_in_a_header(admin_client, link):
    none = create(admin_client, link, name="open", auth_type="none", auth_secret="")
    header = create(
        admin_client,
        link,
        name="keyed",
        auth_type="header",
        auth_header="X-Api-Key",
        auth_secret=SECRET,
    )

    assert none.status_code == 201 and none.data["data"]["has_secret"] is False
    assert header.status_code == 201
    assert header.data["data"]["auth_header"] == "X-Api-Key"


def test_the_api_docs_describe_the_tools_without_the_secret_and_warn_about_the_ai_provider():
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    paths = schema["paths"]
    collection = "/api/v1/channels/accounts/{account_id}/tools/"
    item = collection + "{tool_id}/"
    assert set(paths[collection]) >= {"get", "post"}
    assert set(paths[item]) >= {"get", "patch", "delete"}
    shown = json.dumps(components["ChannelTool"])
    assert "auth_secret" not in shown and "has_secret" in shown
    assert "auth_secret" in json.dumps(components["ChannelToolRequest"])
    assert "AI provider" in paths[collection]["post"]["description"]


@pytest.mark.parametrize("name", ["account", "msg"])
def test_a_parameter_cannot_use_a_name_that_the_system_fills_in_by_itself(admin_client, link, name):
    parameters = [{"name": name, "type": "string", "description": "d", "required": True}]

    response = create(admin_client, link, parameters=parameters)

    assert response.status_code == 400
    assert "parameters" in response.data["errors"]


NEWLINE, TAB = chr(10), chr(9)


@pytest.mark.parametrize(
    "secret",
    [
        "key with " + chr(8220) + "smart quotes" + chr(8221),
        "clave-con-" + chr(241),
        "line" + NEWLINE + "break",
        "tab" + TAB + "key",
    ],
)
def test_a_key_must_be_printable_ascii_so_it_can_travel_in_a_header(admin_client, link, secret):
    response = create(admin_client, link, auth_secret=secret)

    assert response.status_code == 400
    assert "auth_secret" in response.data["errors"]


def test_a_key_with_the_usual_symbols_is_accepted(admin_client, link):
    assert create(admin_client, link, auth_secret="abc-123_XYZ.=+/").status_code == 201


def test_changing_the_authentication_type_clears_what_the_new_type_does_not_use(admin_client, link):
    tool_id = create(admin_client, link, auth_type="header", auth_header="X-Api-Key").data["data"][
        "id"
    ]

    to_none = admin_client.patch(tool_url(link, tool_id), {"auth_type": "none"}, format="json")

    assert to_none.status_code == 200
    data = to_none.data["data"]
    assert (data["auth_type"], data["auth_header"], data["has_secret"]) == ("none", "", False)


def test_changing_to_a_type_that_needs_a_key_asks_for_the_new_one(admin_client, link):
    tool_id = create(admin_client, link, auth_type="none", auth_secret="").data["data"]["id"]

    without = admin_client.patch(tool_url(link, tool_id), {"auth_type": "bearer"}, format="json")
    with_key = admin_client.patch(
        tool_url(link, tool_id), {"auth_type": "bearer", "auth_secret": "new-token"}, format="json"
    )

    assert without.status_code == 400 and "auth_secret" in without.data["errors"]
    assert with_key.status_code == 200 and with_key.data["data"]["has_secret"] is True


def test_editing_and_deleting_a_tool_lock_its_account_like_creating_does(admin_client, link):
    tool_id = create(admin_client, link).data["data"]["id"]

    with CaptureQueriesContext(connection) as edit:
        admin_client.patch(tool_url(link, tool_id), {"description": "x"}, format="json")
    with CaptureQueriesContext(connection) as delete:
        admin_client.delete(tool_url(link, tool_id))

    for queries in (edit, delete):
        locks = [
            q["sql"]
            for q in queries
            if "FOR UPDATE" in q["sql"] and "channels_channelaccount" in q["sql"]
        ]
        assert locks
