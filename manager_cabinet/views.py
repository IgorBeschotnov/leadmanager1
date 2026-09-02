from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from leads.models import Company, CallLog  # предполагаем app 'leads'
from accounts.models import User  # кастомный User
from .letter_templates import (
    TEMPLATES, render_template, get_templates_list, get_attachment_files
)


def manager_required(view_func):
    """Простая проверка: staff + не отозван доступ."""
    @login_required
    @staff_member_required
    def _wrapped(request, *args, **kwargs):
        if getattr(request.user, "access_revoked", False):
            return HttpResponseForbidden("Доступ відкликано")
        return view_func(request, *args, **kwargs)
    return _wrapped


def _is_owner(user) -> bool:
    return user.capabilities.filter(capability="owner").exists()


def _filter_by_team(qs, user):
    """Ізоляція по команді. Owner бачить усе."""
    if _is_owner(user):
        return qs
    if getattr(user, "team_id", None):
        return qs.filter(Q(team=user.team) | Q(team__isnull=True))
    return qs.none()  # без команди і не owner — нічого


# ─────────────────────────────────────────────────────────────
# Список задач (letter_sent + is_sent_by_manager=False)
# ─────────────────────────────────────────────────────────────
@manager_required
def tasks(request):
    qs = (
        Company.objects
        .filter(stage="letter_sent", is_sent_by_manager=False)
        .select_related("assigned_to", "team")
        .order_by("updated_at")  # давность
    )
    qs = _filter_by_team(qs, request.user)

    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(city__icontains=search))

    context = {
        "page": "tasks",
        "leads": qs,
        "templates": get_templates_list(),
        "attachments": get_attachment_files(),
        "search": search,
    }
    return render(request, "manager/tasks.html", context)


# ─────────────────────────────────────────────────────────────
# Отчёты
# ─────────────────────────────────────────────────────────────
@manager_required
def reports(request):
    # Сводка по операторам (последние 30 дней для примера)
    since = timezone.now() - timedelta(days=30)

    operators_stats = (
        CallLog.objects
        .filter(created_at__gte=since)
        .values("operator_id", "operator__first_name", "operator__last_name", "operator__username")
        .annotate(
            total=Count("id"),
            success=Count("id", filter=Q(result="success")),
            refusal=Count("id", filter=Q(result="refusal")),
            call_back=Count("id", filter=Q(result="call_back")),
            wrong=Count("id", filter=Q(result="wrong_number")),
        )
        .order_by("-total")
    )

    recent_calls = (
        CallLog.objects
        .select_related("company", "operator")
        .order_by("-created_at")[:40]
    )

    context = {
        "page": "reports",
        "operators_stats": operators_stats,
        "recent_calls": recent_calls,
    }
    return render(request, "manager/reports.html", context)


# ─────────────────────────────────────────────────────────────
# База (всё кроме new / refusal / success)
# ─────────────────────────────────────────────────────────────
@manager_required
def database(request):
    qs = (
        Company.objects
        .exclude(stage__in=["new", "refusal", "success"])
        .select_related("assigned_to", "team")
        .order_by("-updated_at")
    )
    qs = _filter_by_team(qs, request.user)

    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(city__icontains=search))

    stage_filter = request.GET.get("stage")
    if stage_filter:
        qs = qs.filter(stage=stage_filter)

    context = {
        "page": "database",
        "leads": qs[:200],  # защита от огромных списков
        "search": search,
        "stage_filter": stage_filter,
    }
    return render(request, "manager/database.html", context)


# ─────────────────────────────────────────────────────────────
# Партнёры (stage=success)
# ─────────────────────────────────────────────────────────────
@manager_required
def partners(request):
    qs = (
        Company.objects
        .filter(stage="success")
        .select_related("assigned_to", "team")
        .order_by("-updated_at")
    )
    qs = _filter_by_team(qs, request.user)

    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(city__icontains=search))

    context = {
        "page": "partners",
        "leads": qs,
        "search": search,
    }
    return render(request, "manager/partners.html", context)


# ─────────────────────────────────────────────────────────────
# Карточка лида
# ─────────────────────────────────────────────────────────────
@manager_required
def lead_detail(request, pk):
    lead = get_object_or_404(
        Company.objects.select_related("assigned_to", "team"),
        pk=pk
    )
    call_logs = lead.call_logs.select_related("operator").order_by("-created_at")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save_notes":
            lead.internal_notes = request.POST.get("internal_notes", "")
            lead.save(update_fields=["internal_notes", "updated_at"])
            return redirect("manager:lead_detail", pk=pk)

        if action == "mark_sent":
            lead.is_sent_by_manager = True
            lead.callback_date = timezone.now() + timedelta(days=3)
            # опционально сумма / вес
            donation = request.POST.get("donation_amount", "").strip()
            weight = request.POST.get("package_weight", "").strip()
            attached = request.POST.getlist("attachments")  # імена файлів
            note_parts = []
            if donation:
                note_parts.append(f"Сума: {donation}")
            if weight:
                note_parts.append(f"Вага: {weight}")
            if attached:
                note_parts.append("Файли: " + ", ".join(attached))
            extra = " | ".join(note_parts) if note_parts else ""
            if extra:
                lead.internal_notes = (lead.internal_notes or "") + f"\n[КП] {extra}"
            lead.save()
            # лог
            CallLog.objects.create(
                company=lead,
                operator=request.user,
                result="success",
                comment="КП відправлено менеджером" + (f" ({extra})" if extra else ""),
            )
            return redirect("manager:tasks")

        if action == "generate_and_log":
            template_key = request.POST.get("template_key")
            text = render_template(template_key, lead, operator_name=request.user.name)
            # сохраняем в историю
            CallLog.objects.create(
                company=lead,
                operator=request.user,
                result="success",
                comment=f"[Шаблон: {TEMPLATES.get(template_key, {}).get('name', template_key)}]\n\n{text}",
            )
            # возвращаем текст для копирования (AJAX или redirect с параметром)
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"text": text, "ok": True})
            return redirect("manager:lead_detail", pk=pk)

    context = {
        "page": "lead",
        "lead": lead,
        "call_logs": call_logs,
        "templates": get_templates_list(),
        "attachments": get_attachment_files(),
    }
    return render(request, "manager/lead_detail.html", context)


# ─────────────────────────────────────────────────────────────
# Окно / страница шаблонов
# ─────────────────────────────────────────────────────────────
@manager_required
def templates_list(request):
    """Отдельная страница со всеми шаблонами + предпросмотр."""
    context = {
        "page": "templates",
        "templates": get_templates_list(),
        "full_templates": TEMPLATES,
    }
    return render(request, "manager/templates_list.html", context)


@manager_required
@require_GET
def template_preview(request, key):
    """AJAX: вернуть готовый текст шаблона для конкретной компании."""
    company_id = request.GET.get("company_id")
    if not company_id:
        return JsonResponse({"error": "company_id required"}, status=400)

    company = get_object_or_404(Company, pk=company_id)
    text = render_template(key, company, operator_name=request.user.name)
    return JsonResponse({
        "text": text,
        "name": TEMPLATES.get(key, {}).get("name", key),
    })


# ─────────────────────────────────────────────────────────────
# Карточка оператора
# ─────────────────────────────────────────────────────────────
@manager_required
def operator_detail(request, pk):
    operator = get_object_or_404(User, pk=pk)

    stats = CallLog.objects.filter(operator=operator).aggregate(
        total=Count("id"),
        success=Count("id", filter=Q(result="success")),
        refusal=Count("id", filter=Q(result="refusal")),
        call_back=Count("id", filter=Q(result="call_back")),
        wrong=Count("id", filter=Q(result="wrong_number")),
    )

    active_leads = Company.objects.filter(
        assigned_to=operator,
        stage__in=["in_progress", "letter_sent"]
    ).order_by("-updated_at")

    partner_leads = Company.objects.filter(
        assigned_to=operator,
        stage="success"
    ).order_by("-updated_at")[:20]

    context = {
        "page": "operator",
        "operator": operator,
        "stats": stats,
        "active_leads": active_leads,
        "partner_leads": partner_leads,
    }
    return render(request, "manager/operator_detail.html", context)


# ─────────────────────────────────────────────────────────────
# Список операторов (простая страница)
# ─────────────────────────────────────────────────────────────
@manager_required
def operators_list(request):
    operators = User.objects.filter(
        capabilities__capability="operator"
    ).distinct().order_by("first_name", "username")

    context = {
        "page": "operators",
        "operators": operators,
    }
    return render(request, "manager/operators_list.html", context)
