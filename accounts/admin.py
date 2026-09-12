from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Team, User, UserCapability, AccessAuditLog


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


class UserCapabilityInline(admin.TabularInline):
    model = UserCapability
    extra = 1


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [UserCapabilityInline]
    list_display = ("username", "name", "team", "telegram_id", "access_revoked", "is_staff")
    list_filter = ("team", "access_revoked", "is_staff")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Lead Manager", {"fields": ("telegram_id", "team", "description", "access_revoked")}),
    )

    def save_model(self, request, obj, form, change):
        if obj.is_staff and not obj.is_superuser and not obj.team_id:
            from django.contrib import messages
            messages.error(request, "Укажите команду. Без команды staff-пользователя сохранить нельзя.")
            return  # не сохраняем
        super().save_model(request, obj, form, change)


@admin.register(AccessAuditLog)
class AccessAuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "target_type", "target_id")
    list_filter = ("action", "target_type")
    readonly_fields = ("created_at",)
