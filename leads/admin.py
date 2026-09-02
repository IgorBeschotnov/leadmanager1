from django.contrib import admin

from .models import Category, Company, CallLog


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
    list_display = ("name", "city", "region", "stage", "team", "assigned_to", "updated_at")
    list_filter = ("stage", "team", "region", "categories")
    search_fields = ("name", "phones", "emails", "phone_normalized")
    filter_horizontal = ("categories",)
    readonly_fields = ("phone_normalized", "created_at", "updated_at")
    inlines = [CallLogInline]


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ("company", "operator", "result", "created_at")
    list_filter = ("result",)
