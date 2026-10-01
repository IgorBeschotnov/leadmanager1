from django.db import migrations, models


def initialize_next_actions(apps, schema_editor):
    Company = apps.get_model("leads", "Company")
    for lead in Company.objects.all().iterator():
        if lead.stage == "new" or lead.stage == "in_progress":
            action = "call"
        elif lead.stage == "letter_sent" and not lead.is_sent_by_manager:
            action = "prepare_proposal"
        elif lead.stage == "letter_sent":
            action = "follow_up"
        elif lead.stage == "success":
            action = "thank_partner"
        else:
            action = "none"
        Company.objects.filter(pk=lead.pk).update(next_action=action)


class Migration(migrations.Migration):
    dependencies = [("leads", "0007_calllog_callback_scheduled")]
    operations = [
        migrations.AddField(
            model_name="company",
            name="next_action",
            field=models.CharField(
                choices=[
                    ("call", "Зателефонувати"),
                    ("prepare_proposal", "Підготувати й надіслати КП"),
                    ("follow_up", "Перевірити відповідь / передзвонити"),
                    ("thank_partner", "Подякувати партнеру"),
                    ("contact_partner", "Зв’язатися з партнером"),
                    ("none", "Немає наступної дії"),
                ],
                db_index=True,
                default="call",
                max_length=24,
                verbose_name="Наступна дія",
            ),
        ),
        migrations.RunPython(initialize_next_actions, migrations.RunPython.noop),
    ]
