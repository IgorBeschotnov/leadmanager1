from django.conf import settings
from django.db import models

PUBLIC_FORM_SOURCE = "Заявка з сайту"


class Category(models.Model):
    """10–20 категорий достаточно (не КВЭД). Наполнение через админку."""
    name = models.CharField(max_length=100, unique=True, verbose_name="Название категории")

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name


class Company(models.Model):
    class NextAction(models.TextChoices):
        CALL = "call", "Зателефонувати"
        PREPARE_PROPOSAL = "prepare_proposal", "Підготувати й надіслати КП"
        FOLLOW_UP = "follow_up", "Перевірити відповідь / передзвонити"
        THANK_PARTNER = "thank_partner", "Подякувати партнеру"
        CONTACT_PARTNER = "contact_partner", "Зв’язатися з партнером"
        NONE = "none", "Немає наступної дії"

    name = models.CharField(max_length=255, verbose_name="Название компании")

    categories = models.ManyToManyField(
        Category, blank=True, related_name="companies",
        verbose_name="Виды деятельности"
    )
    city = models.CharField(max_length=100, blank=True, null=True, verbose_name="Город")
    region = models.CharField(max_length=100, blank=True, null=True, verbose_name="Область/регион")
    address = models.CharField(max_length=500, blank=True, null=True, verbose_name="Адрес")
    website = models.URLField(blank=True, null=True, verbose_name="Сайт")

    phones = models.CharField(max_length=500, blank=True, null=True, verbose_name="Телефон(ы)")
    phone_normalized = models.CharField(
        max_length=32, blank=True, null=True, db_index=True,
        verbose_name="Телефон (нормализованный)",
        help_text="Только цифры из первого номера. Мягкий дедуп."
    )
    emails = models.CharField(max_length=500, blank=True, null=True, verbose_name="Email(ы)")
    contact_person = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Контактное лицо"
    )

    source = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="Источник данных"
    )

    internal_notes = models.TextField(
        blank=True, null=True,
        verbose_name="Заметки / специфика компании"
    )

    preferred_channel = models.CharField(
        max_length=50, blank=True, null=True,
        verbose_name="Канал отправки предложения"
    )
    is_sent_by_manager = models.BooleanField(
        default=False,
        verbose_name="КП отправлено менеджером"
    )
    callback_date = models.DateTimeField(
        blank=True, null=True,
        verbose_name="Дата перезвона",
        help_text="По умолчанию +3 дня после КП; менеджер может менять."
    )

    next_action = models.CharField(
        max_length=24,
        choices=NextAction.choices,
        default=NextAction.CALL,
        db_index=True,
        verbose_name="Наступна дія",
    )

    STAGE_CHOICES = [
        ('new', 'Новый'),
        ('in_progress', 'В работе'),
        ('letter_sent', 'Ждет отправки письма / КП'),
        ('success', 'Партнёр'),
        ('refusal', 'Отказ'),
        ('invalid', 'Невалидный / Ошибка'),
    ]
    stage = models.CharField(
        max_length=20, choices=STAGE_CHOICES, default='new',
        verbose_name="Статус воронки"
    )

    team = models.ForeignKey(
        "accounts.Team",
        on_delete=models.PROTECT, null=True, blank=True,
        related_name="leads", verbose_name="Команда"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Закреплен за оператором", related_name="active_leads"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Компания"
        verbose_name_plural = "Компании"
        indexes = [
            models.Index(fields=["team", "stage"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_stage_display()})"

    @property
    def first_phone(self):
        if not self.phones:
            return None
        return self.phones.split(',')[0].strip()

    def _normalize_first_phone(self):
        if not self.phones:
            return None
        raw = self.phones.split(',')[0]
        digits = ''.join(ch for ch in raw if ch.isdigit())
        return digits or None

    def save(self, *args, force_team_change=False, **kwargs):
        if self.pk:
            old_team_id = (
                Company.objects.filter(pk=self.pk)
                .values_list("team_id", flat=True)
                .first()
            )
            if old_team_id and self.team_id and old_team_id != self.team_id and not force_team_change:
                raise ValueError(
                    "Команда лида неизменяема после назначения. "
                    "Используйте save(force_team_change=True) для owner override."
                )
        self.phone_normalized = self._normalize_first_phone()
        super().save(*args, **kwargs)


class CallLog(models.Model):
    """Универсальная история. Статистика звонков = только event_type=call."""

    class EventType(models.TextChoices):
        CALL = "call", "Звонок"
        TEMPLATE_GENERATED = "template_generated", "Шаблон сгенерирован"
        COMMUNICATION_SENT = "communication_sent", "Сообщение отправлено"
        CALLBACK_SCHEDULED = "callback_scheduled", "Следующий звонок назначен"
        PROPOSAL_SENT = "proposal_sent", "КП отправлено"
        STAGE_CHANGED = "stage_changed", "Смена статуса"
        PARTNER_HELP = "partner_help", "Помощь партнёра"

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE,
        related_name="call_logs", verbose_name="Компания"
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        verbose_name="Оператор / автор"
    )
    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices,
        default=EventType.CALL,
        db_index=True,
        verbose_name="Тип события",
    )

    RESULT_CHOICES = [
        ('success', 'Положительно (Ждет письмо/согласен)'),
        ('call_back', 'Перезвонить позже'),
        ('refusal', 'Отказ'),
        ('wrong_number', 'Неправильный номер / Нет связи'),
        ('info', 'Информация / служебное'),
    ]
    result = models.CharField(
        max_length=30, choices=RESULT_CHOICES, default="info",
        verbose_name="Результат"
    )
    comment = models.TextField(blank=True, null=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время")

    class Meta:
        verbose_name = "История события"
        verbose_name_plural = "История событий"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.get_event_type_display()} → {self.company.name} "
            f"({self.created_at.strftime('%d.%m %H:%M')})"
        )


class DataSource(models.Model):
    """
    Источник базы. Открыт для Team в teams.
    Сырые (team=NULL) видны команде только после открытия source.
    Две команды могут брать из одной базы; чужие team не трогают.
    """
    key = models.CharField(
        max_length=255, unique=True,
        verbose_name="Ключ источника",
        help_text="Должен совпадать с Company.source",
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Название")
    teams = models.ManyToManyField(
        "accounts.Team", blank=True, related_name="data_sources",
        verbose_name="Открыт для команд",
        help_text="Пусто = закрыт для всех.",
    )
    notes = models.TextField(blank=True, verbose_name="Заметки")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Источник данных"
        verbose_name_plural = "Источники данных"
        ordering = ["key"]

    def __str__(self):
        n = self.teams.count()
        status = "закрыт" if n == 0 else f"открыт для {n} ком."
        return f"{self.title or self.key} ({status})"

    @property
    def is_released(self):
        return self.teams.exists()
