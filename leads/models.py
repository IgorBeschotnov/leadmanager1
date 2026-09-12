from django.conf import settings
from django.db import models


class Category(models.Model):
    """Вид деятельности компании. Многие-ко-многим на Company —
    один лид может подходить под несколько категорий КП."""
    name = models.CharField(max_length=100, unique=True, verbose_name="Название категории")

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name


class Company(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название компании")

    # --- Классификация ---
    categories = models.ManyToManyField(
        Category, blank=True, related_name="companies",
        verbose_name="Виды деятельности"
    )
    city = models.CharField(max_length=100, blank=True, null=True, verbose_name="Город")
    region = models.CharField(max_length=100, blank=True, null=True, verbose_name="Область/регион")
    website = models.URLField(blank=True, null=True, verbose_name="Сайт")

    # Телефоны и почты — плоским текстом, несколько штук через запятую.
    # Полноценная нормализация (разбивка на отдельные записи) — задача
    # внешнего скрипта позже, когда база будет большой. phone_normalized
    # ниже — минимальный дедуп-помощник, а не замена этой задачи.
    phones = models.CharField(max_length=500, blank=True, null=True, verbose_name="Телефон(ы)")
    phone_normalized = models.CharField(
        max_length=32, blank=True, null=True, db_index=True,
        verbose_name="Телефон (нормализованный)",
        help_text="Только цифры из первого номера в phones. Для мягкой сверки "
                   "дублей на этапе тёплого звонка — без строгого unique."
    )
    emails = models.CharField(max_length=500, blank=True, null=True, verbose_name="Email(ы)")
    contact_person = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Контактное лицо"
    )

    source = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="Источник данных"
    )
    # откуда взят лид: сайт/скрапер + регион, например
    # "business-guide.com.ua — Вінницька область". Заполняется импортёрами/скраперами.

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
        verbose_name="Дата авто-перезвона (+3 дня)"
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

    # --- Команда и ответственный ---
    # Новый лид создаётся с team=None (сырой пул). Team проставляется,
    # когда конкретный менеджер создаёт по лиду карточку — и дальше
    # неизменна (см. save()), кроме owner override.
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
        """Первый номер из строки — то, что раньше давал contacts.first().phone."""
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
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE,
        related_name="call_logs", verbose_name="Компания"
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        verbose_name="Оператор"
    )

    RESULT_CHOICES = [
        ('success', 'Положительно (Ждет письмо/согласен)'),
        ('call_back', 'Перезвонить позже'),
        ('refusal', 'Отказ'),
        ('wrong_number', 'Неправильный номер / Нет связи'),
    ]
    result = models.CharField(max_length=30, choices=RESULT_CHOICES, verbose_name="Результат звонка")
    comment = models.TextField(blank=True, null=True, verbose_name="Комментарий оператора")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время звонка")

    class Meta:
        verbose_name = "История звонка"
        verbose_name_plural = "История звонков"

    def __str__(self):
        return f"Звонок в {self.company.name} — {self.get_result_display()} ({self.created_at.strftime('%d.%m %H:%M')})"

class DataSource(models.Model):
    """
    Источник базы (значение Company.source).
    is_released=True → лиды этого источника видны команде и боту.
    """
    key = models.CharField(
        max_length=255, unique=True,
        verbose_name="Ключ источника",
        help_text="Должен совпадать с Company.source",
    )
    title = models.CharField(
        max_length=255, blank=True,
        verbose_name="Название (для удобства)",
    )
    # Кому открыт этот источник
    teams = models.ManyToManyField(
        "accounts.Team",
        blank=True,
        related_name="data_sources",
        verbose_name="Открыт для команд",
        help_text="Пусто = закрыт для всех. Добавь команду — она увидит лиды.",
    )
    notes = models.TextField(blank=True, verbose_name="Заметки")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Источник данных"
        verbose_name_plural = "Источники данных"
        ordering = ["key"]

    def __str__(self):
        n = self.teams.count()
        if n == 0:
            status = "закрыт"
        else:
            status = f"открыт для {n} ком."
        return f"{self.title or self.key} ({status})"

    @property
    def is_released(self):
        return self.teams.exists()
    
    teams = models.ManyToManyField(
        "accounts.Team",
        blank=True,
        related_name="data_sources",
        verbose_name="Открыт для команд",
        help_text="Пусто = закрыт для всех. Добавь команду — она увидит лиды.",
    )
    
    is_released = models.BooleanField(
        default=False,
        verbose_name="Открыт для команды",
    )
    released_at = models.DateTimeField(
        blank=True, null=True,
        verbose_name="Когда открыли",
    )
    notes = models.TextField(blank=True, verbose_name="Заметки")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Источник данных"
        verbose_name_plural = "Источники данных"
        ordering = ["-is_released", "key"]

    def __str__(self):
        status = "открыт" if self.is_released else "закрыт"
        return f"{self.title or self.key} ({status})"
