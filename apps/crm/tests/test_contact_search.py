"""
Searching and filtering the contacts of a business by name, phone, stage, tags and person in
charge, for any member of the business.
"""

import uuid

import pytest
from wanps.messaging.models import App

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.crm.models import Contact, Stage, Tag
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for

CONTACTS_URL = "/api/v1/crm/contacts/"


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def link(tenant, meta_app):
    return add_account(tenant, meta_app, "111")


@pytest.fixture
def member(tenant):
    return client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))


def contact_of(link, phone, channel_name):
    add_message(link, phone, "Hola", contact_name=channel_name)
    return Contact.objects.get(account=link.account, external_id=phone)


def found(member, **query):
    response = member.get(CONTACTS_URL, query)
    assert response.status_code == 200
    return {contact["contact_id"] for contact in response.data["data"]["contacts"]}


def tag(tenant, name, *contacts):
    new = Tag.objects.create(tenant=tenant, name=name)
    for contact in contacts:
        contact.tags.add(new)
    return new


@pytest.mark.parametrize("role", Membership.Role.values)
def test_searching_by_part_of_a_name_finds_the_contacts_whatever_the_capitalization(
    tenant, link, role
):
    contact_of(link, "593990000001", "Ana Paz")
    luis = contact_of(link, "593990000002", "Luis Gil")
    contact_of(link, "593990000003", "Eva Soto")
    # The name the team wrote is the one the team sees, so the channel's name no longer counts
    luis.name = "Doctor Marcos"
    luis.save()
    any_member = client_for(add_member(tenant, "any@acme.test", role))

    assert found(any_member, search="ANA P") == {"593990000001"}
    assert found(any_member, search="marcos") == {"593990000002"}
    assert found(any_member, search="luis") == set()


def test_searching_by_part_of_a_phone_finds_the_phone_written_by_the_team_and_the_whatsapp_one(
    tenant, link, member
):
    contact_of(link, "593990000001", "Ana")
    written = contact_of(link, "593990000002", "Luis")
    written.phone = "+593 98 765 4321"
    written.save()

    assert found(member, search="0000001") == {"593990000001"}
    assert found(member, search="765 43") == {"593990000002"}


def test_a_search_that_matches_nothing_gives_an_empty_list(link, member):
    contact_of(link, "593990000001", "Ana")

    response = member.get(CONTACTS_URL, {"search": "zzz"})

    assert response.status_code == 200
    assert response.data["data"] == {"contacts": [], "has_more": False}


def test_filtering_by_tags_gives_the_contacts_that_have_all_of_them(tenant, link, member):
    ana = contact_of(link, "593990000001", "Ana")
    luis = contact_of(link, "593990000002", "Luis")
    contact_of(link, "593990000003", "Eva")
    vip = tag(tenant, "VIP", ana, luis)
    wholesale = tag(tenant, "Mayorista", ana)

    assert found(member, tag=[str(vip.pk)]) == {"593990000001", "593990000002"}
    assert found(member, tag=[str(vip.pk), str(wholesale.pk)]) == {"593990000001"}


def test_filtering_by_person_in_charge_or_by_nobody(tenant, link, member):
    ana = contact_of(link, "593990000001", "Ana")
    contact_of(link, "593990000002", "Luis")
    contact_of(link, "593990000003", "Eva")
    carla = add_member(tenant, "carla@acme.test", Membership.Role.AGENT)
    ana.assigned_to = carla
    ana.save()

    assert found(member, assigned_to=str(carla.pk)) == {"593990000001"}
    assert found(member, assigned_to="none") == {"593990000002", "593990000003"}


def test_filters_together_narrow_the_result(tenant, link, member):
    ana = contact_of(link, "593990000001", "Ana")
    luis = contact_of(link, "593990000002", "Luis")
    contact_of(link, "593990000003", "Anabel")
    carla = add_member(tenant, "carla@acme.test", Membership.Role.AGENT)
    interested = Stage.objects.get(tenant=tenant, name="Interesado")
    vip = tag(tenant, "VIP", ana, luis)
    for contact in (ana, luis):
        contact.stage = interested
        contact.assigned_to = carla
        contact.save()

    everything = {
        "search": "an",
        "stage": str(interested.pk),
        "tag": [str(vip.pk)],
        "assigned_to": str(carla.pk),
    }

    assert found(member, **everything) == {"593990000001"}
    assert found(member, **{**everything, "search": "luis"}) == {"593990000002"}
    assert found(member, **{**everything, "search": "eva"}) == set()


def test_the_filtered_list_is_paged(link, member):
    for number in range(3):
        contact_of(link, f"59399000000{number}", f"Ana {number}")
    contact_of(link, "593990000009", "Luis")

    first = member.get(CONTACTS_URL, {"search": "ana", "limit": 2}).data["data"]
    second = member.get(CONTACTS_URL, {"search": "ana", "limit": 2, "offset": 2}).data["data"]

    assert (len(first["contacts"]), first["has_more"]) == (2, True)
    assert (len(second["contacts"]), second["has_more"]) == (1, False)


def test_the_contacts_of_another_business_never_match(tenant, meta_app, link, member):
    contact_of(link, "593990000001", "Ana")
    rival = Tenant.objects.create(name="Rival Clinic")
    theirs = contact_of(add_account(rival, meta_app, "222"), "593990000009", "Ana Rival")
    tag(rival, "VIP", theirs)

    assert found(member, search="ana") == {"593990000001"}
    assert found(member, search="rival") == set()


@pytest.mark.parametrize("filter_name", ["stage", "tag", "assigned_to"])
def test_a_stage_tag_or_member_of_another_business_or_that_does_not_exist_is_rejected(
    tenant, meta_app, link, member, filter_name
):
    contact_of(link, "593990000001", "Ana")
    rival = Tenant.objects.create(name="Rival Clinic")
    theirs = {
        "stage": Stage.objects.get(tenant=rival, name="Cliente"),
        "tag": Tag.objects.create(tenant=rival, name="VIP"),
        "assigned_to": add_member(rival, "boss@rival.test", Membership.Role.ADMIN),
    }[filter_name]

    for value in (str(theirs.pk), str(uuid.uuid4())):
        query = {filter_name: [value] if filter_name == "tag" else value}
        response = member.get(CONTACTS_URL, query)

        assert response.status_code == 400
        assert filter_name in response.data["errors"]
