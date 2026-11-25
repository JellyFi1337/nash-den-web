# Подпись поля callsign: «позывной» → «качество дня» (решение 034). Имя поля не меняется.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("journal", "0004_section06_modes_and_roles"),
    ]

    operations = [
        migrations.AlterField(
            model_name="entry",
            name="callsign",
            field=models.CharField(blank=True, max_length=80, verbose_name="качество дня"),
        ),
    ]
