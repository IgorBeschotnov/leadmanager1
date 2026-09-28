# Generated manually for leadmanager1 decisions patch
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leads", "0003_alter_datasource_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="calllog",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("call", "Звонок"),
                    ("template_generated", "Шаблон сгенерирован"),
                    ("proposal_sent", "КП отправлено"),
                    ("stage_changed", "Смена статуса"),
                    ("partner_help", "Помощь партнёра"),
                ],
                db_index=True,
                default="call",
                max_length=30,
                verbose_name="Тип события",
            ),
        ),
        migrations.AlterField(
            model_name="calllog",
            name="result",
            field=models.CharField(
                choices=[
                    ("success", "Положительно (Ждет письмо/согласен)"),
                    ("call_back", "Перезвонить позже"),
                    ("refusal", "Отказ"),
                    ("wrong_number", "Неправильный номер / Нет связи"),
                    ("info", "Информация / служебное"),
                ],
                default="info",
                max_length=30,
                verbose_name="Результат",
            ),
        ),
        migrations.AddIndex(
            model_name="calllog",
            index=models.Index(fields=["event_type", "created_at"], name="leads_calll_event_t_idx"),
        ),
    ]
