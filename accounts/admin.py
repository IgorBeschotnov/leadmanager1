from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Team, User, UserCapability, AccessAuditLog


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "bot_username", "access_valid_until", "created_at")
    search_fields = ("name", "bot_username")
    fields = (
        "name",
        "description",
        "bot_token",
        "bot_username",
        "access_password_word",
        "access_valid_until",
        "created_at",
    )
    readonly_fields = ("created_at",)


class UserCapabilityInline(admin.TabularInline):
    model = UserCapability
    extra = 1


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [UserCapabilityInline]

    list_display = (
        "username",
        "name",
        "team",
        "telegram_id",
        "access_revoked",
        "is_staff",
    )

    list_filter = (
        "team",
        "access_revoked",
        "is_staff",
    )

    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Lead Manager — рабочая система",
            {
                "fields": (
                    "telegram_id",
                    "team",
                    "access_revoked",
                )
            },
        ),
        (
            "Публичная карточка — сайт",
            {
                "fields": (
                    "is_public_profile",
                    "public_role_title",
                    "description",
                    "public_photo",
                    "public_photo_url",
                    "public_order",
                ),
                "description": (
                    "Настройки карточки пользователя на публичном сайте. "
                    "Включите показ, укажите должность, кратко опишите человека "
                    "и при необходимости загрузите фотографию."
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if obj.is_staff and not obj.is_superuser and not obj.team_id:
            from django.contrib import messages

            messages.error(
                request,
                "Укажите команду. Без команды staff-пользователя сохранить нельзя.",
            )
            return

        super().save_model(request, obj, form, change)


@admin.register(AccessAuditLog)
class AccessAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "action",
        "target_type",
        "target_id",
    )

    list_filter = (
        "action",
        "target_type",
    )

    readonly_fields = ("created_at",)