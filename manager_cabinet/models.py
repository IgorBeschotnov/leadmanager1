from django.conf import settings
from django.db import models


class CommunicationTemplate(models.Model):
    class Type(models.TextChoices):
        PROPOSAL = "proposal", "Комерційна пропозиція"
        THANKS = "thanks", "Подяка партнеру"

    type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=100, blank=True)
    base_text = models.TextField(help_text="Базовий текст або приклад для AI")
    ai_instruction = models.TextField(blank=True, help_text="Як персоналізувати повідомлення")
    example_result = models.TextField(blank=True, help_text="Приклад готового персоналізованого повідомлення")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["type", "name"]

    def __str__(self):
        return self.name


class GeneratedMessage(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Чернетка"
        SENT = "sent", "Відправлено"

    company = models.ForeignKey("leads.Company", on_delete=models.CASCADE, related_name="generated_messages")
    template = models.ForeignKey(CommunicationTemplate, on_delete=models.SET_NULL, null=True, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    body = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
