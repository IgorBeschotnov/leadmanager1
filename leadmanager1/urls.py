from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from manager_cabinet.views import public_home

urlpatterns = [
    path("", public_home, name="home"),
    path("admin/", admin.site.urls),
    path("manager/", include("manager_cabinet.urls")),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
]