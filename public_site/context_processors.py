from .models import SiteSettings


def site_settings(request):
    """Доступно в кожному шаблоні як {{ site_settings.* }} —
    без потреби передавати вручну з кожного view."""
    return {"site_settings": SiteSettings.get_solo()}
