from django.urls import path
from . import views

app_name = "manager"

urlpatterns = [
    path("tasks/", views.tasks, name="tasks"),
    path("reports/", views.reports, name="reports"),
    path("database/", views.database, name="database"),
    path("partners/", views.partners, name="partners"),
    path("templates/", views.templates_list, name="templates"),
    path("templates/<str:key>/preview/", views.template_preview, name="template_preview"),
    path("lead/<int:pk>/", views.lead_detail, name="lead_detail"),
    path("operators/", views.operators_list, name="operators"),
    path("operator/<int:pk>/", views.operator_detail, name="operator_detail"),
]
