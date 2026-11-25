# В 0002 у updated_at подпись «изменено», а TimeStampedModel задаёт «обновлено».

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("access", "0002_codedelivery"),
    ]

    operations = [
        migrations.AlterField(
            model_name="codedelivery",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="обновлено"),
        ),
    ]
