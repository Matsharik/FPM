# Photoprint-Tracker-2 / «Фотопринт Manage» (FPM): фронтенд Трека 1 (Space Hackathon, сдача 13.11.2026)

Главная инструкция: `docs/FRONTEND_PROMPT.md` (всё, что ниже строки `---`). План — `docs/FRONTEND_PLAN.md`.
Бэкенд готов (ветка `backend-v3`, отчёт `BACKEND_REPORT.md`, контракт `docs/FRONTEND_CONTRACT.md`).

## Жёсткие правила (действуют всегда)
- Ветка `frontend-v1`. Один коммит на фазу, сообщение начинается с «Ф<N>:». В `main` не коммить, `git push` не выполняй.
- Бэкенд не меняешь. Исключение — минимальные правки, согласованные с владельцем (статика, печать адреса в `run.py`); каждая — в `docs/DECISIONS.md` и с прогоном `pytest`.
- `timeseries/` не трогай.
- Никаких денег: ни валютных знаков и кодов, ни сумм, ни переключателя денег. `npm run check:money` должен проходить.
- Никакой сети и LLM в рантайме, ничего из CDN. Шрифт и иконки — локально.
- В интерфейсе только данные API. Фикстуры — только для `#/ui` и тестов.
- Не префетчить `GET /api/nodes/{id}` и `GET /api/deviations/{id}` (пишут журнал).
- Паузы после Ф1 и Ф3: коммит, `web/` пересобран, `docs/FRONTEND_HANDOFF.md`, отчёт до 15 строк, остановка до слова «продолжай».
- Решения по ходу — строкой `FE: …` в `docs/DECISIONS.md`.
- В новой сессии читай `docs/FRONTEND_PLAN.md`, `docs/FRONTEND_HANDOFF.md`, `docs/DECISIONS.md` (строки `FE:`) и `git log -10`. Весь репозиторий заново не перечитывай. Субагентов не запускай.

## Команды
Python — `.venv313` (3.13). `python` в PATH указывает на пустой `.venv` с 3.15, им не пользуйся.
- Бэкенд для разработки: `.venv313/Scripts/python.exe run.py --port 8790 --data <временная папка> [--reset]`
- Фронт: `cd frontend && npm run dev` (прокси `/api` → 8790), `npm run build` (в `../web`), `npm run verify` (типы + тесты + check:money + сборка)
- Скриншоты: `cd frontend && npm run shots` (Playwright, нужен запущенный бэкенд с собранным `web/`)
- Тесты бэкенда: `.venv313/Scripts/python.exe -m pytest -q`

## Стиль
- TypeScript strict, React 19, CSS Modules + `src/styles/tokens.css`. Тексты интерфейса — по-русски, предложения с заглавной.
- Числа `ru-RU`, время — Europe/Minsk, «сейчас» — только из `/api/demo/clock`.
