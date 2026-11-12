# FRONTEND_HANDOFF — после Ф3 (ПАУЗА 2)

## Готово
- Коммиты: Ф0–Ф1 `b132ddd`, Ф2 `d619f84`, Ф3 — последний (`git log -3`). Ветка `frontend-v1`.
- `npm run verify` зелёный: типы, 29 тестов Vitest, `check:money`, сборка в `web/`. `pytest` после правок бэкенда — 309 зелёных.
- `npm run scenario` — шаги 1–10 раздела 8 кликами в Chromium, дважды подряд с одинаковыми цифрами, ошибок консоли нет.
- Экраны: Вход, Пульс, Структура (дерево, инспектор, влияние, расследование), карточка отклонения (5 шагов, флажок решения, pending, до/после, «Глазами»), портфель «Решения», «Что изменилось» после перемотки.
- Заглушки: Заказы, Источники, Команда, Моя смена, Словарь, Журнал, конструктор (`screens/Stub.tsx`).

## Карта кода (`frontend/src`)
- `api/` — client (X-User, ошибки), hooks (запросы, ключ с логином), deviationHooks (карточка, мутации, «Что изменилось»), types.
- `lib/` — format, time, status, permissions, pulse, panel, graph (видимость дерева), impact (7.3), transitions, changes, audit; тесты `*.test.ts`.
- `ui/` — дизайн-система (Status, Values, Sparkline, KpiChart, Provenance, Refs, Tile, ChainStepper, Inspector, GlossaryHint, Floating, States, Toast, ConfirmDialog).
- `shell/` — Shell, DemoClock, InspectorHost, ChangesPanel. `inspector/` — NodePanel, KpiBlock, OtherPanels (связь, событие).
- `screens/` — login, pulse, tree (Tree, OrgNode, WeightEdge, layout ELK, TraceStrip), deviation (карточка), deviations (портфель), uikit, Home, Stub.
- `scripts/` — check-money, gen-fixtures, shots, scenario.

## Как запускать
- Бэкенд: `.venv313/Scripts/python.exe run.py --reset --port 8790 --data <временная папка>`
- Dev: `cd frontend && npm run dev` (прокси на 8790). Сборка `npm run build`, проверка `npm run verify`.
- Скриншоты `npm run shots [-- фильтр]`, сценарий `npm run scenario` (нужен собранный `web/` и бэкенд на 8790).

## Решения и отступления
- DECISIONS, строки `FE:` (Ф2: раскладка, «только проблемные», тултип без статуса точек; Ф3: trace из кэша карточки, полоса расследования на холсте, флажок решения, срок 09:00).

## Правки после паузы 1 (сделаны)
- Жёлтая кнопка на плитке «Качество» видна на 1366×768 без прокрутки (`pulse-director-1366.png`).
- `run.py`: Python 3.11–3.13, иначе понятное сообщение; `python run.py --check`; README — раздел «Интерфейс».
- «Глазами другой роли» есть и на дереве (`tree-as-head_client-1366.png`).

## Известные дыры
- Межфункциональная связь Поддержка → Сборка у директора идёт петлёй (узлы в одном слое).
- Карточка заказа в инспекторе — заглушка до Ф4; чипы заказов уже ведут туда.

## Дальше (порядок после паузы)
Заказы 8×4 и конвейер → минимум конструктора → Словарь, Журнал, домашние экраны ролей → гид, `DEMO_SCRIPT.md`, README, отчёт, чистая машина → Источники, Команда, Моя смена, импорт/экспорт, Ctrl+K.

## Вопросы
- Время сдачи 13.11.
