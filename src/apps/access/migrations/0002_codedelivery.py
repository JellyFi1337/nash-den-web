import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("team", "0004_section06_modes_and_roles"),
        ("access", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CodeDelivery",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="изменено")),
                ("day", models.DateField(verbose_name="день")),
                ("revision", models.PositiveIntegerField(verbose_name="версия")),
                (
                    "member",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="code_deliveries",
                        to="team.member",
                        verbose_name="участник",
                    ),
                ),
            ],
            options={
                "verbose_name": "доставка кода",
                "verbose_name_plural": "доставки кода",
            },
        ),
        migrations.AddConstraint(
            model_name="codedelivery",
            constraint=models.UniqueConstraint(
                fields=("day", "revision", "member"),
                name="code_delivery_once",
            ),
        ),
    ]
