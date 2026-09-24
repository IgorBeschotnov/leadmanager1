from django.contrib import admin
from .models import AISettings


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ("model_name", "api_provider", "is_active", "updated_at")
    list_filter = ("is_active", "api_provider")
    readonly_fields = ("updated_at",)

    fieldsets = (
        ("API", {
            "fields": ("api_provider", "api_key", "api_base_url", "model_name"),
        }),
        ("Базовый текст КП", {
            "fields": ("base_kp_text",),
            "description": "Большое эталонное письмо со всеми хотелками, таблицей и реквизитами.",
        }),
        ("Промпт", {
            "fields": ("system_prompt",),
            "classes": ("collapse",),
        }),
        ("Статус", {
            "fields": ("is_active", "updated_at"),
        }),
    )

    def has_add_permission(self, request):
        # Разрешаем создать только если ещё нет ни одной записи
        if AISettings.objects.exists():
            return False
        return super().has_add_permission(request)
