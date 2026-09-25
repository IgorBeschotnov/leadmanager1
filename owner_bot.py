"""
Owner-бот: продление доступа команд.

.env:
  OWNER_BOT_TOKEN=...   # токен отдельного бота владельца
  OWNER_TELEGRAM_IDS=123456789,987654321   # кто может продлевать (через запятую)

Запуск:
  python owner_bot.py
"""

import os
import sys
from pathlib import Path
from datetime import timedelta

import django
import telebot
from telebot import types
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "leadmanager1.settings")
django.setup()

from django.utils import timezone
from accounts.models import Team

TOKEN = os.getenv("OWNER_BOT_TOKEN") or os.getenv("OWNER_BOT_TOKEN".lower())
if not TOKEN:
    raise RuntimeError("В .env потрібен OWNER_BOT_TOKEN")

# Telegram user id власників (числа)
_raw_ids = os.getenv("OWNER_TELEGRAM_IDS", "")
OWNER_IDS = {int(x.strip()) for x in _raw_ids.split(",") if x.strip().isdigit()}

bot = telebot.TeleBot(TOKEN)

# user_id -> team_id, чекаємо пароль
waiting_password: dict[int, int] = {}

EXTEND_DAYS = 7
WARN_HOURS = 10


def is_owner(user_id: int) -> bool:
    if not OWNER_IDS:
        # якщо список порожній — пускаємо всіх (для першого тесту)
        return True
    return user_id in OWNER_IDS


def teams_expiring_soon():
    """Команди, у яких доступ закінчується протягом WARN_HOURS годин."""
    now = timezone.now()
    until = now + timedelta(hours=WARN_HOURS)
    return (
        Team.objects
        .filter(access_valid_until__isnull=False)
        .filter(access_valid_until__lte=until)
        .filter(access_valid_until__gte=now - timedelta(hours=1))
        .order_by("access_valid_until")
    )


def teams_need_attention():
    """Вже прострочені або скоро закінчаться."""
    now = timezone.now()
    until = now + timedelta(hours=WARN_HOURS)
    return (
        Team.objects
        .filter(access_valid_until__isnull=False)
        .filter(access_valid_until__lte=until)
        .order_by("access_valid_until")
    )


def format_team_line(t: Team) -> str:
    dt = t.access_valid_until
    if not dt:
        return f"{t.name} — без дати"
    local = timezone.localtime(dt)
    status = "⚠️ прострочено" if dt < timezone.now() else "⏳ скоро"
    return f"{t.name} — до {local.strftime('%d.%m.%Y %H:%M')} ({status})"


@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "Немає доступу.")
        return
    bot.reply_to(
        message,
        "Owner-бот.\n"
        "/expire — команди, яким скоро кінець доступу (або вже кінець)\n"
        "/teams — усі команди з датою доступу\n"
        "Оберіть команду кнопкою → введіть умовний пароль команди.",
    )


@bot.message_handler(commands=["teams"])
def cmd_teams(message):
    if not is_owner(message.from_user.id):
        return
    teams = Team.objects.exclude(access_valid_until__isnull=True).order_by("access_valid_until")
    if not teams.exists():
        bot.reply_to(message, "Немає команд з датою доступу.")
        return
    lines = [format_team_line(t) for t in teams]
    bot.reply_to(message, "Команди:\n" + "\n".join(lines))


@bot.message_handler(commands=["expire"])
def cmd_expire(message):
    if not is_owner(message.from_user.id):
        return
    send_expire_list(message.chat.id)


def send_expire_list(chat_id: int):
    teams = list(teams_need_attention())
    if not teams:
        bot.send_message(chat_id, "Немає команд на продовження зараз.")
        return

    text = (
        f"Команди з доступом ≤ {WARN_HOURS} год (або вже минув):\n"
        "Оберіть команду, потім надішліть її слово-пароль."
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    for t in teams:
        label = format_team_line(t)
        markup.add(
            types.InlineKeyboardButton(label[:60], callback_data=f"ext_{t.pk}")
        )
    bot.send_message(chat_id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("ext_"))
def on_pick_team(call):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "Немає доступу")
        return
    team_id = int(call.data.split("_", 1)[1])
    try:
        team = Team.objects.get(pk=team_id)
    except Team.DoesNotExist:
        bot.answer_callback_query(call.id, "Команду не знайдено")
        return

    waiting_password[call.from_user.id] = team.pk
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        f"Команда: **{team.name}**\n"
        f"Надішліть слово-пароль для підтвердження "
        f"(те, що вказано в адмінці для цієї команди).",
        parse_mode="Markdown",
    )


@bot.message_handler(func=lambda m: m.from_user.id in waiting_password)
def on_password(message):
    if not is_owner(message.from_user.id):
        return
    team_id = waiting_password.pop(message.from_user.id, None)
    if not team_id:
        return
    try:
        team = Team.objects.get(pk=team_id)
    except Team.DoesNotExist:
        bot.reply_to(message, "Команду не знайдено.")
        return

    word = (message.text or "").strip()
    expected = (team.access_password_word or "").strip()
    if not expected:
        bot.reply_to(
            message,
            f"У команди «{team.name}» в адмінці не задано слово-пароль.",
        )
        return
    if word.lower() != expected.lower():
        bot.reply_to(message, "Невірне слово. Спробуйте /expire і оберіть знову.")
        return

    now = timezone.now()
    base = team.access_valid_until if team.access_valid_until and team.access_valid_until > now else now
    team.access_valid_until = base + timedelta(days=EXTEND_DAYS)
    team.save(update_fields=["access_valid_until"])
    local = timezone.localtime(team.access_valid_until)
    bot.reply_to(
        message,
        f"✅ «{team.name}» продовжено до {local.strftime('%d.%m.%Y %H:%M')} "
        f"(+{EXTEND_DAYS} днів).",
    )


def notify_owners_if_needed():
    """Виклик при старті: якщо є кого продовжувати — написати всім OWNER_IDS."""
    teams = list(teams_need_attention())
    if not teams or not OWNER_IDS:
        return
    for oid in OWNER_IDS:
        try:
            send_expire_list(oid)
        except Exception as e:
            print("notify error", oid, e)


if __name__ == "__main__":
    print("Owner-бот запущено")
    print("OWNER_IDS:", OWNER_IDS or "(порожньо = всі)")
    notify_owners_if_needed()
    bot.infinity_polling(skip_pending=True)