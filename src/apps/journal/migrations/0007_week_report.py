from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("journal", "0006_training_event"),
    ]

    operations = [
        migrations.CreateModel(
            name="WeekReport",
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
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="обновлено")),
                (
                    "week",
                    models.PositiveSmallIntegerField(unique=True, verbose_name="неделя потока"),
                ),
                (
                    "payload",
                    models.JSONField(blank=True, default=dict, verbose_name="текст недели"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "черновик"), ("published", "опубликован")],
                        default="draft",
                        max_length=16,
                        verbose_name="статус",
                    ),
                ),
                (
                    "warnings",
                    models.JSONField(blank=True, default=list, verbose_name="предупреждения"),
                ),
                ("notes", models.JSONField(blank=True, default=list, verbose_name="заметки")),
                (
                    "published_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="опубликован"),
                ),
                (
                    "uploaded_via",
                    models.CharField(
                        choices=[("bot", "бот"), ("admin", "админка"), ("command", "команда")],
                        default="admin",
                        max_length=16,
                        verbose_name="откуда",
                    ),
                ),
            ],
            options={
                "verbose_name": "неделя словами",
                "verbose_name_plural": "недели словами",
                "ordering": ["-week"],
            },
        ),
    ]
