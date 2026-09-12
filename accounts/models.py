from django.contrib.auth.models import AbstractUser
from django.db import models


class Team(models.Model):
    """Команда — рабочая единица. Команды изолированы друг от друга,
    сквозная видимость только у владельца (owner override)."""
    name = models.CharField(max_length=100, unique=True, verbose_name="Название команды")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Команда"
        verbose_name_plural = "Команды"

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Кастомная модель пользователя вместо django.contrib.auth.User.
    Решение принято в диалоге 20_БАЗА_ДАННЫХ: свап AUTH_USER_MODEL
    дёшев сейчас (новый проект, миграций ещё нет), а после появления
    реальных данных — дорог. Зафиксировать в ШТАБ.

    Поля name/telegram_id/team/description/access_revoked — по
    структуре из 90_АДМИНИСТРИРОВАНИЕ_роли_и_доступы.md (v0.2).
    AbstractUser уже даёт username/password/email — этого достаточно
    для входа в систему, доп.поля из документа добавлены поверх.
    """
    
    telegram_id = models.CharField(
        max_length=64, blank=True, null=True,
        verbose_name="Telegram ID", help_text="Для раздачи лидов через бота"
    )
    # Допущение из документа: один пользователь = одна команда.
    # Если понадобится членство в нескольких — выносить в team_members.
    team = models.ForeignKey(
        Team, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="members", verbose_name="Команда"
    )
    description = models.TextField(blank=True, null=True, verbose_name="Карточка пользователя")
    access_revoked = models.BooleanField(
        default=False, verbose_name="Доступ отозван",
        help_text="Ручной отзыв доступа владельцем (owner override)"
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return self.name or self.username

    @property
    def name(self):
        return self.get_full_name() or self.username
    
    def clean(self):
            from django.core.exceptions import ValidationError
            super().clean()
            if self.is_staff and not self.is_superuser and not self.team_id:
                raise ValidationError({
                    "team": "Укажите команду. Менеджера/сотрудника без команды создавать нельзя."
                    })
                    


class UserCapability(models.Model):
    """Одна запись = одна способность пользователя. Роли комбинируемые,
    не эксклюзивные (менеджер команды может быть и оператором)."""

    class Capability(models.TextChoices):
        OWNER = "owner", "Владелец"
        COLLECTOR = "collector", "Сборщик данных"
        OUTREACH = "outreach", "Outreach"
        SALES = "sales", "Продажи"
        TEAM_MANAGER = "team_manager", "Руководитель команды"
        OPERATOR = "operator", "Оператор"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="capabilities")
    capability = models.CharField(max_length=20, choices=Capability.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Способность пользователя"
        verbose_name_plural = "Способности пользователей"
        # Не в исходном документе — добавлено, чтобы нельзя было
        # дважды выдать одну и ту же способность одному пользователю.
        unique_together = ("user", "capability")

    def __str__(self):
        return f"{self.user} — {self.get_capability_display()}"


class AccessAuditLog(models.Model):
    """Общий журнал действий. Дублирует функцию StageChangeLog —
    смены stage лида логируются сюда же (action='lead_status_changed',
    target_type='lead'), отдельная модель истории воронки не нужна."""
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="audit_entries"
    )
    action = models.CharField(
        max_length=100,
        help_text="lead_status_changed, access_revoked, role_added, ..."
    )
    target_type = models.CharField(
        max_length=50,
        help_text="lead, user, team, ..."
    )
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
