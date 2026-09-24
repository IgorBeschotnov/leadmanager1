"""
Тонкий клиент к OpenAI-compatible API (Groq и др.).
"""
import requests
from django.conf import settings as django_settings


class AIClientError(Exception):
    pass


def call_chat_completion(
    api_key: str,
    model: str,
    messages: list[dict],
    base_url: str = "https://api.groq.com/openai/v1",
    temperature: float = 0.4,
    max_tokens: int = 2500,
    timeout: int = 60,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as e:
        raise AIClientError(f"Сеть: {e}") from e

    if resp.status_code == 429:
        raise AIClientError("Rate limit (429). Подожди немного и попробуй снова.")
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise AIClientError(f"HTTP {resp.status_code}: {detail}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise AIClientError(f"Неожиданный ответ API: {data}") from e
