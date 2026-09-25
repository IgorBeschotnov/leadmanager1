from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from leads.models import Company, CallLog, DataSource
from accounts.models import User
from .letter_templates import (
    TEMPLATES, render_template, get_templates_list, get_attachment_files
)

# AI-генерация КП
from ai.generate import generate_kp
from ai.client import AIClientError
from django.views.decorators.http import require_GET  # если ещё нет

@require_GET
def public_home(request):
    """Публічна головна — без логіну. Текст/менеджери — заглушка, потім замінимо."""
    managers = [
        {
            "name": "Тетяна",
            "role": "Керівник команди",
            "desc": "Координація дзвінків та КП",
            "avatar": "https://ui-avatars.com/api/?name=Tetiana&background=0d6efd&color=fff&size=128",
        },
        {
            "name": "Олег",
            "role": "Оператор",
            "desc": "Перший контакт з лідами",
            "avatar": "https://ui-avatars.com/api/?name=Oleg&background=198754&color=fff&size=128",
        },
        {
            "name": "Марія",
            "role": "Менеджер з партнерств",
            "desc": "Супровід партнерів і листів",
            "avatar": "https://ui-avatars.com/api/?name=Maria&background=6f42c1&color=fff&size=128",
        },
    ]
    return render(request, "public/home.html", {
        "managers": managers,
        "org_name": "Реабілітаційний центр",
        "org_city": "Шахтарське",
    })

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
    return qs.none()


def _filter_released(qs, user):
    if _is_owner(user):
        return qs
    team = getattr(user, "team", None)
    if not team:
        return qs.filter(Q(source__isnull=True) | Q(source=""))
    released_keys = (
        DataSource.objects.filter(teams=team).values_list("key", flat=True)
    )
    return qs.filter(
        Q(source__in=released_keys) | Q(source__isnull=True) | Q(source="")
    )

# ─────────────────────────────────────────────────────────────
# Список задач (letter_sent + is_sent_by_manager=False)
# ─────────────────────────────────────────────────────────────
@manager_required
def tasks(request):
    # Оператор запросил отправку КП → менеджер обрабатывает по очереди
    qs = (
        Company.objects
        .filter(stage="letter_sent", is_sent_by_manager=False)
        .select_related("assigned_to", "team")
        .order_by("updated_at")  # FIFO: дольше ждут — выше
    )
    qs = _filter_by_team(qs, request.user)
    qs = _filter_released(qs, request.user)

    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(city__icontains=search) |
            Q(phones__icontains=search) |
            Q(phone_normalized__icontains=search)
        )

    context = {
        "page": "tasks",
        "leads": qs,
        "templates": get_templates_list(),
        "attachments": get_attachment_files(),
        "search": search,
    }
    return render(request, "manager/tasks.html", context)

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
    # Уже у оператора / с пометками, или менеджер уже отправил КП.
    # Не показываем «сырых» new и не дублируем очередь Задач.
    qs = (
        Company.objects
        .exclude(stage__in=["new", "refusal", "success"])
        .exclude(stage="letter_sent", is_sent_by_manager=False)  # это только Задачи
        .select_related("assigned_to", "team")
        .order_by("-updated_at")
    )
    qs = _filter_by_team(qs, request.user)
    qs = _filter_released(qs, request.user)

    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(city__icontains=search) |
            Q(phones__icontains=search) |
            Q(phone_normalized__icontains=search)
        )

    stage_filter = request.GET.get("stage")
    if stage_filter:
        qs = qs.filter(stage=stage_filter)

    context = {
        "page": "database",
        "leads": qs[:200],
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
    qs = _filter_released(qs, request.user)

    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(city__icontains=search) |
            Q(phones__icontains=search) |
            Q(phone_normalized__icontains=search)
        )

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

        # --- Сохранить внутренние заметки ---
        if action == "save_notes":
            lead.internal_notes = request.POST.get("internal_notes", "")
            lead.save(update_fields=["internal_notes", "updated_at"])
            return redirect("manager:lead_detail", pk=pk)

        # --- Отметить КП как отправленное (без суммы и веса) ---
        if action == "mark_sent":
            lead.is_sent_by_manager = True
            lead.callback_date = timezone.now() + timedelta(days=3)

            attached = request.POST.getlist("attachments")
            extra = ""
            if attached:
                extra = "Файли: " + ", ".join(attached)
                lead.internal_notes = (lead.internal_notes or "") + f"\n[КП] {extra}"

            lead.save()

            CallLog.objects.create(
                company=lead,
                operator=request.user,
                result="success",
                comment="КП відправлено менеджером" + (f" ({extra})" if extra else ""),
            )
            return redirect("manager:tasks")

        if action == "make_partner":
            lead.stage = "success"
            lead.save(update_fields=["stage", "updated_at"])

            CallLog.objects.create(
                company=lead,
                operator=request.user,
                result="success",
                comment="Переведено в партнери",
            )
            return redirect("manager:lead_detail", pk=pk)

        # --- Зафиксировать помощь от партнёра (только для stage=success) ---
        if action == "record_help":
            if lead.stage != "success":
                return redirect("manager:lead_detail", pk=pk)

            donation = request.POST.get("donation_amount", "").strip()
            weight = request.POST.get("package_weight", "").strip()

            note_parts = []
            if donation:
                note_parts.append(f"Сума допомоги: {donation} грн")
            if weight:
                note_parts.append(f"Вага: {weight} кг")

            if note_parts:
                extra = " | ".join(note_parts)
                lead.internal_notes = (lead.internal_notes or "") + f"\n[Допомога] {extra}"
                lead.save(update_fields=["internal_notes", "updated_at"])

                CallLog.objects.create(
                    company=lead,
                    operator=request.user,
                    result="success",
                    comment=f"Зафіксовано допомогу партнера: {extra}",
                )
            return redirect("manager:lead_detail", pk=pk)

        # --- Сгенерировать текст шаблона и записать в историю ---
        if action == "generate_and_log":
            template_key = request.POST.get("template_key")
            text = render_template(template_key, lead, operator_name=request.user.name)
            CallLog.objects.create(
                company=lead,
                operator=request.user,
                result="success",
                comment=f"[Шаблон: {TEMPLATES.get(template_key, {}).get('name', template_key)}]\n\n{text}",
            )
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
# AI-генерация КП (персонализированный текст через LLM)
# ─────────────────────────────────────────────────────────────
@manager_required
@require_POST
def ai_generate_kp(request, pk):
    """
    POST /manager/lead/<pk>/ai-generate/

    Параметры формы:
      channel        = email | telegram | viber | whatsapp
      tone           = emotional | official | short
      volume         = short | medium | full
      date           = дата відправки (текст)
      number         = номер листа
      manager_name   = ім'я менеджера
      manager_phone  = телефон менеджера
    """
    lead = get_object_or_404(Company, pk=pk)

    channel = request.POST.get("channel", "email")
    tone = request.POST.get("tone", "official")
    volume = request.POST.get("volume", "medium")

    inserts = {
        "Дата відправки": request.POST.get("date", ""),
        "Номер листа": request.POST.get("number", ""),
        "Менеджер": request.POST.get("manager_name", "") or (
            getattr(request.user, "get_full_name", lambda: "")() or request.user.username
        ),
        "Телефон менеджера": request.POST.get("manager_phone", ""),
    }

    try:
        text = generate_kp(
            company=lead,
            channel=channel,
            tone=tone,
            volume=volume,
            inserts=inserts,
        )
        return JsonResponse({"ok": True, "text": text})
    except AIClientError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Внутрішня помилка: {e}"}, status=500)


# ─────────────────────────────────────────────────────────────
# Страница шаблонов
# ─────────────────────────────────────────────────────────────
@manager_required
def templates_list(request):
    context = {
        "page": "templates",
        "templates": get_templates_list(),
        "full_templates": TEMPLATES,
    }
    return render(request, "manager/templates_list.html", context)


@manager_required
@require_GET
def template_preview(request, key):
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


@manager_required
def lead_create(request):
    """Создание нового лида прямо из кабинета менеджера."""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            return redirect("manager:lead_create")

        lead = Company(
            name=name,
            phones=request.POST.get("phones", "").strip() or None,
            city=request.POST.get("city", "").strip() or None,
            region=request.POST.get("region", "").strip() or None,
            contact_person=request.POST.get("contact_person", "").strip() or None,
            emails=request.POST.get("emails", "").strip() or None,
            preferred_channel=request.POST.get("preferred_channel", "").strip() or None,
            internal_notes=request.POST.get("internal_notes", "").strip() or None,
            stage=request.POST.get("stage", "in_progress"),
            team=request.user.team,
            assigned_to=request.user,
        )
        lead.save()

        call_result = request.POST.get("call_result", "").strip()
        call_comment = request.POST.get("call_comment", "").strip()
        if call_result:
            CallLog.objects.create(
                company=lead,
                operator=request.user,
                result=call_result,
                comment=call_comment or None,
            )

        return redirect("manager:lead_detail", pk=lead.pk)

    context = {
        "page": "lead_create",
    }
    return render(request, "manager/lead_create.html", context)


# ─────────────────────────────────────────────────────────────
# Список операторов
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
@require_GET
def public_home(request):
    managers = [
        {
            "name": "Тетяна",
            "role": "Керівник команди",
            "desc": "Координація дзвінків та КП",
            "avatar": "https://ui-avatars.com/api/?name=Tetiana&background=0d6efd&color=fff&size=128",
        },
        {
            "name": "Олег",
            "role": "Оператор",
            "desc": "Перший контакт з лідами",
            "avatar": "https://ui-avatars.com/api/?name=Oleg&background=198754&color=fff&size=128",
        },
        {
            "name": "Марія",
            "role": "Менеджер з партнерств",
            "desc": "Супровід партнерів і листів",
            "avatar": "https://ui-avatars.com/api/?name=Maria&background=6f42c1&color=fff&size=128",
        },
    ]
    return render(request, "public/home.html", {
        "managers": managers,
        "org_name": "Реабілітаційний центр",
        "org_city": "Шахтарське",
    })