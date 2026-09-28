from django.contrib.auth.models import AbstractUser
from django.db import models


class Team(models.Model):
    """Команда — рабочая единица. Команды изолированы друг от друга,
    сквозная видимость только у владельца (owner override)."""
    name = models.CharField(max_length=100, unique=True, verbose_name="Название команды")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    created_at = models.DateTimeField(auto_now_add=True)
    bot_token = models.CharField(
        max_length=100,
        verbose_name="Токен Telegram-бота",
        help_text="Обязателен. Отдельный бот этой организации.",
    )
    bot_username = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="@username бота",
    )
    access_password_word = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Слово-пароль для продления",
        help_text="Простое слово; запрос раз в неделю в owner-боте",
    )
    access_valid_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Доступ к приложению до",
    )

    class Meta:
        verbose_name = "Команда"
        verbose_name_plural = "Команды"

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if not self.bot_token:
            raise ValidationError({
                "bot_token": "Укажите токен бота команды."
            })


class User(AbstractUser):
    """Кастомная модель пользователя.

    Один пользователь = одна команда.
    servant — только публичная карточка на сайте, без прав в кабинете.
    """

    telegram_id = models.CharField(
        max_length=64, blank=True, null=True,
        verbose_name="Telegram ID", help_text="Для раздачи лидов через бота"
    )
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="members", verbose_name="Команда"
    )
    description = models.TextField(blank=True, null=True, verbose_name="Карточка пользователя")
    access_revoked = models.BooleanField(
        default=False, verbose_name="Доступ отозван",
        help_text="Ручной отзыв доступа владельцем (owner override)"
    )

    is_public_profile = models.BooleanField(
        default=False, verbose_name="Показувати картку на сайті",
        help_text="Увімкни, щоб людина зʼявилась у блоці «Команда» на публічній сторінці"
    )
    public_role_title = models.CharField(
        max_length=100, blank=True, verbose_name="Посада для сайту",
        help_text="Людська назва ролі для відвідувачів сайту"
    )
    public_photo_url = models.URLField(
        blank=True, verbose_name="Фото — посилання (запасний варіант)",
    )
    public_photo = models.ImageField(
        upload_to="staff/", blank=True, null=True,
        verbose_name="Фото — файл",
    )
    public_order = models.PositiveIntegerField(
        default=0, verbose_name="Порядок на сайті",
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return self.name or self.username

    @property
    def name(self):
        return self.get_full_name() or self.username

    def has_capability(self, code: str) -> bool:
        return self.capabilities.filter(capability=code).exists()

    def is_owner(self) -> bool:
        return self.has_capability(UserCapability.Capability.OWNER)

    def is_servant_only(self) -> bool:
        """Только servant без рабочих ролей — нет доступа в кабинет."""
        caps = set(self.capabilities.values_list("capability", flat=True))
        if not caps:
            return False
        work = {
            UserCapability.Capability.OWNER,
            UserCapability.Capability.TEAM_MANAGER,
            UserCapability.Capability.OPERATOR,
            UserCapability.Capability.COLLECTOR,
            UserCapability.Capability.OUTREACH,
            UserCapability.Capability.SALES,
        }
        return UserCapability.Capability.SERVANT in caps and not (caps & work)

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.is_staff and not self.is_superuser and not self.team_id:
            # servant без team допустим
            has_servant = False
            if self.pk:
                has_servant = self.capabilities.filter(
                    capability=UserCapability.Capability.SERVANT
                ).exists()
            if not has_servant:
                raise ValidationError({
                    "team": "Укажите команду. Менеджера/сотрудника без команды создавать нельзя."
                })


class UserCapability(models.Model):
    """Роли комбинируемые.

    Рабочие: owner, team_manager, operator.
    servant — только публичная карточка.
    collector/outreach/sales — резерв, пока не проверяем.
    """

    class Capability(models.TextChoices):
        OWNER = "owner", "Владелец"
        COLLECTOR = "collector", "Сборщик данных"
        OUTREACH = "outreach", "Outreach"
        SALES = "sales", "Продажи"
        TEAM_MANAGER = "team_manager", "Руководитель / менеджер команды"
        OPERATOR = "operator", "Оператор"
        SERVANT = "servant", "Служитель (только сайт)"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="capabilities")
    capability = models.CharField(max_length=20, choices=Capability.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Способность пользователя"
        verbose_name_plural = "Способности пользователей"
        unique_together = ("user", "capability")

    def __str__(self):
        return f"{self.user} — {self.get_capability_display()}"


class AccessAuditLog(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="audit_entries"
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=50)
    target_id = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Запись аудита"
        verbose_name_plural = "Журнал аудита"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self):
        return f"{self.action} — {self.target_type}#{self.target_id}"
