"""
Telegram-бот оператора для leadmanager1.

Запуск з кореня проєкту:
    python bot.py

Токен береться з .env:
    BOT_TOKEN=123456:ABC...
або
    TELEGRAM_BOT_TOKEN=123456:ABC...

Оператори — користувачі з capability=operator і заповненим telegram_id.
Прив'язка чату: хто написав /start з якого Telegram ID — той і оператор.
"""

import os
import sys
from pathlib import Path

import django
import telebot
from telebot import types, apihelper
from dotenv import load_dotenv

# --- шляхи і Django ---
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

apihelper.CONNECT_TIMEOUT = 30
apihelper.READ_TIMEOUT = 30

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadmanager1.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.db.models import Q
from leads.models import Company, CallLog, DataSource

User = get_user_model()

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN / TELEGRAM_BOT_TOKEN не знайдено. "
        "Додай рядок у файл .env у корені проєкту."
    )

bot = telebot.TeleBot(BOT_TOKEN)

# chat_id -> User.id (обраний оператор у цьому чаті)
current_operator: dict[int, int] = {}

# telegram user_id -> (company_id, chat_id) — очікуємо текст примітки
waiting_for_comment: dict[int, tuple[int, int]] = {}


# ─────────────────────────────────────────────────────────────
# Оператори з БД
# ─────────────────────────────────────────────────────────────
def get_operators_qs():
    """Користувачі з роллю operator (і бажано з telegram_id)."""
    return (
        User.objects
        .filter(capabilities__capability="operator", access_revoked=False)
        .distinct()
        .order_by("first_name", "username")
    )


def get_operator_by_telegram(telegram_id: int | str):
    """Знайти оператора за Telegram ID."""
    tid = str(telegram_id)
    return (
        User.objects
        .filter(
            telegram_id=tid,
            capabilities__capability="operator",
            access_revoked=False,
        )
        .distinct()
        .first()
    )


def get_operator_user(chat_id: int, from_user_id: int | None = None):
    """
    Повертає (User, display_name) для поточного чату.
    Пріоритет:
      1) явно обраний у current_operator
      2) користувач з telegram_id == from_user_id
      3) перший оператор у системі (fallback)
    """
    op_id = current_operator.get(chat_id)
    if op_id:
        try:
            user = User.objects.get(pk=op_id)
            return user, (user.name or user.username)
        except User.DoesNotExist:
            current_operator.pop(chat_id, None)

    if from_user_id:
        user = get_operator_by_telegram(from_user_id)
        if user:
            current_operator[chat_id] = user.pk
            return user, (user.name or user.username)

    user = get_operators_qs().first()
    if user:
        current_operator[chat_id] = user.pk
        return user, (user.name or user.username)

    return None, "—"

def get_new_lead_for_operator(user):
    """
    Новый лид только из источников, открытых для команды оператора.
    team у оператора обязателен.
    """
    team = getattr(user, "team", None)
    if not team:
        return None

    released_keys = list(
        DataSource.objects.filter(teams=team).values_list("key", flat=True)
    )

    # Сырой пул (team пустой) или уже этой команды; статус new
    qs = (
        Company.objects
        .filter(stage="new")
        .filter(Q(team__isnull=True) | Q(team=team))
    )

    if released_keys:
        qs = qs.filter(
            Q(source__in=released_keys)
            | Q(source__isnull=True)
            | Q(source="")
        )
    else:
        # Нет открытых источников — только лиды без source
        qs = qs.filter(Q(source__isnull=True) | Q(source=""))

    return qs.order_by("created_at").first()
# ─────────────────────────────────────────────────────────────
# Клавіатури
# ─────────────────────────────────────────────────────────────
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📞 Прислать новый лид"),
        types.KeyboardButton("🔄 На повторный дозвон"),
    )
    markup.add(types.KeyboardButton("👤 Сменить оператора"))
    return markup


def get_operator_select_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for op in get_operators_qs():
        label = op.name or op.username
        extra = f" (tg:{op.telegram_id})" if op.telegram_id else ""
        markup.add(types.InlineKeyboardButton(
            f"👤 {label}{extra}",
            callback_data=f"opselect_{op.pk}",
        ))
    if not markup.keyboard:
        markup.add(types.InlineKeyboardButton(
            "⚠️ Немає операторів у БД", callback_data="noop"
        ))
    return markup


def get_lead_card_markup(company_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("ℹ️ Запросить полную информацию", callback_data=f"info_{company_id}"),
        types.InlineKeyboardButton("❌ Нет ответа", callback_data=f"res_noanswer_{company_id}"),
        types.InlineKeyboardButton("🚫 Не звонить", callback_data=f"res_donotcall_{company_id}"),
        types.InlineKeyboardButton("📝 Добавить примечание", callback_data=f"comment_{company_id}"),
        types.InlineKeyboardButton("🚀 Отклик (Отправить предложение)", callback_data=f"response_menu_{company_id}"),
    )
    return markup


def get_channel_select_markup(company_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💬 Телеграм", callback_data=f"send_tg_{company_id}"),
        types.InlineKeyboardButton("🟢 Вайбер", callback_data=f"send_viber_{company_id}"),
        types.InlineKeyboardButton("🟢 Ватсап", callback_data=f"send_whatsapp_{company_id}"),
        types.InlineKeyboardButton("📧 Почта", callback_data=f"send_email_{company_id}"),
        types.InlineKeyboardButton("📝 Добавить примечание", callback_data=f"comment_{company_id}"),
        types.InlineKeyboardButton("⬅️ Назад", callback_data=f"back_{company_id}"),
    )
    return markup


def get_note_only_markup(company_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(
        "📝 Добавить примечание", callback_data=f"comment_{company_id}"
    ))
    return markup


def send_lead_card(chat_id: int, company: Company, operator_name: str):
    phone = company.first_phone or "Телефон не указан"
    card_text = (
        f"👤 **Оператор:** {operator_name}\n"
        f"🏢 **Компания:** {company.name}\n"
        f"📍 **Город:** {company.city or 'Не указан'}\n"
        f"📞 **Телефон:** `{phone}`"
    )
    bot.send_message(
        chat_id, card_text,
        #parse_mode="Markdown",
        reply_markup=get_lead_card_markup(company.id),
    )


# ─────────────────────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_obj, operator_name = get_operator_user(
        message.chat.id, from_user_id=message.from_user.id
    )
    if not user_obj:
        bot.send_message(
            message.chat.id,
            "⚠️ У системі немає жодного оператора.\n"
            "Додай користувача з capability=operator і telegram_id в адмінці.",
        )
        return

    # якщо telegram_id ще порожній — підставимо
    if not user_obj.telegram_id:
        user_obj.telegram_id = str(message.from_user.id)
        user_obj.save(update_fields=["telegram_id"])

    bot.send_message(
        message.chat.id,
        f"Доброго дня! 🤝 Поточний оператор: **{operator_name}**.\n"
        f"Оберіть режим роботи:",
        #parse_mode="Markdown",
        reply_markup=get_main_menu(),
    )


@bot.message_handler(func=lambda m: m.text == "👤 Сменить оператора")
def handle_switch_operator(message):
    bot.send_message(
        message.chat.id,
        "Оберіть оператора зі списку:",
        reply_markup=get_operator_select_markup(),
    )


@bot.message_handler(func=lambda m: m.text in [
    "📞 Прислать новый лид", "🔄 На повторный дозвон"
])
def handle_lead_request(message):
    user_obj, operator_name = get_operator_user(
        message.chat.id, from_user_id=message.from_user.id
    )
    if not user_obj:
        bot.send_message(message.chat.id, "Спочатку налаштуй операторів у адмінці.")
        return

            company = get_new_lead_for_operator(user_obj)
        if not company:
            bot.send_message(
                message.chat.id,
                "🎉 Немає нових лідів для Вашої команди "
                "(перевірте відкриті джерела в адмінці).",
                reply_markup=get_main_menu(),
            )
            return
        company.stage = "in_progress"
        company.assigned_to = user_obj
        if user_obj.team_id and not company.team_id:
            company.team = user_obj.team
        company.save()
    else:
        company = (
            Company.objects
            .filter(stage="in_progress", assigned_to=user_obj)
            .order_by("updated_at")
            .first()
        )
        if not company:
            company = (
                Company.objects
                .filter(stage="in_progress")
                .order_by("updated_at")
                .first()
            )
        if not company:
            bot.send_message(
                message.chat.id,
                "📭 Немає лідів на повторний дозвон.",
                reply_markup=get_main_menu(),
            )
            return

    send_lead_card(message.chat.id, company, operator_name)


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    data = call.data
    parts = data.split("_")
    action = parts[0]

    if action == "noop":
        bot.answer_callback_query(call.id, "Немає операторів")
        return

    if action == "opselect":
        op_id = int(parts[1])
        try:
            user = User.objects.get(pk=op_id)
        except User.DoesNotExist:
            bot.answer_callback_query(call.id, "Оператор не знайдений")
            return
        current_operator[call.message.chat.id] = user.pk
        name = user.name or user.username
        bot.answer_callback_query(call.id, f"Оператор: {name}")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"👤 Поточний оператор: **{name}**",
            parse_mode="Markdown",
        )
        bot.send_message(
            call.message.chat.id,
            "Готово, продовжуйте роботу:",
            reply_markup=get_main_menu(),
        )
        return

    if action == "info":
        company_id = int(parts[1])
        company = Company.objects.get(id=company_id)
        last_log = (
            company.call_logs
            .exclude(comment__isnull=True)
            .exclude(comment__exact="")
            .order_by("-created_at")
            .first()
        )
        last_comment = (
            f"{last_log.comment} ({last_log.created_at.strftime('%d.%m %H:%M')})"
            if last_log else "Пометок пока нет"
        )
        info_text = (
            f"📋 **Полная информация:**\n"
            f"Название: {company.name}\n"
            f"Адрес/Город: {company.city or '—'}\n"
            f"Регион: {company.region or '—'}\n"
            f"Сайт: {company.website or 'Нет'}\n"
            f"Телефоны: {company.phones or 'Не указаны'}\n"
            f"Email: {company.emails or 'Не указан'}\n\n"
            f"📝 **Последняя пометка:** {last_comment}"
        )
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, info_text, parse_mode="Markdown")
        return

    if action == "res":
        sub_action = parts[1]
        company_id = int(parts[2])
        company = Company.objects.get(id=company_id)
        user_obj, operator_name = get_operator_user(
            call.message.chat.id, from_user_id=call.from_user.id
        )

        if sub_action == "noanswer":
            company.stage = "in_progress"
            company.save(update_fields=["stage", "updated_at"])
            CallLog.objects.create(
                company=company,
                operator=user_obj,
                result="call_back",
                comment="Нет ответа (перенесено на повтор)",
            )
            text_res = f"⚠️ Статус: Нет ответа (на повтор). Оператор: {operator_name}."
        else:
            company.stage = "refusal"
            company.save(update_fields=["stage", "updated_at"])
            CallLog.objects.create(
                company=company,
                operator=user_obj,
                result="refusal",
                comment="Не звонить / Отказ",
            )
            text_res = f"🚫 Компания в статусе 'Не звонить'. Оператор: {operator_name}."

        bot.answer_callback_query(call.id, "Сохранено!")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text_res,
        )
        return

    if action == "comment":
        company_id = int(parts[1])
        waiting_for_comment[call.from_user.id] = (company_id, call.message.chat.id)
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            "✍️ Напишіть текст примітки наступним повідомленням:",
        )
        return

    if action == "response":
        company_id = int(parts[2])
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_channel_select_markup(company_id),
        )
        return

    if action == "back":
        company_id = int(parts[1])
        bot.answer_callback_query(call.id)
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_lead_card_markup(company_id),
        )
        return

    if action == "send":
        channel = parts[1]
        company_id = int(parts[2])
        company = Company.objects.get(id=company_id)
        user_obj, operator_name = get_operator_user(
            call.message.chat.id, from_user_id=call.from_user.id
        )

        channel_names = {
            "tg": "Telegram",
            "viber": "Viber",
            "whatsapp": "WhatsApp",
            "email": "Email",
        }
        chosen = channel_names.get(channel, channel)

        company.stage = "letter_sent"
        company.preferred_channel = chosen
        company.is_sent_by_manager = False
        company.save()

        CallLog.objects.create(
            company=company,
            operator=user_obj,
            result="success",
            comment=(
                f"Запит на відправку КП через {chosen}. "
                f"Оператор: {operator_name}. Очікує менеджера."
            ),
        )

        bot.answer_callback_query(call.id, "Завдання передано менеджеру!")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                f"✅ **Запит зафіксовано!**\n"
                f"🏢 Компанія: {company.name}\n"
                f"📬 Канал: **{chosen}**\n"
                f"👤 Оператор: {operator_name}\n"
                f"⏳ Статус: у задачах менеджера."
            ),
            parse_mode="Markdown",
            reply_markup=get_note_only_markup(company_id),
        )
        return


@bot.message_handler(func=lambda m: m.from_user.id in waiting_for_comment)
def save_comment_text(message):
    user_id = message.from_user.id
    company_id, chat_id = waiting_for_comment.pop(user_id)

    company = Company.objects.get(id=company_id)
    user_obj, operator_name = get_operator_user(chat_id, from_user_id=user_id)

    CallLog.objects.create(
        company=company,
        operator=user_obj,
        result="call_back",
        comment=f"Примітка оператора ({operator_name}): {message.text}",
    )
    bot.send_message(
        message.chat.id,
        f"✅ Примітку збережено для **{company.name}**!",
        parse_mode="Markdown",
    )


if __name__ == "__main__":
    print("Бот запущено, очікую повідомлення...")
    print(f"Операторів у БД: {get_operators_qs().count()}")
    bot.infinity_polling(skip_pending=True)
