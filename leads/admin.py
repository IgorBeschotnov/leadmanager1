from django.contrib import admin, messages
from django.utils import timezone

from .models import Category, Company, CallLog, DataSource


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


class CallLogInline(admin.TabularInline):
    model = CallLog
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "region", "source", "stage", "team", "assigned_to", "updated_at")
    list_filter = ("stage", "team", "region", "source", "categories")
    search_fields = ("name", "phones", "emails", "phone_normalized", "source")
    filter_horizontal = ("categories",)
    readonly_fields = ("phone_normalized", "created_at", "updated_at")
    inlines = [CallLogInline]
    actions = ["delete_selected_leads"]

    @admin.action(description="Удалить выбранные лиды (навсегда)")
    def delete_selected_leads(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"Удалено лидов: {count}", messages.WARNING)


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ("company", "operator", "result", "created_at")
    list_filter = ("result",)


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "is_released", "released_at", "leads_count")
    list_filter = ("is_released",)
    search_fields = ("key", "title")
    actions = ["release_sources", "close_sources", "sync_from_companies"]
    readonly_fields = ("released_at", "created_at")

    def leads_count(self, obj):
        return Company.objects.filter(source=obj.key).count()
    leads_count.short_description = "Лидов"

    @admin.action(description="Открыть для команды")
    def release_sources(self, request, queryset):
        updated = queryset.update(is_released=True, released_at=timezone.now())
        self.message_user(request, f"Открыто источников: {updated}")

    @admin.action(description="Закрыть (скрыть от команды)")
    def close_sources(self, request, queryset):
        updated = queryset.update(is_released=False)
        self.message_user(request, f"Закрыто источников: {updated}")

    @admin.action(description="Подтянуть источники из компаний")
    def sync_from_companies(self, request, queryset):
        keys = (
            Company.objects
            .exclude(source__isnull=True)
            .exclude(source="")
            .values_list("source", flat=True)
            .distinct()
        )
        created = 0
        for key in keys:
            _, was_created = DataSource.objects.get_or_create(
                key=key,
                defaults={"title": key},
            )
            if was_created:
                created += 1
        self.message_user(request, f"Новых источников: {created}")