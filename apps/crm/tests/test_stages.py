"""
The stages of the pipeline, managed by the admins of the business: create, rename, reorder and
delete them.
"""

import pytest
from wanps.messaging.models import App

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.crm.models import Contact
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

STAGES_URL = "/api/v1/crm/stages/"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def admin(tenant):
    return client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))


def stages(member):
    response = member.get(STAGES_URL)
    assert response.status_code == 200
    return response.data["data"]["stages"]


def names(member):
    return [stage["name"] for stage in stages(member)]


def test_an_admin_creates_a_stage_and_it_is_added_at_the_end_with_no_contacts(admin):
    response = admin.post(STAGES_URL, {"name": "Propuesta enviada"}, format="json")

    assert response.status_code == 201
    assert response.data["data"]["name"] == "Propuesta enviada"
    assert response.data["data"]["contacts"] == 0
    assert stages(admin)[-1] == {
        "id": response.data["data"]["id"],
        "name": "Propuesta enviada",
        "contacts": 0,
    }
    assert names(admin) == [
        "Nuevo",
        "En conversación",
        "Interesado",
        "Cliente",
        "Perdido",
        "Propuesta enviada",
    ]


def stage_url(stage_id):
    return f"{STAGES_URL}{stage_id}/"


def stage_named(member, name):
    return next(stage for stage in stages(member) if stage["name"] == name)


def test_an_admin_renames_a_stage_and_the_new_name_shows_in_the_pipeline_the_list_and_the_file(
    tenant, meta_app, admin
):
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")
    contact = Contact.objects.get()
    nuevo = stage_named(admin, "Nuevo")["id"]

    response = admin.patch(stage_url(nuevo), {"name": "Primer contacto"}, format="json")

    assert response.status_code == 200
    assert response.data["data"] == {"id": nuevo, "name": "Primer contacto", "contacts": 1}
    assert names(admin)[0] == "Primer contacto"
    listed = admin.get("/api/v1/crm/contacts/").data["data"]["contacts"][0]
    assert listed["stage"] == {"id": nuevo, "name": "Primer contacto"}
    file = admin.get(f"/api/v1/crm/contacts/{contact.pk}/").data["data"]
    assert file["stage"] == {"id": nuevo, "name": "Primer contacto"}


ORDER_URL = f"{STAGES_URL}order/"


def test_an_admin_reorders_the_stages_and_the_pipeline_shows_them_in_that_order(admin):
    ids = {stage["name"]: stage["id"] for stage in stages(admin)}
    order = ["Interesado", "Nuevo", "Perdido", "En conversación", "Cliente"]

    response = admin.put(ORDER_URL, {"stages": [ids[name] for name in order]}, format="json")

    assert response.status_code == 200
    assert [stage["name"] for stage in response.data["data"]["stages"]] == order
    assert names(admin) == order


def test_after_reordering_a_new_contact_starts_in_the_stage_that_is_now_first(
    tenant, meta_app, admin
):
    ids = {stage["name"]: stage["id"] for stage in stages(admin)}
    order = ["Interesado", "Nuevo", "En conversación", "Cliente", "Perdido"]
    admin.put(ORDER_URL, {"stages": [ids[name] for name in order]}, format="json")

    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")

    listed = admin.get("/api/v1/crm/contacts/").data["data"]["contacts"][0]
    assert listed["stage"] == {"id": ids["Interesado"], "name": "Interesado"}


def rival_stage():
    return str(Tenant.objects.create(name="Rival Clinic").stages.first().pk)


@pytest.mark.parametrize(
    "wrong",
    [
        lambda ids: ids[1:],
        lambda ids: [*ids[:-1], ids[0]],
        lambda ids: [*ids[:-1], rival_stage()],
        lambda ids: [*ids[:-1], "6b0f3c38-0000-4000-8000-000000000000"],
        lambda ids: [*ids, ids[0]],
    ],
    ids=["missing", "repeated", "of another business", "unknown", "one more"],
)
def test_an_order_that_is_not_exactly_the_stages_of_the_business_is_rejected(admin, wrong):
    ids = [stage["id"] for stage in reversed(stages(admin))]

    response = admin.put(ORDER_URL, {"stages": wrong(ids)}, format="json")

    assert response.status_code == 400
    assert names(admin) == ["Nuevo", "En conversación", "Interesado", "Cliente", "Perdido"]


def test_an_admin_deletes_a_stage_without_contacts(admin):
    perdido = stage_named(admin, "Perdido")["id"]

    response = admin.delete(stage_url(perdido))

    assert response.status_code == 200
    assert names(admin) == ["Nuevo", "En conversación", "Interesado", "Cliente"]


def add_contacts(tenant, meta_app, count):
    link = add_account(tenant, meta_app, "111")
    for number in range(count):
        add_message(link, f"59399000000{number}", "Hola", contact_name=f"Client {number}")


def test_deleting_a_stage_with_contacts_moves_them_to_the_chosen_stage(tenant, meta_app, admin):
    add_contacts(tenant, meta_app, 2)
    nuevo, cliente = stage_named(admin, "Nuevo")["id"], stage_named(admin, "Cliente")["id"]

    response = admin.delete(f"{stage_url(nuevo)}?move_to={cliente}")

    assert response.status_code == 200
    assert names(admin) == ["En conversación", "Interesado", "Cliente", "Perdido"]
    assert stage_named(admin, "Cliente")["contacts"] == 2
    listed = admin.get("/api/v1/crm/contacts/").data["data"]["contacts"]
    assert [contact["stage"]["name"] for contact in listed] == ["Cliente", "Cliente"]


@pytest.mark.parametrize(
    "move_to",
    [
        lambda nuevo: "",
        lambda nuevo: f"?move_to={nuevo}",
        lambda nuevo: f"?move_to={rival_stage()}",
        lambda nuevo: "?move_to=6b0f3c38-0000-4000-8000-000000000000",
    ],
    ids=["missing", "itself", "of another business", "unknown"],
)
def test_deleting_a_stage_with_contacts_without_a_valid_stage_to_move_them_is_rejected(
    tenant, meta_app, admin, move_to
):
    add_contacts(tenant, meta_app, 2)
    nuevo = stage_named(admin, "Nuevo")["id"]

    response = admin.delete(f"{stage_url(nuevo)}{move_to(nuevo)}")

    assert response.status_code == 400
    assert names(admin) == ["Nuevo", "En conversación", "Interesado", "Cliente", "Perdido"]
    assert stage_named(admin, "Nuevo")["contacts"] == 2


def test_the_last_stage_of_a_business_cannot_be_deleted(admin):
    *others, last = stages(admin)
    for stage in others:
        assert admin.delete(stage_url(stage["id"])).status_code == 200

    response = admin.delete(stage_url(last["id"]))

    assert response.status_code == 400
    assert names(admin) == ["Perdido"]


DEFAULT_NAMES = ["Nuevo", "En conversación", "Interesado", "Cliente", "Perdido"]


@pytest.mark.parametrize("name", ["Nuevo", "nuevo", "EN CONVERSACIÓN"])
def test_creating_a_stage_with_a_name_already_used_in_the_business_is_rejected(admin, name):
    response = admin.post(STAGES_URL, {"name": name}, format="json")

    assert response.status_code == 400
    assert names(admin) == DEFAULT_NAMES


@pytest.mark.parametrize("name", ["Perdido", "perdido", "INTERESADO"])
def test_renaming_a_stage_to_a_name_already_used_in_the_business_is_rejected(admin, name):
    cliente = stage_named(admin, "Cliente")["id"]

    response = admin.patch(stage_url(cliente), {"name": name}, format="json")

    assert response.status_code == 400
    assert names(admin) == DEFAULT_NAMES


def test_the_name_of_a_deleted_stage_can_be_used_again(admin):
    admin.delete(stage_url(stage_named(admin, "Perdido")["id"]))

    response = admin.post(STAGES_URL, {"name": "Perdido"}, format="json")

    assert response.status_code == 201
    assert names(admin) == DEFAULT_NAMES


@pytest.mark.parametrize("role", [Membership.Role.AGENT, Membership.Role.SUPERVISOR])
def test_agents_and_supervisors_cannot_create_rename_reorder_or_delete_stages(admin, tenant, role):
    member = client_for(add_member(tenant, "member@acme.test", role))
    ids = [stage["id"] for stage in stages(admin)]

    assert member.post(STAGES_URL, {"name": "Propuesta"}, format="json").status_code == 403
    assert member.patch(stage_url(ids[0]), {"name": "Otro"}, format="json").status_code == 403
    order = {"stages": list(reversed(ids))}
    assert member.put(ORDER_URL, order, format="json").status_code == 403
    assert member.delete(stage_url(ids[-1])).status_code == 403
    assert names(admin) == DEFAULT_NAMES


def test_a_stage_of_another_business_is_not_found_and_does_not_change(admin):
    rival = Tenant.objects.create(name="Rival Clinic")
    theirs = rival.stages.get(name="Nuevo")

    assert admin.patch(stage_url(theirs.pk), {"name": "Mine"}, format="json").status_code == 404
    assert admin.delete(stage_url(theirs.pk)).status_code == 404
    assert [stage.name for stage in rival.stages.all()] == DEFAULT_NAMES


def test_the_deleted_contacts_of_a_deleted_stage_move_to_the_first_stage_left(
    tenant, meta_app, admin
):
    add_contacts(tenant, meta_app, 1)
    contact = Contact.objects.get()
    contact.delete()
    nuevo = stage_named(admin, "Nuevo")["id"]

    response = admin.delete(stage_url(nuevo))

    assert response.status_code == 200
    contact = Contact.all_objects.get(pk=contact.pk)
    assert contact.stage.name == "En conversación"


def test_the_contacts_moved_from_a_deleted_stage_and_the_reordered_stages_are_marked_as_changed(
    tenant, meta_app, admin
):
    add_contacts(tenant, meta_app, 1)
    contact = Contact.objects.get()
    before = contact.updated_at
    ids = {stage["name"]: stage["id"] for stage in stages(admin)}
    first = tenant.stages.get(name="Nuevo")

    admin.put(ORDER_URL, {"stages": list(reversed(ids.values()))}, format="json")
    admin.delete(f"{stage_url(ids['Nuevo'])}?move_to={ids['Cliente']}")

    contact.refresh_from_db()
    assert contact.updated_at > before
    assert tenant.stages.get(name="Cliente").updated_at > first.updated_at
