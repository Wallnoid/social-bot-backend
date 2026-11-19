from django.db import migrations

BATCH_SIZE = 1000


def create_contacts(apps, schema_editor):
    """
    Give a contact to every chat that already exists in an account that belongs to a business.

    Chats of disconnected accounts count too: their link is deleted but the client stays a
    client of the business. A chat that already has its contact is left as it is.
    """
    ChannelAccount = apps.get_model("channels", "ChannelAccount")
    Message = apps.get_model("messaging", "Message")
    Contact = apps.get_model("crm", "Contact")

    tenant_of = dict(ChannelAccount._base_manager.values_list("account_id", "tenant_id"))
    have_one = set(Contact._base_manager.values_list("account_id", "external_id"))
    chats = (
        Message._base_manager.filter(account_id__in=tenant_of)
        .order_by()
        .values_list("account_id", "contact_id")
        .distinct()
    )
    # In batches, so a big database never holds every new contact in memory at once
    batch = []
    for account_id, contact_id in chats.iterator():
        if (account_id, contact_id) in have_one:
            continue
        batch.append(
            Contact(tenant_id=tenant_of[account_id], account_id=account_id, external_id=contact_id)
        )
        if len(batch) == BATCH_SIZE:
            save(Contact, batch)
            batch = []
    save(Contact, batch)


def save(model, contacts):
    # A new message may create a contact while this runs (the app is still serving)
    model.objects.bulk_create(contacts, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("channels", "0008_handover"),
        ("crm", "0001_initial"),
        ("messaging", "0003_longer_message_external_id"),
    ]

    operations = [
        migrations.RunPython(create_contacts, migrations.RunPython.noop),
    ]
