# Конец потока — 22.11.2026 (решение 036). Старое значение по умолчанию 17.11
# заменяется только у тех записей, где оно ещё стоит. Другая дата — выбор владельца.

import datetime

from django.db import migrations, models

OLD_END = datetime.date(2026, 11, 17)
NEW_END = datetime.date(2026, 11, 22)


def move_old_default_forward(apps, schema_editor):
    del schema_editor
    site_config = apps.get_model("core", "SiteConfig")
    site_config.objects.filter(stream_end=OLD_END).update(stream_end=NEW_END)


def move_new_default_back(apps, schema_editor):
    del schema_editor
    site_config = apps.get_model("core", "SiteConfig")
    site_config.objects.filter(stream_end=NEW_END).update(stream_end=OLD_END)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_report_schema"),
    ]

    operations = [
        migrations.AlterField(
            model_name="siteconfig",
            name="stream_end",
            field=models.DateField(default=NEW_END, verbose_name="конец потока"),
        ),
        migrations.RunPython(move_old_default_forward, move_new_default_back),
    ]
