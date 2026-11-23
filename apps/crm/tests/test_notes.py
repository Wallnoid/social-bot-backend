"""
The internal notes of a contact: the team writes them, reads them and keeps them; the clients
never see them.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from wanps.messaging.models import App

from apps.channels.tests.test_manage_accounts import add_account
from apps.conversations.tests.test_inbox import add_message
from apps.crm.models import Contact, Note
from apps.tenants.models import Membership, Tenant
from apps.tenants.tests.helpers import add_member, client_for


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme Dental")


@pytest.fixture
def meta_app(db):
    return App.objects.create(name="Social Bot", app_secret="app-secret", verify_token="verify")


@pytest.fixture
def contact(tenant, meta_app):
    add_message(add_account(tenant, meta_app, "111"), "593990000001", "Hola", contact_name="Ana")
    return Contact.objects.get()


def notes_url(contact):
    return f"/api/v1/crm/contacts/{contact.pk}/notes/"


def notes(member, contact):
    response = member.get(notes_url(contact))
    assert response.status_code == 200
    return response.data["data"]["notes"]


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_writes_a_note_and_sees_it_with_themselves_as_author(tenant, contact, role):
    membership = add_member(tenant, "member@acme.test", role, first_name="Eva", last_name="Rojas")
    member = client_for(membership)

    response = member.post(notes_url(contact), {"text": "Prefiere las tardes"}, format="json")

    assert response.status_code == 201
    [note] = notes(member, contact)
    assert note["id"] == response.data["data"]["id"]
    assert note["text"] == "Prefiere las tardes"
    assert note["author"] == {"id": str(membership.user_id), "name": "Eva Rojas"}
    assert note["created_at"] is not None


@pytest.fixture
def member(tenant):
    return client_for(add_member(tenant, "member@acme.test", Membership.Role.AGENT))


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_an_empty_note_is_rejected_and_nothing_is_saved(member, contact, text):
    response = member.post(notes_url(contact), {"text": text}, format="json")

    assert response.status_code == 400
    assert notes(member, contact) == []


def write_notes(member, contact, texts):
    """Write the notes in order, the first one the oldest (a day apart)."""
    for days_ago, text in zip(range(len(texts), 0, -1), texts, strict=True):
        note_id = member.post(notes_url(contact), {"text": text}, format="json").data["data"]["id"]
        Note.objects.filter(pk=note_id).update(created_at=timezone.now() - timedelta(days=days_ago))


def test_the_notes_come_latest_first_and_paged(member, contact):
    write_notes(member, contact, ["first", "second", "third"])

    page_1 = member.get(f"{notes_url(contact)}?limit=2").data["data"]
    page_2 = member.get(f"{notes_url(contact)}?limit=2&offset=2").data["data"]

    assert [note["text"] for note in page_1["notes"]] == ["third", "second"]
    assert page_1["has_more"] is True
    assert [note["text"] for note in page_2["notes"]] == ["first"]
    assert page_2["has_more"] is False


@pytest.mark.parametrize("role", Membership.Role.values)
def test_any_member_sees_the_notes_written_by_others_with_their_text_author_and_time(
    tenant, contact, role
):
    ana = add_member(
        tenant, "ana@acme.test", Membership.Role.AGENT, first_name="Ana", last_name="Paz"
    )
    luis = add_member(tenant, "luis@acme.test", Membership.Role.SUPERVISOR)
    write_notes(client_for(ana), contact, ["Quiere factura"])
    write_notes(client_for(luis), contact, ["Llamar el lunes"])
    reader = client_for(add_member(tenant, "reader@acme.test", role))

    found = notes(reader, contact)

    assert {(note["text"], note["author"]["name"]) for note in found} == {
        ("Quiere factura", "Ana Paz"),
        ("Llamar el lunes", "luis@acme.test"),
    }
    assert all(note["created_at"] for note in found)


def note_url(contact, note_id):
    return f"{notes_url(contact)}{note_id}/"


def write_note(member, contact, text):
    return member.post(notes_url(contact), {"text": text}, format="json").data["data"]["id"]


def test_the_author_edits_their_note_and_everyone_sees_the_change(tenant, member, contact):
    note_id = write_note(member, contact, "Quiere factura")
    other = client_for(add_member(tenant, "other@acme.test", Membership.Role.SUPERVISOR))

    response = member.patch(
        note_url(contact, note_id), {"text": "Quiere factura a nombre de Acme"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["data"]["text"] == "Quiere factura a nombre de Acme"
    assert [note["text"] for note in notes(other, contact)] == ["Quiere factura a nombre de Acme"]


def test_the_author_deletes_their_note_and_it_is_gone_for_everyone(tenant, member, contact):
    note_id = write_note(member, contact, "Quiere factura")
    keep = write_note(member, contact, "Llamar el lunes")
    other = client_for(add_member(tenant, "other@acme.test", Membership.Role.SUPERVISOR))

    response = member.delete(note_url(contact, note_id))

    assert response.status_code == 200
    assert [note["id"] for note in notes(other, contact)] == [keep]


def test_an_admin_deletes_the_note_of_another_member(tenant, member, contact):
    note_id = write_note(member, contact, "Quiere factura")
    admin = client_for(add_member(tenant, "admin@acme.test", Membership.Role.ADMIN))

    response = admin.delete(note_url(contact, note_id))

    assert response.status_code == 200
    assert notes(member, contact) == []


@pytest.mark.parametrize("role", Membership.Role.values)
def test_nobody_but_the_author_edits_a_note_and_only_an_admin_deletes_the_note_of_another(
    tenant, member, contact, role
):
    note_id = write_note(member, contact, "Quiere factura")
    other = client_for(add_member(tenant, "other@acme.test", role))

    edited = other.patch(note_url(contact, note_id), {"text": "Cambiado"}, format="json")
    deleted = other.delete(note_url(contact, note_id))

    assert edited.status_code == 403
    assert deleted.status_code == (200 if role == Membership.Role.ADMIN else 403)
    expected = [] if role == Membership.Role.ADMIN else [("Quiere factura")]
    assert [note["text"] for note in notes(member, contact)] == expected


def test_the_contact_and_the_notes_of_another_business_are_not_found_and_do_not_change(
    meta_app, member
):
    rival = Tenant.objects.create(name="Rival Clinic")
    add_message(add_account(rival, meta_app, "222"), "593990000009", "Hola", contact_name="Zoe")
    theirs = Contact.objects.get(tenant=rival)
    their_admin = client_for(add_member(rival, "boss@rival.test", Membership.Role.ADMIN))
    their_note = write_note(their_admin, theirs, "Secreto del rival")

    assert member.get(notes_url(theirs)).status_code == 404
    assert member.post(notes_url(theirs), {"text": "Mine now"}, format="json").status_code == 404
    patched = member.patch(note_url(theirs, their_note), {"text": "Hacked"}, format="json")
    assert patched.status_code == 404
    assert member.delete(note_url(theirs, their_note)).status_code == 404
    assert [note["text"] for note in notes(their_admin, theirs)] == ["Secreto del rival"]


def test_the_notes_of_a_deleted_contact_are_not_found_to_read_edit_or_delete(member, contact):
    note_id = write_note(member, contact, "Quiere factura")
    contact.delete()

    assert member.get(notes_url(contact)).status_code == 404
    edited = member.patch(note_url(contact, note_id), {"text": "Cambiado"}, format="json")
    assert edited.status_code == 404
    assert member.delete(note_url(contact, note_id)).status_code == 404
    assert Note.objects.get(pk=note_id).text == "Quiere factura"


def test_a_note_longer_than_5000_characters_is_rejected_and_one_of_5000_is_saved(member, contact):
    too_long = member.post(notes_url(contact), {"text": "a" * 5001}, format="json")
    just_enough = member.post(notes_url(contact), {"text": "a" * 5000}, format="json")

    assert too_long.status_code == 400
    assert just_enough.status_code == 201
    assert [len(note["text"]) for note in notes(member, contact)] == [5000]
