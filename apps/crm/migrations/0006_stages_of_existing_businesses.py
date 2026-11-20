from django.db import migrations

# As they were when this ran: the stages every business starts with
DEFAULT_STAGES = ["Nuevo", "En conversación", "Interesado", "Cliente", "Perdido"]


def create_stages(apps, schema_editor):
    """
    Give the default stages to every business that has none, and put in the first one every
    contact that has no stage. Deleted businesses too, so a restored one has its pipeline.
    """
    Tenant = apps.get_model("tenants", "Tenant")
    Stage = apps.get_model("crm", "Stage")
    Contact = apps.get_model("crm", "Contact")

    have_stages = set(Stage._base_manager.values_list("tenant_id", flat=True))
    Stage._base_manager.bulk_create(
        Stage(tenant_id=tenant_id, name=name, position=position)
        for tenant_id in Tenant._base_manager.exclude(pk__in=have_stages).values_list(
            "pk", flat=True
        )
        for position, name in enumerate(DEFAULT_STAGES)
    )
    first_of = {}
    for stage in Stage._base_manager.order_by("-position"):
        first_of[stage.tenant_id] = stage.pk
    for tenant_id, stage_id in first_of.items():
        Contact._base_manager.filter(tenant_id=tenant_id, stage__isnull=True).update(
            stage_id=stage_id
        )


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0005_contact_stage"),
        ("tenants", "0005_tenant_suspended_at"),
    ]

    operations = [
        migrations.RunPython(create_stages, migrations.RunPython.noop),
    ]
