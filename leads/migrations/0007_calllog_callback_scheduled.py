from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leads", "0006_company_address")]
    operations = [
        migrations.AlterField(
            model_name="calllog",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("call", "Звонок"),
                    ("template_generated", "Шаблон сгенерирован"),
                    ("communication_sent", "Сообщение отправлено"),
                    ("callback_scheduled", "Следующий звонок назначен"),
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
    ]
