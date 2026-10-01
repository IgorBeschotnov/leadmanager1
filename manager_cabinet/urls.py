from django.urls import path
from . import views

app_name = "manager"

urlpatterns = [
    path("tasks/", views.tasks, name="tasks"),
    path("guide/", views.guide, name="guide"),
    path("reports/", views.reports, name="reports"),
    path("database/", views.database, name="database"),
    path("partners/", views.partners, name="partners"),
    path("processed/", views.processed, name="processed"),
    path("templates/", views.templates_list, name="templates"),
    path("templates/<int:pk>/toggle/", views.template_toggle, name="template_toggle"),
    path("lead/<int:pk>/", views.lead_detail, name="lead_detail"),
    path("operators/", views.operators_list, name="operators"),
    path("operator/<int:pk>/", views.operator_detail, name="operator_detail"),
    path("lead/create/", views.lead_create, name="lead_create"),
    path("lead/<int:pk>/ai-generate/", views.ai_generate_kp, name="ai_generate_kp"),
]
