"""
Генерация персонализированного КП.
"""
from .models import AISettings
from .client import call_chat_completion, AIClientError


CHANNEL_HINTS = {
    "email": "Повне звернення для email. Можна використати структуру з таблицями/списками. До 2000 символів.",
    "telegram": "Коротке повідомлення для Telegram (до 900 символів). Без таблиць, тільки текст.",
    "viber": "Коротке повідомлення для Viber (до 900 символів). Без таблиць.",
    "whatsapp": "Дуже коротке повідомлення для WhatsApp (до 600 символів).",
}

TONE_HINTS = {
    "emotional": "Емоційний, теплий, з акцентом на людях і довірі.",
    "official": "Офіційний, стриманий, діловий.",
    "short": "Максимально короткий і по суті.",
}

VOLUME_HINTS = {
    "short": "Короткий варіант.",
    "medium": "Середній обсяг.",
    "full": "Повний текст, близький до базового зразка.",
}


def build_prompt(company, channel: str, tone: str, volume: str, inserts: dict, base_kp: str) -> str:
    categories = ""
    if hasattr(company, "categories"):
        cats = list(company.categories.values_list("name", flat=True))
        categories = ", ".join(cats) if cats else "не вказано"

    contact = getattr(company, "contact_person", None) or "Колеги"
    city = getattr(company, "city", None) or ""
    region = getattr(company, "region", None) or ""

    channel_h = CHANNEL_HINTS.get(channel, CHANNEL_HINTS["email"])
    tone_h = TONE_HINTS.get(tone, TONE_HINTS["official"])
    volume_h = VOLUME_HINTS.get(volume, VOLUME_HINTS["medium"])

    inserts_block = "\n".join(
        f"- {k}: {v}" for k, v in inserts.items() if v
    ) or "немає"

    return f"""Ти пишеш персоналізоване звернення про гуманітарну допомогу.

=== БАЗОВИЙ ТЕКСТ (еталон, адаптуй під одержувача) ===
{base_kp}

=== ДАНІ ОРГАНІЗАЦІЇ-ОДЕРЖУВАЧА ===
Назва: {company.name}
Місто: {city}
Регіон: {region}
Категорії: {categories}
Контактна особа: {contact}

=== ПАРАМЕТРИ ===
Канал: {channel} — {channel_h}
Тон: {tone} — {tone_h}
Обсяг: {volume} — {volume_h}

=== ВСТАВКИ МЕНЕДЖЕРА ===
{inserts_block}

=== ВИМОГИ ===
1. Пиши українською.
2. Збережи ключові факти про підопічних і потреби з базового тексту.
3. Персоналізуй під назву і (якщо є) категорію організації.
4. Не вигадуй реквізити, телефони, IBAN — бери тільки з базового тексту.
5. Якщо канал месенджер — не роби таблиць, пиши коротко.
6. В кінці залиш місце під реквізити / контакти з базового тексту (якщо вони там є).
7. Поверни ТІЛЬКИ готовий текст листа, без коментарів і пояснень.
"""


def generate_kp(
    company,
    channel: str = "email",
    tone: str = "official",
    volume: str = "medium",
    inserts: dict | None = None,
) -> str:
    """
    Генерує текст КП.
    Raises AIClientError при помилках API / відсутності налаштувань.
    """
    settings = AISettings.get_active()
    if not settings:
        raise AIClientError("Немає активних налаштувань AI. Додай їх в адмінці.")

    if not settings.api_key:
        raise AIClientError("API Key не вказано в налаштуваннях AI.")

    if not settings.base_kp_text.strip():
        raise AIClientError("Базовий текст КП порожній. Заповни його в адмінці.")

    inserts = inserts or {}
    user_prompt = build_prompt(
        company=company,
        channel=channel,
        tone=tone,
        volume=volume,
        inserts=inserts,
        base_kp=settings.base_kp_text,
    )

    messages = []
    if settings.system_prompt.strip():
        messages.append({"role": "system", "content": settings.system_prompt.strip()})
    messages.append({"role": "user", "content": user_prompt})

    return call_chat_completion(
        api_key=settings.api_key,
        model=settings.model_name,
        messages=messages,
        base_url=settings.api_base_url,
        temperature=0.35,
        max_tokens=2200,
    )
