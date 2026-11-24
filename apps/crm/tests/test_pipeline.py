"""
The pipeline of a business: its stages in order, the contacts of each one, and moving a contact
from one stage to another, for any member of the business.
"""

import uuid

import pytest
from django.core import serializers
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from wanps.messaging.models import App

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.crm.models import Stage
from apps.crm.tests.migrations import migrate_to
from apps.crm.tests.test_contact_list import sent
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

STAGES_URL = "/api/v1/crm/stages/"
CONTACTS_URL = "/api/v1/crm/contacts/"
DEFAULT_STAGES = ["Nuevo", "En conversación", "Interesado", "Cliente", "Perdido"]


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def member(tenant):
    return client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))


def stages(member):
    response = member.get(STAGES_URL)
    assert response.status_code == 200
    return response.data["data"]["stages"]


def test_a_new_business_has_the_five_default_stages_in_order(member):
    assert [stage["name"] for stage in stages(member)] == DEFAULT_STAGES


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_sees_how_many_contacts_each_stage_has(tenant, meta_app, role):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Hola", contact_name="Ana")
    add_message(link, "593990000002", "Buenas", contact_name="Luis")
    any_member = client_for(add_member(tenant, "any@acme.test", role))

    counts = {stage["name"]: stage["contacts"] for stage in stages(any_member)}

    assert counts == {
        "Nuevo": 2,
        "En conversación": 0,
        "Interesado": 0,
        "Cliente": 0,
        "Perdido": 0,
    }


def stage_named(member, name):
    return next(stage for stage in stages(member) if stage["name"] == name)


def test_the_contacts_of_a_stage_are_paged_latest_contact_first(tenant, meta_app, member):
    link = add_account(tenant, meta_app, "111")
    sent(add_message(link, "593990000001", "Hola", contact_name="Ana"), days_ago=3)
    sent(add_message(link, "593990000002", "Hola", contact_name="Luis"), days_ago=1)
    sent(add_message(link, "593990000003", "Hola", contact_name="Eva"), days_ago=2)
    nuevo = stage_named(member, "Nuevo")["id"]

    first = member.get(CONTACTS_URL, {"stage": nuevo, "limit": 2}).data["data"]
    second = member.get(CONTACTS_URL, {"stage": nuevo, "limit": 2, "offset": 2}).data["data"]
    cliente = member.get(CONTACTS_URL, {"stage": stage_named(member, "Cliente")["id"]})

    assert [contact["name"] for contact in first["contacts"]] == ["Luis", "Eva"]
    assert first["has_more"] is True
    assert [contact["name"] for contact in second["contacts"]] == ["Ana"]
    assert second["has_more"] is False
    assert cliente.data["data"]["contacts"] == []


def test_a_new_contact_starts_in_nuevo(tenant, meta_app, member):
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")
    nuevo = stage_named(member, "Nuevo")

    listed = member.get(CONTACTS_URL).data["data"]["contacts"][0]
    opened = member.get(f"{CONTACTS_URL}{listed['id']}/").data["data"]

    assert listed["stage"] == {"id": nuevo["id"], "name": "Nuevo"}
    assert opened["stage"] == {"id": nuevo["id"], "name": "Nuevo"}


@pytest.mark.django_db(transaction=True)
def test_businesses_and_contacts_that_existed_before_get_the_stages_and_start_in_nuevo():
    tenant = Tenant.objects.create(name="Acme Dental")
    meta_app = App.objects.create(name="Social Bot", app_secret="secret", verify_token="verify")
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")
    # The database as it was before the pipeline: contacts had no stage and businesses had none.
    # It is set up through the models of that point of the history, because the current ones
    # ask for columns that did not exist yet.
    before = migrate_to(("crm", "0005_contact_stage"))
    before.get_model("crm", "Contact")._base_manager.all().update(stage=None)
    before.get_model("crm", "Stage")._base_manager.all().delete()

    migrate_to()

    member = client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))
    assert [stage["name"] for stage in stages(member)] == DEFAULT_STAGES
    assert stage_named(member, "Nuevo")["contacts"] == 1
    assert member.get(CONTACTS_URL).data["data"]["contacts"][0]["stage"]["name"] == "Nuevo"


def test_moving_a_contact_shows_it_in_the_new_stage_everywhere(tenant, meta_app, member):
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")
    contact = member.get(CONTACTS_URL).data["data"]["contacts"][0]
    interesado = stage_named(member, "Interesado")["id"]

    response = member.patch(f"{CONTACTS_URL}{contact['id']}/", {"stage": interesado}, format="json")

    assert response.status_code == 200
    assert response.data["data"]["stage"] == {"id": interesado, "name": "Interesado"}
    opened = member.get(f"{CONTACTS_URL}{contact['id']}/").data["data"]
    assert opened["stage"]["name"] == "Interesado"
    column = member.get(CONTACTS_URL, {"stage": interesado}).data["data"]["contacts"]
    assert [listed["id"] for listed in column] == [contact["id"]]
    nuevo = member.get(CONTACTS_URL, {"stage": stage_named(member, "Nuevo")["id"]})
    assert nuevo.data["data"]["contacts"] == []
    counts = {stage["name"]: stage["contacts"] for stage in stages(member)}
    assert (counts["Nuevo"], counts["Interesado"]) == (0, 1)


def a_contact_of(tenant, meta_app, member):
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")
    return member.get(CONTACTS_URL).data["data"]["contacts"][0]


def test_a_stage_of_another_business_is_rejected_and_the_contact_stays(tenant, meta_app, member):
    contact = a_contact_of(tenant, meta_app, member)
    rival = Tenant.objects.create(name="Rival Clinic")
    theirs = Stage.objects.get(tenant=rival, name="Cliente")

    response = member.patch(
        f"{CONTACTS_URL}{contact['id']}/", {"stage": str(theirs.pk)}, format="json"
    )

    assert response.status_code == 400
    opened = member.get(f"{CONTACTS_URL}{contact['id']}/").data["data"]
    assert opened["stage"]["name"] == "Nuevo"


def test_a_stage_that_does_not_exist_is_rejected_and_the_contact_stays(tenant, meta_app, member):
    contact = a_contact_of(tenant, meta_app, member)

    response = member.patch(
        f"{CONTACTS_URL}{contact['id']}/", {"stage": str(uuid.uuid4())}, format="json"
    )

    assert response.status_code == 400
    opened = member.get(f"{CONTACTS_URL}{contact['id']}/").data["data"]
    assert opened["stage"]["name"] == "Nuevo"


def test_the_stages_of_another_business_are_not_listed(tenant, meta_app, member):
    rival = Tenant.objects.create(name="Rival Clinic")
    add_message(add_account(rival, meta_app, "222"), "593990000009", "Hola", contact_name="Zoe")
    theirs = {str(pk) for pk in Stage.objects.filter(tenant=rival).values_list("pk", flat=True)}

    listed = stages(member)

    assert len(listed) == 5
    assert not theirs & {stage["id"] for stage in listed}
    assert all(stage["contacts"] == 0 for stage in listed)


def test_a_message_of_a_chat_that_has_its_contact_does_not_look_up_the_stages(tenant, meta_app):
    link = add_account(tenant, meta_app, "111")
    add_message(link, "593990000001", "Hola", contact_name="Ana")

    with CaptureQueriesContext(connection) as queries:
        add_message(link, "593990000001", "Sigo aquí", contact_name="Ana")

    assert not [query for query in queries if '"crm_stage"' in query["sql"]]


def test_loading_a_business_from_a_fixture_does_not_add_the_default_stages(db):
    # A fixture carries its dates: a raw load does not set them
    now = timezone.now()
    dumped = serializers.serialize(
        "json", [Tenant(name="Loaded Clinic", created_at=now, updated_at=now)]
    )

    for loaded in serializers.deserialize("json", dumped):
        loaded.save()

    assert not Stage.objects.filter(tenant__name="Loaded Clinic").exists()
