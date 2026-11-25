# Расписание отдельно от ленты дня и задания отчёта. Конец потока не меняет.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("journal", "0005_callsign_label"),
    ]

    operations = [
        migrations.CreateModel(
            name="TrainingEvent",
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
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="создано"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="обновлено"),
                ),
                (
                    "import_key",
                    models.CharField(max_length=80, unique=True, verbose_name="ключ"),
                ),
                ("starts_on", models.DateField(verbose_name="начало")),
                (
                    "ends_on",
                    models.DateField(blank=True, null=True, verbose_name="конец"),
                ),
                (
                    "starts_at",
                    models.TimeField(blank=True, null=True, verbose_name="время"),
                ),
                ("title", models.CharField(max_length=200, verbose_name="название")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("exercise", "упражнение"),
                            ("call", "созвон"),
                            ("meeting", "очная встреча"),
                            ("week", "итоги недели"),
                            ("weekend", "уикенд"),
                            ("notice", "объявление"),
                        ],
                        max_length=16,
                        verbose_name="вид",
                    ),
                ),
                ("description", models.TextField(blank=True, verbose_name="описание")),
                ("url", models.URLField(blank=True, max_length=500, verbose_name="ссылка")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("preliminary", "предварительно"),
                            ("confirmed", "подтверждено"),
                        ],
                        default="confirmed",
                        max_length=16,
                        verbose_name="статус",
                    ),
                ),
                (
                    "source",
                    models.CharField(blank=True, max_length=40, verbose_name="источник"),
                ),
                (
                    "changed_on",
                    models.DateField(blank=True, null=True, verbose_name="уточнено"),
                ),
            ],
            options={
                "verbose_name": "событие расписания",
                "verbose_name_plural": "расписание",
                "ordering": ["starts_on", "starts_at", "pk"],
            },
        ),
    ]
