from django.urls import path

from . import views

app_name = "public_site"

urlpatterns = [
    path("", views.home, name="home"),
    path("partners/", views.partner_form, name="partner_form"),
]
