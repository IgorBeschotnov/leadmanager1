from django.contrib import admin

from .models import CarouselSlide, SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Singleton: редагуємо єдиний існуючий рядок, новий створити не можна,
    якщо один вже є (див. SiteSettings.clean)."""

    fieldsets = (
        ("Головна сторінка", {"fields": ("org_name", "hero_title", "hero_subtitle")}),
        ("Футер", {"fields": ("footer_about", "address", "phone", "email")}),
        ("Соцмережі", {"fields": ("tiktok_url", "facebook_url", "instagram_url")}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CarouselSlide)
class CarouselSlideAdmin(admin.ModelAdmin):
    list_display = ("order", "title", "is_active")
    list_display_links = ("title",)
    list_editable = ("order", "is_active")
    ordering = ("order",)
