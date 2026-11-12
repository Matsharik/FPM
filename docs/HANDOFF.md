# HANDOFF — состояние после Ф8 (сдача)

## Готово
- Все фазы Ф0–Ф8 закрыты. Ф6 `3c73eb2`, Ф7 `d163f5e`, Ф8 `4316306` + `c58b4e3`, контракт для фронтенда — последний коммит (`git log -5`). Таблица коммитов Ф0–Ф5 — `BACKEND_REPORT.md`.
- Тесты: `.venv313/Scripts/python.exe -m pytest -q` — 308 зелёных (≈2,5 мин; под нагрузкой до 10).
- Сервер: `.venv313/Scripts/python.exe run.py [--reset] [--clock ISO] [--port N] [--data DIR]`; печатает демо-логины и `/docs`.
- Приёмка: `python scripts/smoke_demo.py --start` — 14 шагов, на чистом клоне (3.13) 14 OK.
- Проверка чистой машины и чек-лист из 12 пунктов — `BACKEND_REPORT.md`.

## Документы для фронтенда
- `docs/FRONTEND_CONTRACT.md` — по экранам (вход, 8 плиток, граф, узел и ряды, карточка отклонения, поток заказов, подчинённые, словарь, журнал, конструктор, демо-время): эндпоинты, заголовки, настоящие запросы и ответы, различия по ролям, пустые состояния, ошибки, подводные камни, демо-сценарий с id, чего бэкенд не даёт.
  Пересборка: `python run.py --reset --port 8790`, затем `python scripts/gen_frontend_contract.py --base http://127.0.0.1:8790` (настоящие HTTP-запросы, только stdlib).
- `docs/api.md` — все режимы раздела 8 (`python scripts/gen_api_docs.py`, в памяти, нужен httpx).
- `docs/openapi.json` — схема (`python scripts/export_openapi.py`; тест падает, если файл устарел).
- После любой правки API перевыгрузить все три.

## Карта кода (Ф6–Ф8)
- `config/sources.yaml` — 5 источников, 8 этапов (владелец — первый существующий узел, норматив, критерий), заказы, аннотации.
- `core/sources.py`, `core/events.py` — источники и события (видимость, фильтры, аннотации).
- `core/orders.py` — заказы: `materialize` (будущее плана скрыто по часам), `view` (урезание чужих этапов), `query`, `flow_summary`, `dims_for`, `affected`.
- `core/overview.py` — 8 плиток; `core/orgio.py` — `validate`, `export`, `import_`.
- `seed/orders.py` — заказы, события, аннотации (чистая функция); `seed/generator.py` — фон с сезонной нагрузкой.
- `api/routers/flow.py`, `overview.py`, `builder.py` (+ validate/export/import).
- Тесты Ф6–Ф8: `test_flow`, `test_route_guard` (все маршруты: 401 и метки утечек), `test_no_money` (включая FRONTEND_CONTRACT), `test_fix_notes`, `test_builder_io`, `test_delivery`.

## Решения
- D86–D105 в `docs/DECISIONS.md`. Для фронтенда важны: D73 (скрытые вклады и путь trace), D86 (план заказов на 15 суток вперёд), D89 (видимость), D90 (dims и затронутые заказы), D103 (импорт не транзакционный).

## Известные дыры
- FIX_NOTES №6, №7, №9, №13, №14 и остатки №12, №15 — `BACKEND_REPORT.md`, раздел 4.
- Python 3.11 и 3.12 на этой машине не установлены — не проверялись; `pytest` в чистом клоне не запускался (нехватка памяти).
- `git fetch origin` зависает (нет учётных данных); сверка с `origin/main` не сделана.

## Открытые вопросы
- Смысл этапа 8 «Возврат» — уточнить у организаторов (D87).
