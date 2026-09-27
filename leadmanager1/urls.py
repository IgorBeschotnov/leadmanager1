from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("manager/", include("manager_cabinet.urls")),
    path("", include("public_site.urls")),

    # Вход / выход
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
]

if settings.DEBUG:
    # У проді файли з MEDIA_ROOT віддає Nginx (або інший веб-сервер),
    # а не Django — цей рядок працює тільки для локальної розробки.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
