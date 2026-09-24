# leadmanager1

Новый проект взамен старого `leadmanager` — чистая пересборка под
согласованную схему БД (см. `docs/DECISIONS_DB_v2.md`).

## Быстрый старт

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Админка: http://127.0.0.1:8000/admin/

## Структура

- `accounts/` — Team, User (кастомная модель), UserCapability, AccessAuditLog
- `leads/` — Category, Company, CallLog
- `docs/DECISIONS_DB_v2.md` — решение по схеме, для переноса в центральный
  журнал решений (00_ШТАБ)

## Что перенести из старого проекта вручную

- `bot.py` (Telegram-бот) — старый `prozorro_collector.py` на паузе, не переносить
  как есть, дизайн скрапера/импорта под новую схему ещё не согласован
  (модуль 40_СКРАПЕР_ИМПОРТ)
- Тестовые данные для UI, если были

## Не перенесено из старой модели (осознанно)

- `edrpou` — убран ещё в старом проекте, дедуп теперь через
  `phone_normalized`
- Отдельная модель `Contact` — заменена на `contact_person` (см. решение)
- `Operator`, proxy-модели (`ActiveLead`, `Partner`, `Task`) — не
  восстанавливались

  ## Прод / сервер

- Сайт: `http://<IP>/` — публічна головна
- Кабінет: `/manager/` → задачі
- Адмінка: `/admin/`
- Бот: `python bot.py` (токен у `.env`: `BOT_TOKEN`)

### Кабінет
- **Задачі** — letter_sent, ще не відправлено менеджером
- **База** — робочі ліди (без new/refusal/success)
- **AI КП** — на картці ліда, потрібні Настройки AI в адмінці

### DataSource
Джерело відкривається для команд через M2M `teams` в адмінці (не поле is_released).
