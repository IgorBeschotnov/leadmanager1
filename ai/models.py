from django.db import models


class AISettings(models.Model):
    """
    Singleton-настройки AI.
    Меняются только из Django Admin.
    """
    PROVIDER_CHOICES = [
        ("groq", "Groq"),
        ("openai", "OpenAI-compatible"),
    ]

    # --- API ---
    api_provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default="groq",
        verbose_name="Провайдер",
    )
    api_key = models.CharField(
        max_length=255,
        verbose_name="API Key",
        help_text="Ключ вида gsk_... для Groq",
    )
    api_base_url = models.CharField(
        max_length=255,
        default="https://api.groq.com/openai/v1",
        verbose_name="Base URL",
        help_text="Для Groq оставь как есть. Для других — свой endpoint.",
    )
    model_name = models.CharField(
        max_length=100,
        default="openai/gpt-oss-20b",
        verbose_name="Модель",
        help_text="Например: openai/gpt-oss-20b, qwen/qwen3.8-27b",
    )

    # --- Базовый текст КП (большое письмо со всеми хотелками) ---
    base_kp_text = models.TextField(
        verbose_name="Базовый текст КП",
        help_text=(
            "Полный эталонный текст обращения: описание организации, "
            "таблица потребностей, реквизиты и т.д. "
            "Модель будет адаптировать его под конкретного лида."
        ),
        blank=True,
    )

    # --- Системный промпт (опционально) ---
    system_prompt = models.TextField(
        verbose_name="Системный промпт",
        blank=True,
        help_text="Дополнительные инструкции модели. Можно оставить пустым.",
        default=(
            "Ти допомагаєш писати персоналізовані звернення про гуманітарну допомогу "
            "від ГО «Майбутнє-Нове Покоління Україна». Пиши українською мовою. "
            "Зберігай факти про підопічних і потреби. Не вигадуй реквізити."
        ),
    )

    # --- Служебное ---
    is_active = models.BooleanField(default=True, verbose_name="Активно")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки AI"
        verbose_name_plural = "Настройки AI"

    def __str__(self):
        return f"AISettings ({self.model_name}) — {'активно' if self.is_active else 'выкл'}"

    def save(self, *args, **kwargs):
        # Гарантируем только одну активную запись
        if self.is_active:
            AISettings.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()
