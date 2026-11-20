import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0006_stages_of_existing_businesses"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contact",
            name="stage",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="contacts",
                to="crm.stage",
            ),
        ),
    ]
