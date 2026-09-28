# Generated manually — capability servant
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_user_public_photo_alter_user_public_photo_url"),
    ]

    operations = [
        migrations.AlterField(
            model_name="usercapability",
            name="capability",
            field=models.CharField(
                choices=[
                    ("owner", "Владелец"),
                    ("collector", "Сборщик данных"),
                    ("outreach", "Outreach"),
                    ("sales", "Продажи"),
                    ("team_manager", "Руководитель / менеджер команды"),
                    ("operator", "Оператор"),
                    ("servant", "Служитель (только сайт)"),
                ],
                max_length=20,
            ),
        ),
    ]
