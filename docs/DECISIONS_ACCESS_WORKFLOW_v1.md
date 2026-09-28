# РЕШЕНИЯ: доступ, workflow, CallLog, роли (патч 2026-09-28)

**Статус:** принято (Игорь)  
**Код:** accounts/models, leads/models, manager_cabinet/views

---

## 1. Доступ к лидам

| Роль | Что видит |
|------|-----------|
| **owner** | Все команды + все сырые |
| **team_manager / operator** (staff кабинета) | Только `team = своя` + сырые из **открытых** DataSource |
| **servant** | Нет кабинета (только публичная карточка) |

- Сырые (`team=NULL`) **не** видны, пока owner не открыл `DataSource.teams`.
- Две команды могут брать из одной базы: в бот уходит `team=NULL`, в боте уже с именем команды. Чужие `team` не трогают.
- Если команда отключилась — другая добивает остаток, не звонит по лидам другой команды.

## 2. Роли (capabilities)

Рабочие в кабинете: `owner`, `team_manager`, `operator`.  
`servant` — только сайт.  
`collector` / `outreach` / `sales` — резерв, пока не проверяем.

Оператор в основном через Telegram-бот. Часто комбинация operator + manager-кабинет.  
Разница team_manager vs «менеджер»: КП уходит от имени team_manager (мягкое правило).

## 3. Workflow

```
NEW  →  (только после оператора/взятия)  →  IN_PROGRESS
                                              ├── REFUSAL   (не в кабинете менеджера)
                                              ├── INVALID   (не в кабинете менеджера)
                                              └── LETTER_SENT  (= КП реально отправлено)
                                                       ├── REFUSAL
                                                       ├── IN_PROGRESS  (повторный перезвон)
                                                       └── SUCCESS  (может «уснуть»)
```

- `new → refusal/invalid` только после работы оператора.
- `in_progress → new` — нет.
- `letter_sent → in_progress` — да (recall).
- Отдельный статус callback — не обязателен; есть `callback_date`.

## 4. CallLog = универсальная история

`event_type`:
- `call` — только это в статистике звонков
- `template_generated`
- `proposal_sent`
- `stage_changed`
- `partner_help`

AI-генерации **не** пишутся в CallLog (можно крутить много раз). Удачные шаблоны — позже.

## 5. Processed / архив

Раздел ` /manager/processed/ `:
- letter_sent + уже отправлено менеджером
- in_progress с просроченным callback_date
- success (партнёры для периодической работы)

refusal / invalid — **не** показываются менеджеру.

## 6. callback_date

- По умолчанию +3 дня при mark_sent.
- Менеджер может задать свою дату (action=set_callback / поле в mark_sent).
- Через дату появляется в очереди / processed.

## 7. КП (MVP)

Кнопка «КП отправлено» = ручная фиксация + пометка (канал/файлы/заметка в notes).  
Реальная отправка email/мессенджеров — позже.

## 8. DataSource

Сначала owner открывает источник команде → команда видит сырые → берёт в работу (team проставляется).

## 9. Дедуп

Только `phone_normalized`. ЕДРПОУ — не сейчас.

## 10. Категории

10–20 шт., через админку. Скрипт сортировки базы — отдельно перед наполнением.

## 11. Django

`Django>=5.2,<6.0` (LTS 5.2). Не поднимать на 6.x без явной нужды.

## 12. Отчёты

Только своя Team. Owner — все. Командам друг о друге ничего не видно.

---

## Миграции

```bash
python manage.py migrate accounts
python manage.py migrate leads
```

Файлы: `accounts/migrations/0005_capability_servant.py`, `leads/migrations/0004_calllog_event_type.py`.
