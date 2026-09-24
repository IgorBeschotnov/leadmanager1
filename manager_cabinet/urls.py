from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "manager"

urlpatterns = [
    # /manager/ → задачи
    path("", RedirectView.as_view(pattern_name="manager:tasks", permanent=False)),

    path("tasks/", views.tasks, name="tasks"),
    path("reports/", views.reports, name="reports"),
    path("database/", views.database, name="database"),
    path("partners/", views.partners, name="partners"),
    path("templates/", views.templates_list, name="templates"),
    path("templates/<str:key>/preview/", views.template_preview, name="template_preview"),
    path("lead/<int:pk>/", views.lead_detail, name="lead_detail"),
    path("operators/", views.operators_list, name="operators"),
    path("operator/<int:pk>/", views.operator_detail, name="operator_detail"),
    path("lead/create/", views.lead_create, name="lead_create"),
    path("lead/<int:pk>/ai-generate/", views.ai_generate_kp, name="ai_generate_kp"),
]