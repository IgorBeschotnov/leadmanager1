"""
Шаблоны коммерческих предложений (КП).
Плейсхолдеры:
  {company_name}   — название компании
  {contact_name}   — контактное лицо (или «Коллеги» если пусто)
  {operator_name}  — имя оператора
  {city}           — город
"""

TEMPLATES = {
    "standard": {
        "name": "Стандартное",
        "channel_hint": "любой",
        "body": (
            "Доброго дня, {contact_name}!\n\n"
            "Мене звати {operator_name}. Я представляю реабілітаційний центр у м. Шахтарське.\n\n"
            "Ми шукаємо партнерів та спонсорів, які готові підтримати наших захисників. "
            "Компанія «{company_name}» ({city}) виглядає як потенційний партнер, тому звертаємось саме до вас.\n\n"
            "Готові надіслати детальну пропозицію та відповісти на будь-які питання.\n\n"
            "З повагою,\n{operator_name}"
        ),
    },
    "short_messenger": {
        "name": "Коротке (месенджер)",
        "channel_hint": "Telegram / Viber / WhatsApp",
        "body": (
            "Вітаю, {contact_name}! 👋\n\n"
            "Я {operator_name} з реабілітаційного центру (Шахтарське).\n"
            "Шукаємо партнерів для підтримки захисників.\n\n"
            "«{company_name}» — цікава для співпраці. Можу надіслати коротке КП?\n\n"
            "Дякую!"
        ),
    },
    "official_email": {
        "name": "Офіційне (email)",
        "channel_hint": "Email",
        "body": (
            "Шановний(а) {contact_name}!\n\n"
            "Мене звати {operator_name}, я представляю реабілітаційний центр у місті Шахтарське.\n\n"
            "Звертаємося до компанії «{company_name}» з пропозицією партнерства / спонсорської підтримки "
            "наших військових, які проходять реабілітацію.\n\n"
            "Будемо вдячні за можливість надіслати офіційну комерційну пропозицію "
            "та обговорити можливі формати співпраці.\n\n"
            "З повагою,\n"
            "{operator_name}\n"
            "Реабілітаційний центр, м. Шахтарське"
        ),
    },
}


def render_template(template_key: str, company, operator_name: str = "") -> str:
    """Подставляет плейсхолдеры и возвращает готовый текст."""
    tpl = TEMPLATES.get(template_key)
    if not tpl:
        return ""

    contact = company.contact_person or "Колеги"
    return tpl["body"].format(
        company_name=company.name or "Компанія",
        contact_name=contact,
        operator_name=operator_name or "менеджер",
        city=company.city or "",
    )


def get_templates_list():
    """Список шаблонов для UI."""
    return [
        {"key": key, "name": data["name"], "channel_hint": data["channel_hint"]}
        for key, data in TEMPLATES.items()
    ]


# ─── Файли для прикріплення (папка attachments/) ───
from pathlib import Path

ATTACHMENTS_DIR = Path(__file__).resolve().parent / "attachments"


def get_attachment_files():
    """Повертає список файлів з папки attachments/."""
    if not ATTACHMENTS_DIR.exists():
        return []
    files = []
    for f in sorted(ATTACHMENTS_DIR.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "path": str(f),
            })
    return files
