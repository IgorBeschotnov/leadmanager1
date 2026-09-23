# Generated manually to match applied schema on server

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='bot_token',
            field=models.CharField(
                default='',  # уже применено на сервере; для новых инстансов можно убрать после
                help_text='Обязателен. Отдельный бот этой организации.',
                max_length=100,
                verbose_name='Токен Telegram-бота',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='team',
            name='bot_username',
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name='@username бота',
            ),
        ),
        migrations.AddField(
            model_name='team',
            name='access_password_word',
            field=models.CharField(
                blank=True,
                help_text='Простое слово; запрос раз в неделю в owner-боте',
                max_length=50,
                verbose_name='Слово-пароль для продления',
            ),
        ),
        migrations.AddField(
            model_name='team',
            name='access_valid_until',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Доступ к приложению до',
            ),
        ),
    ]