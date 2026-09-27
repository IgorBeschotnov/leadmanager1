from django.core.exceptions import ValidationError
from django.db import models


class SiteSettings(models.Model):
    """Єдиний рядок з текстами/посиланнями для публічного сайту.

    Свідомо НЕ через код/шаблони — редагується у звичайній адмінці
    (/admin/public_site/sitesettings/), щоб верстку не можна було
    випадково зламати: поля структуровані, а не вільний HTML.
    """

    org_name = models.CharField(
        max_length=100, default="Наш центр",
        verbose_name="Назва центру (шапка/футер)",
    )
    hero_title = models.CharField(
        max_length=200, default="Ми поруч із тими, кому зараз найважче",
        verbose_name="Заголовок на головній",
    )
    hero_subtitle = models.TextField(
        blank=True,
        default="Коротко про центр: кому допомагаємо, як довго працюємо, чому це важливо.",
        verbose_name="Підзаголовок на головній",
    )
    footer_about = models.TextField(
        blank=True,
        default="Підтримуємо тих, хто найбільше потребує допомоги.",
        verbose_name="Короткий опис у футері",
    )
    address = models.CharField(max_length=255, blank=True, verbose_name="Адреса")
    phone = models.CharField(max_length=50, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")
    tiktok_url = models.URLField(blank=True, verbose_name="Посилання на TikTok")
    facebook_url = models.URLField(blank=True, verbose_name="Посилання на Facebook")
    instagram_url = models.URLField(blank=True, verbose_name="Посилання на Instagram")

    class Meta:
        verbose_name = "Налаштування сайту"
        verbose_name_plural = "Налаштування сайту"

    def __str__(self):
        return "Налаштування публічного сайту"

    def clean(self):
        # Singleton: тільки один рядок налаштувань.
        if not self.pk and SiteSettings.objects.exists():
            raise ValidationError("Налаштування сайту вже існують — редагуй існуючий запис, не створюй новий.")

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class CarouselSlide(models.Model):
    """Один слайд стаціонарної карусельки на головній. Порядок — order."""

    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    title = models.CharField(max_length=100, verbose_name="Заголовок слайду")
    text = models.TextField(verbose_name="Текст слайду")
    is_active = models.BooleanField(default=True, verbose_name="Показувати")

    class Meta:
        verbose_name = "Слайд карусельки"
        verbose_name_plural = "Слайди карусельки"
        ordering = ["order", "id"]

    def __str__(self):
        return self.title
