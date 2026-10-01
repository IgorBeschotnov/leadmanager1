from datetime import timedelta
from html import escape
from html.parser import HTMLParser

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Prefetch, Q, Sum
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST
from leads.models import Company, CallLog, DataSource, PUBLIC_FORM_SOURCE
from accounts.models import User
from .letter_templates import get_attachment_files
from .models import CommunicationTemplate, GeneratedMessage

# AI-генерация КП
from ai.generate import generate_communication
from ai.client import AIClientError

NOTE_COLORS = {"red", "orange", "yellow", "green", "blue"}


class _NotesSanitizer(HTMLParser):
    """Keep note text and only the five supported color spans and line breaks."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.color_stack = []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "iframe", "object"}:
            self.suppressed += 1
            return
        if self.suppressed:
            return
        if tag == "br":
            self.parts.append("<br>")
        elif tag == "span":
            color = attrs.get("data-note-color", "")
            allowed = color in NOTE_COLORS
            self.color_stack.append(allowed)
            if allowed:
                self.parts.append(f'<span data-note-color="{color}">')
        elif tag in {"p", "div"}:
            self.parts.append("<br>")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "iframe", "object"} and self.suppressed:
            self.suppressed -= 1
            return
        if self.suppressed:
            return
        if tag == "span" and self.color_stack:
            if self.color_stack.pop():
                self.parts.append("</span>")
        elif tag in {"p", "div"}:
            self.parts.append("<br>")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(escape(data))

    def html(self):
        while self.color_stack:
            if self.color_stack.pop():
                self.parts.append("</span>")
        return "".join(self.parts)


def _sanitize_notes(value):
    parser = _NotesSanitizer()
    parser.feed(value or "")
    parser.close()
    return parser.html()

def manager_required(view_func):
    """staff + не отозван + не servant-only."""
    @login_required
    @staff_member_required
    def _wrapped(request, *args, **kwargs):
        if getattr(request.user, "access_revoked", False):
            return HttpResponseForbidden("Доступ відкликано")
        if getattr(request.user, "is_servant_only", lambda: False)():
            return HttpResponseForbidden("Роль «служитель» не має доступу до кабінету")
        return view_func(request, *args, **kwargs)
    return _wrapped


def _is_owner(user) -> bool:
    if hasattr(user, "is_owner"):
        return user.is_owner()
    return user.capabilities.filter(capability="owner").exists()


def _filter_by_team(qs, user):
    """Только назначенные team=user.team. Сырые — через _filter_released_raw."""
    if _is_owner(user):
        return qs
    if getattr(user, "team_id", None):
        return qs.filter(team=user.team)
    return qs.none()


def _filter_released_raw(qs, user):
    """Сырые (team=NULL) только из открытых DataSource."""
    if _is_owner(user):
        return qs.filter(team__isnull=True)
    team = getattr(user, "team", None)
    if not team:
        return qs.none()
    released_keys = list(
        DataSource.objects.filter(teams=team).values_list("key", flat=True)
    )
    if not released_keys:
        return qs.none()
    return qs.filter(team__isnull=True, source__in=released_keys)


def _visible_leads_qs(user):
    base = Company.objects.all()
    if _is_owner(user):
        return base
    return (_filter_by_team(base, user) | _filter_released_raw(base, user)).distinct()


def _user_can_see_lead(user, lead) -> bool:
    if _is_owner(user):
        return True
    if not getattr(user, "team_id", None):
        return False
    if lead.team_id == user.team_id:
        return True
    if lead.team_id is None and lead.source:
        return DataSource.objects.filter(key=lead.source, teams=user.team).exists()
    return False


def _get_lead_or_403(user, pk):
    lead = get_object_or_404(
        Company.objects.select_related("assigned_to", "team"), pk=pk
    )
    if not _user_can_see_lead(user, lead):
        from django.http import Http404
        raise Http404("Лід не знайдено або немає доступу")
    return lead


def _filter_users_by_team(qs, user):
    if _is_owner(user):
        return qs
    if getattr(user, "team_id", None):
        return qs.filter(team=user.team)
    return qs.none()


def _filter_calllogs_by_team(qs, user):
    if _is_owner(user):
        return qs
    if getattr(user, "team_id", None):
        return qs.filter(company__team=user.team)
    return qs.none()


# ─────────────────────────────────────────────────────────────
# Список задач (letter_sent + is_sent_by_manager=False)
# ─────────────────────────────────────────────────────────────
@manager_required
def tasks(request):
    # Proposal requests, new public leads, and next actions that are due.
    now = timezone.now()
    due_actions = [Company.NextAction.CALL, Company.NextAction.FOLLOW_UP,
                   Company.NextAction.THANK_PARTNER, Company.NextAction.CONTACT_PARTNER]
    qs = (
        Company.objects
        .filter(
            Q(stage="letter_sent", is_sent_by_manager=False,
              callback_date__isnull=True)
            | Q(stage="letter_sent", is_sent_by_manager=False,
                callback_date__lte=now, next_action=Company.NextAction.PREPARE_PROPOSAL)
            | Q(source=PUBLIC_FORM_SOURCE, stage="new")
            | Q(stage__in=["in_progress", "letter_sent", "success"],
                callback_date__lte=now, next_action__in=due_actions)
        )
        .select_related("assigned_to", "team")
        .order_by(F("callback_date").asc(nulls_last=True), "updated_at")
    )
    if not _is_owner(request.user):
        qs = _visible_leads_qs(request.user).filter(pk__in=qs.values_list('pk', flat=True))

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
        "attachments": get_attachment_files(),
        "search": search,
        "public_form_source": PUBLIC_FORM_SOURCE,
        "now": now,
    }
    return render(request, "manager/tasks.html", context)


@manager_required
def guide(request):
    return render(request, "manager/guide.html", {"page": "guide"})

# ─────────────────────────────────────────────────────────────
# Отчёты
# ─────────────────────────────────────────────────────────────
@manager_required
def reports(request):
    since = timezone.now() - timedelta(days=30)

    call_qs = CallLog.objects.filter(
        created_at__gte=since,
        event_type=CallLog.EventType.CALL,
    )
    call_qs = _filter_calllogs_by_team(call_qs, request.user)

    operators_stats = (
        call_qs
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
        call_qs
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
    # Active records and scheduled proposal actions; unscheduled queue items stay in Tasks.
    now = timezone.now()
    qs = (
        Company.objects
        .exclude(stage__in=["new", "refusal", "success"])
        .exclude(
            Q(stage="letter_sent", is_sent_by_manager=False, callback_date__isnull=True)
            | Q(stage="letter_sent", is_sent_by_manager=False, callback_date__lte=now)
        )
        .select_related("assigned_to", "team")
        .order_by(F("callback_date").asc(nulls_last=True), "-updated_at")
    )
    if not _is_owner(request.user):
        qs = _visible_leads_qs(request.user).filter(pk__in=qs.values_list('pk', flat=True))

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
    action_filter = request.GET.get("next_action")
    if action_filter in Company.NextAction.values:
        qs = qs.filter(next_action=action_filter)

    context = {
        "page": "database",
        "leads": qs[:200],
        "search": search,
        "stage_filter": stage_filter,
        "action_filter": action_filter,
        "next_actions": Company.NextAction.choices,
        "now": timezone.now(),
    }
    return render(request, "manager/database.html", context)


# ─────────────────────────────────────────────────────────────
# Партнёры (stage=success)
# ─────────────────────────────────────────────────────────────
@manager_required
def partners(request):
    contact_history = CallLog.objects.filter(event_type=CallLog.EventType.CALL).order_by("-created_at")[:1]
    help_history = CallLog.objects.filter(event_type=CallLog.EventType.PARTNER_HELP).order_by("-created_at")[:1]
    qs = (
        Company.objects
        .filter(stage="success")
        .select_related("assigned_to", "team")
        .prefetch_related(
            Prefetch("call_logs", queryset=contact_history, to_attr="contact_history"),
            Prefetch("call_logs", queryset=help_history, to_attr="help_history"),
        )
        .order_by(F("callback_date").asc(nulls_last=True), "-updated_at")
    )
    if not _is_owner(request.user):
        qs = _visible_leads_qs(request.user).filter(pk__in=qs.values_list('pk', flat=True))

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
def processed(request):
    """Архив: отправленные КП, просроченный callback, партнёры.
    refusal/invalid менеджеру не показываем."""
    now = timezone.now()
    qs = Company.objects.filter(
        Q(stage="letter_sent", is_sent_by_manager=True)
        | Q(stage="in_progress", callback_date__lt=now)
        | Q(stage="success")
    ).select_related("assigned_to", "team").order_by("-updated_at")
    if not _is_owner(request.user):
        qs = _filter_by_team(qs, request.user)
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(city__icontains=search)
            | Q(phones__icontains=search)
        )
    return render(request, "manager/database.html", {
        "page": "processed",
        "leads": qs[:200],
        "search": search,
    })


@manager_required
def lead_detail(request, pk):
    lead = _get_lead_or_403(request.user, pk)
    call_logs = lead.call_logs.select_related("operator").order_by("-created_at")

    if request.method == "POST":
        action = request.POST.get("action")

        # --- Сохранить внутренние заметки ---
        if action == "save_notes":
            lead.internal_notes = _sanitize_notes(request.POST.get("internal_notes", ""))
            lead.save(update_fields=["internal_notes", "updated_at"])
            return redirect("manager:lead_detail", pk=pk)

        if action == "save_address":
            lead.address = request.POST.get("address", "").strip() or None
            lead.save(update_fields=["address", "updated_at"])
            return redirect("manager:lead_detail", pk=pk)

        if action == "schedule_callback":
            raw_callback = request.POST.get("callback_date", "").strip()
            callback = parse_datetime(raw_callback) if raw_callback else None
            if not callback:
                return HttpResponseBadRequest("Оберіть коректні дату й час наступного дзвінка.")
            next_action = request.POST.get("next_action", "")
            if lead.stage == "in_progress":
                allowed_actions = {Company.NextAction.CALL, Company.NextAction.FOLLOW_UP}
            elif lead.stage == "letter_sent" and not lead.is_sent_by_manager:
                allowed_actions = {Company.NextAction.PREPARE_PROPOSAL}
            elif lead.stage == "letter_sent":
                allowed_actions = {Company.NextAction.FOLLOW_UP, Company.NextAction.CALL}
            elif lead.stage == "success":
                allowed_actions = {Company.NextAction.THANK_PARTNER, Company.NextAction.CONTACT_PARTNER}
            else:
                allowed_actions = set()
            if next_action not in allowed_actions:
                return HttpResponseBadRequest("Оберіть наступну дію зі списку.")
            if timezone.is_naive(callback):
                callback = timezone.make_aware(callback, timezone.get_current_timezone())
            if callback <= timezone.now():
                return HttpResponseBadRequest("Наступний дзвінок потрібно запланувати на майбутній час.")
            lead.callback_date = callback
            lead.next_action = next_action
            lead.save(update_fields=["callback_date", "next_action", "updated_at"])
            CallLog.objects.create(
                company=lead,
                operator=request.user,
                event_type=CallLog.EventType.CALLBACK_SCHEDULED,
                result="call_back",
                comment=f"{lead.get_next_action_display()} · {timezone.localtime(callback).strftime('%d.%m.%Y о %H:%M')}",
            )
            return redirect("manager:lead_detail", pk=pk)

        if action == "clear_next_action":
            lead.callback_date = None
            lead.save(update_fields=["callback_date", "updated_at"])
            CallLog.objects.create(company=lead, operator=request.user,
                event_type=CallLog.EventType.CALLBACK_SCHEDULED, result="info",
                comment=f"Строк для дії «{lead.get_next_action_display()}» прибрано")
            return redirect("manager:lead_detail", pk=pk)

        # --- Отметить КП как отправленное (без суммы и веса) ---
        if action == "mark_sent":
            lead.is_sent_by_manager = True
            lead.callback_date = timezone.now() + timedelta(days=3)
            lead.next_action = Company.NextAction.FOLLOW_UP

            attached = request.POST.getlist("attachments")
            extra = ""
            if attached:
                extra = "Файли: " + ", ".join(attached)
                lead.internal_notes = (lead.internal_notes or "") + f"\n[КП] {extra}"

            lead.save()

            CallLog.objects.create(
                company=lead,
                operator=request.user,
                event_type=CallLog.EventType.PROPOSAL_SENT,
                result="info",
                comment="КП відправлено менеджером" + (f" ({extra})" if extra else ""),
            )
            message_id = request.POST.get("message_id")
            if message_id:
                message = get_object_or_404(GeneratedMessage, pk=message_id, company=lead)
                message.body = request.POST.get("message_body", message.body)
                message.status = GeneratedMessage.Status.SENT
                message.sent_at = timezone.now()
                message.save(update_fields=["body", "status", "sent_at"])
            return redirect("manager:tasks")

        # --- Взяти в опрацювання (для щойно створених, stage=new — щоб
        # заявка з публічної форми зникла з "Задач" і почала свій шлях) ---
        if action == "start_processing":
            call_result = request.POST.get("call_result", "").strip()
            stage_for_result = {"success": "letter_sent", "refusal": "refusal", "wrong_number": "invalid"}
            lead.stage = stage_for_result.get(call_result, "in_progress")
            lead.assigned_to = lead.assigned_to or request.user
            lead.team = lead.team or request.user.team
            lead.next_action = {
                "letter_sent": Company.NextAction.PREPARE_PROPOSAL,
                "refusal": Company.NextAction.NONE,
                "invalid": Company.NextAction.NONE,
                "in_progress": Company.NextAction.FOLLOW_UP if call_result == "call_back" else Company.NextAction.CALL,
            }[lead.stage]
            lead.callback_date = timezone.now() + timedelta(days=1) if call_result == "call_back" else None
            if lead.stage == "letter_sent":
                lead.is_sent_by_manager = False
            lead.save(update_fields=["stage", "next_action", "callback_date", "is_sent_by_manager", "assigned_to", "team", "updated_at"])

            call_comment = request.POST.get("call_comment", "").strip()
            if call_result:
                CallLog.objects.create(
                    company=lead,
                    operator=request.user,
                    event_type=CallLog.EventType.CALL,
                    result=call_result,
                    comment=call_comment or "Перший контакт із заявки з сайту",
                )
            CallLog.objects.create(
                company=lead,
                operator=request.user,
                event_type=CallLog.EventType.STAGE_CHANGED,
                result="info",
                comment=f"stage → {lead.stage}; next_action → {lead.next_action}",
            )
            return redirect("manager:lead_detail", pk=pk)

        if action == "make_partner":
            lead.stage = "success"
            lead.next_action = Company.NextAction.THANK_PARTNER
            lead.callback_date = None
            lead.save(update_fields=["stage", "next_action", "callback_date", "updated_at"])

            CallLog.objects.create(
                company=lead,
                operator=request.user,
                event_type=CallLog.EventType.STAGE_CHANGED,
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
                lead.next_action = Company.NextAction.THANK_PARTNER
                lead.callback_date = timezone.now() + timedelta(days=1)
                lead.save(update_fields=["internal_notes", "next_action", "callback_date", "updated_at"])

                CallLog.objects.create(
                    company=lead,
                    operator=request.user,
                    event_type=CallLog.EventType.PARTNER_HELP,
                    result="success",
                    comment=f"Зафіксовано допомогу партнера: {extra}",
                )
            return redirect("manager:lead_detail", pk=pk)

        if action == "send_generated_message":
            message = get_object_or_404(GeneratedMessage, pk=request.POST.get("message_id"), company=lead)
            message.body = request.POST.get("message_body", message.body)
            message.status = GeneratedMessage.Status.SENT
            message.sent_at = timezone.now()
            message.save(update_fields=["body", "status", "sent_at"])
            if message.template and message.template.type == CommunicationTemplate.Type.PROPOSAL:
                lead.is_sent_by_manager = True
                lead.callback_date = timezone.now() + timedelta(days=3)
                lead.next_action = Company.NextAction.FOLLOW_UP
            elif message.template and message.template.type == CommunicationTemplate.Type.THANKS:
                lead.next_action = Company.NextAction.CONTACT_PARTNER
                lead.callback_date = None
            if message.template:
                lead.save(update_fields=["is_sent_by_manager", "callback_date", "next_action", "updated_at"])
            CallLog.objects.create(company=lead, operator=request.user,
                event_type=CallLog.EventType.PROPOSAL_SENT if message.template and message.template.type == CommunicationTemplate.Type.PROPOSAL else CallLog.EventType.COMMUNICATION_SENT,
                result="info", comment=f"Відправлено повідомлення «{message.template.name if message.template else 'шаблон'}»\n\n{message.body}")
            return redirect("manager:lead_detail", pk=pk)

    context = {
        "page": "lead",
        "lead": lead,
        "now": timezone.now(),
        "internal_notes_html": _sanitize_notes(lead.internal_notes or ""),
        "callback_date_input": timezone.localtime(lead.callback_date).strftime("%Y-%m-%dT%H:%M") if lead.callback_date else "",
        "min_callback_date_input": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
        "next_action_options": (
            [(Company.NextAction.CALL, Company.NextAction.CALL.label),
             (Company.NextAction.FOLLOW_UP, Company.NextAction.FOLLOW_UP.label)]
            if lead.stage == "in_progress" else
            [(Company.NextAction.PREPARE_PROPOSAL, Company.NextAction.PREPARE_PROPOSAL.label)]
            if lead.stage == "letter_sent" and not lead.is_sent_by_manager else
            [(Company.NextAction.FOLLOW_UP, Company.NextAction.FOLLOW_UP.label),
             (Company.NextAction.CALL, Company.NextAction.CALL.label)]
            if lead.stage == "letter_sent" else
            [(Company.NextAction.THANK_PARTNER, Company.NextAction.THANK_PARTNER.label),
             (Company.NextAction.CONTACT_PARTNER, Company.NextAction.CONTACT_PARTNER.label)]
            if lead.stage == "success" else []
        ),
        "next_action_value": lead.next_action,
        "call_logs": call_logs,
        "attachments": get_attachment_files(),
        "public_form_source": PUBLIC_FORM_SOURCE,
        "proposal_templates": CommunicationTemplate.objects.filter(type=CommunicationTemplate.Type.PROPOSAL, is_active=True),
        "thanks_templates": CommunicationTemplate.objects.filter(type=CommunicationTemplate.Type.THANKS, is_active=True),
        "generated_messages": lead.generated_messages.select_related("template", "author")[:20],
    }
    return render(request, "manager/lead_detail.html", context)


# ─────────────────────────────────────────────────────────────
# AI-генерация КП (персонализированный текст через LLM)
# ─────────────────────────────────────────────────────────────
@manager_required
@require_POST
def ai_generate_kp(request, pk):
    lead = _get_lead_or_403(request.user, pk)

    template_id = request.POST.get("template_id")
    if not template_id:
        return JsonResponse({"ok": False, "error": "Оберіть шаблон комунікації."}, status=400)
    template = get_object_or_404(CommunicationTemplate, pk=template_id, is_active=True)
    expected_type = CommunicationTemplate.Type.THANKS if lead.stage == "success" else CommunicationTemplate.Type.PROPOSAL
    if template.type != expected_type:
        return JsonResponse({"ok": False, "error": "Цей шаблон не відповідає типу комунікації."}, status=400)

    try:
        text = generate_communication(lead, template, request.user)
        message = GeneratedMessage.objects.create(company=lead, template=template, author=request.user, body=text)
        CallLog.objects.create(company=lead, operator=request.user,
            event_type=CallLog.EventType.TEMPLATE_GENERATED, result="info",
            comment=f"Підготовлено чернетку «{template.name}»")
        return JsonResponse({"ok": True, "text": text, "message_id": message.pk})
    except AIClientError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Внутрішня помилка: {e}"}, status=500)


# ─────────────────────────────────────────────────────────────
# Communication templates
# ─────────────────────────────────────────────────────────────
@manager_required
def templates_list(request):
    editing = None
    if request.method == "POST":
        template_id = request.POST.get("template_id")
        editing = get_object_or_404(CommunicationTemplate, pk=template_id) if template_id else CommunicationTemplate()
        template_type = request.POST.get("type", CommunicationTemplate.Type.PROPOSAL)
        if template_type not in CommunicationTemplate.Type.values:
            return JsonResponse({"error": "Невідомий тип комунікації."}, status=400)
        editing.type = template_type
        editing.name = request.POST.get("name", "").strip()
        editing.category = request.POST.get("category", "").strip()
        editing.description = request.POST.get("description", "").strip()
        editing.base_text = request.POST.get("base_text", "").strip()
        editing.ai_instruction = request.POST.get("ai_instruction", "").strip()
        editing.example_result = request.POST.get("example_result", "").strip()
        if editing.name and editing.base_text:
            editing.save()
            return redirect("manager:templates")
    edit_id = request.GET.get("edit")
    editing = get_object_or_404(CommunicationTemplate, pk=edit_id) if edit_id else editing
    context = {
        "page": "templates",
        "communication_templates": CommunicationTemplate.objects.all(),
        "editing": editing,
    }
    return render(request, "manager/templates_list.html", context)


@manager_required
@require_POST
def template_toggle(request, pk):
    template = get_object_or_404(CommunicationTemplate, pk=pk)
    template.is_active = not template.is_active
    template.save(update_fields=["is_active", "updated_at"])
    return redirect("manager:templates")
# ─────────────────────────────────────────────────────────────
# Карточка оператора
# ─────────────────────────────────────────────────────────────
@manager_required
def operator_detail(request, pk):
    operator = get_object_or_404(User, pk=pk)
    if not _is_owner(request.user):
        if operator.team_id != getattr(request.user, "team_id", None):
            return HttpResponseForbidden("Немає доступу до оператора іншої команди")

    stats = CallLog.objects.filter(
        operator=operator, event_type=CallLog.EventType.CALL
    ).aggregate(
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
    if not _is_owner(request.user):
        active_leads = active_leads.filter(team=request.user.team)

    partner_leads = Company.objects.filter(
        assigned_to=operator,
        stage="success"
    ).order_by("-updated_at")[:20]
    if not _is_owner(request.user):
        partner_leads = partner_leads.filter(team=request.user.team)

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

        stage = request.POST.get("stage", "in_progress")
        initial_action = {
            "new": Company.NextAction.CALL,
            "in_progress": Company.NextAction.CALL,
            "letter_sent": Company.NextAction.PREPARE_PROPOSAL,
            "success": Company.NextAction.THANK_PARTNER,
            "refusal": Company.NextAction.NONE,
            "invalid": Company.NextAction.NONE,
        }.get(stage, Company.NextAction.CALL)
        lead = Company(
            name=name,
            phones=request.POST.get("phones", "").strip() or None,
            city=request.POST.get("city", "").strip() or None,
            region=request.POST.get("region", "").strip() or None,
            address=request.POST.get("address", "").strip() or None,
            contact_person=request.POST.get("contact_person", "").strip() or None,
            emails=request.POST.get("emails", "").strip() or None,
            preferred_channel=request.POST.get("preferred_channel", "").strip() or None,
            internal_notes=_sanitize_notes(request.POST.get("internal_notes", "").strip()) or None,
            stage=stage,
            next_action=initial_action,
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
                event_type=CallLog.EventType.CALL,
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
    operators = _filter_users_by_team(operators, request.user)

    context = {
        "page": "operators",
        "operators": operators,
    }
    return render(request, "manager/operators_list.html", context)
