"""Собрать ``docs/api.md``: контракт для фронтенда с примерами из сид-данных.

    python scripts/gen_api_docs.py

Скрипт поднимает приложение в памяти на временной папке данных, делает
``reset`` и проходит режимы раздела 8 настоящими запросами. Ответы
сокращаются (длинные списки — первые элементы и «… ещё N»). Нужен httpx из
``requirements-dev.txt``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api.server import create_app  # noqa: E402

OUT = ROOT / "docs" / "api.md"
BASE = "http://127.0.0.1:8000"
MAX_ITEMS = 2
MAX_SERIES = 3
MAX_TEXT_LINES = 45

HEADER = """# API трекера «Фотопринт» — контракт для фронтенда

Сгенерировано `python scripts/gen_api_docs.py` по демо-данным после `reset`
(время стенда 2026-11-23 09:00 +03:00). Полная схема — `docs/openapi.json`
и `/docs` запущенного сервера. Длинные списки в примерах сокращены:
`"… ещё N"` значит, что в настоящем ответе элементов больше.

## Общие правила

- Пользователь — заголовок `X-User: <login>` (паролей нет, в продакшне — SSO/AD).
  Без заголовка — `401` везде, кроме `GET /health` и `GET /api/auth/users`.
  Логины: `director`, `head_client`, `head_prod`, `qc_otk`, `builder`.
- Чужая зона: детали — `403 out_of_zone`, списки фильтруются, цифры чужих
  узлов не отдаются (граничные узлы серые, этапы заказов урезаны).
- Ошибки всегда в одном формате:
  `{"error": {"code": "...", "message": "...", "details": {...}}}`.
- Время — ISO-8601 с поясом. Все «сейчас» — часы стенда (`GET /api/demo/clock`).
- Единицы: `units=natural` (по умолчанию) или `relative`; `money` выключен
  по ТЗ (`400 money_disabled`). Денежных сумм в API нет.

### Как отправлять запросы с кириллицей на Windows

В Git Bash `curl -d '{"name": "Закупки"}'` портит кириллицу. Тело кладите в файл
в UTF-8 и передавайте `-d @body.json`:

```bash
curl -s -X POST http://127.0.0.1:8000/api/builder/nodes \\
  -H "X-User: builder" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```

В PowerShell:

```powershell
$body = '{"name": "Закупки", "type": "department"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/builder/nodes `
  -Headers @{ "X-User" = "builder" } -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```
"""


def shrink(value: Any, key: str = "") -> Any:
    limit = MAX_SERIES if key in ("points", "flags", "kpi_links", "links", "steps") else MAX_ITEMS
    if isinstance(value, list):
        items = [shrink(item) for item in value[:limit]]
        if len(value) > limit:
            items.append(f"… ещё {len(value) - limit}")
        return items
    if isinstance(value, dict):
        return {k: shrink(v, k) for k, v in value.items()}
    return value


class Doc:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.parts: list[str] = [HEADER]

    def section(self, title: str, text: str = "") -> None:
        self.parts.append(f"\n## {title}\n")
        if text:
            self.parts.append(text + "\n")

    def call(self, method: str, path: str, user: str | None = "director", body: Any = None,
             params: dict[str, Any] | None = None, note: str = "", full: bool = False) -> Any:
        headers = {"X-User": user} if user else {}
        response = self.client.request(method, path, headers=headers, json=body, params=params)
        query = ("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else ""
        self.parts.append(f"\n### {method} {path}{query}\n")
        if note:
            self.parts.append(note + "\n")
        user_part = f'-H "X-User: {user}" ' if user else ""
        curl = f"curl -s {'-X ' + method + ' ' if method != 'GET' else ''}{user_part}\"{BASE}{path}{query}\""
        if body is not None:
            self.parts.append("Тело запроса:\n\n```json\n" + json.dumps(shrink(body), ensure_ascii=False, indent=2) + "\n```\n")
            curl += ' -H "Content-Type: application/json; charset=utf-8" -d @body.json'
        self.parts.append(f"```bash\n{curl}\n```\n")
        try:
            data = response.json()
        except ValueError:
            data = response.text
        shown = data if full else shrink(data)
        if isinstance(shown, str) and len(shown.splitlines()) > MAX_TEXT_LINES:
            lines = shown.splitlines()
            shown = "\n".join(lines[:MAX_TEXT_LINES] + [f"# … ещё {len(lines) - MAX_TEXT_LINES} строк"])
        text = json.dumps(shown, ensure_ascii=False, indent=2) if not isinstance(shown, str) else shown
        lang = "json" if not isinstance(shown, str) else "yaml"
        self.parts.append(f"Ответ `{response.status_code}`:\n\n```{lang}\n{text}\n```\n")
        return data


def node(client: TestClient, name: str) -> int:
    nodes = client.get("/api/nodes", params={"name": name}, headers={"X-User": "director"}).json()
    return next(item["id"] for item in nodes if item["name"] == name)


def build(client: TestClient) -> str:
    doc = Doc(client)
    support, assembly, production = node(client, "Поддержка"), node(client, "Сборка"), node(client, "Производство")
    otk_person = node(client, "Контролёр ОТК Иванова")

    doc.section("Вход", "Режим для всех: выбор пользователя и его профиль (слайд 5 ТЗ).")
    doc.call("GET", "/api/auth/users", None, full=True)
    doc.call("GET", "/api/me", "head_prod")

    doc.section("Обзор (главный экран)", "8 плиток в зоне пользователя и сводка портфеля решений (слайд 3).")
    doc.call("GET", "/api/overview")

    doc.section("Граф KPI", "Узлы зоны, связи с весами и долями, серые граничные узлы.")
    doc.call("GET", "/api/graph", "head_prod",
             note="У `head_prod` «Поддержка» — граничный узел сверху (`boundary: upstream`) с одним KPI.")
    doc.call("GET", f"/api/nodes/{assembly}")
    doc.call("GET", "/api/analysis/contributions", params={"node": support, "kpi": "defect_tickets_share"})

    doc.section("Детали", "KPI узла, ряды с флажками и аннотациями, прогноз, режим единиц.")
    doc.call("GET", f"/api/nodes/{assembly}/kpis", params={"units": "relative"})
    doc.call("GET", f"/api/kpi/{assembly}/defect_rate",
             params={"from": "2026-11-10T00:00:00+03:00", "to": "2026-11-23T09:00:00+03:00", "agg": "day"})
    doc.call("GET", f"/api/kpi/{assembly}/defect_rate/forecast", params={"horizon": 14})

    doc.section("Расследование", "Сигнал → контекст → причина (слайд 4).")
    doc.call("GET", "/api/analysis/trace", params={"node": support, "kpi": "defect_tickets_share"})
    doc.call("GET", "/api/deviations/DEV-0001")

    doc.section("Решения (портфель)", "Главный критерий: решение сохранено и перепроверено.")
    doc.call("GET", "/api/deviations")
    suggestion = doc.call("GET", "/api/deviations/DEV-0001/suggest")["suggestions"][0]
    doc.call("GET", "/api/deviations/DEV-0001/orders")
    doc.call("PATCH", "/api/deviations/DEV-0001", body={
        "status": "assigned",
        "action": {"text": suggestion["action"], "owner_login": "head_prod", "due_at": suggestion["due_at"],
                   "playbook_ref": suggestion["id"]},
    })
    doc.call("POST", "/api/demo/advance", params={"days": 7}, note="Перемотка демо-времени (см. «Демо»).")
    doc.call("POST", "/api/admin/deviations/DEV-0001/recheck")

    doc.section("Поток заказов", "8 этапов × событие, статус, владелец, проверяемый результат (слайд 2).")
    doc.call("GET", "/api/flow/summary")
    orders = doc.call("GET", "/api/orders", params={"product_line": "Выпускные альбомы", "stage": 5, "status": "defect"})
    if orders["items"]:
        doc.call("GET", f"/api/orders/{orders['items'][0]['order_id']}", full=True)
        doc.call("GET", f"/api/orders/{orders['items'][0]['order_id']}", "head_client",
                 note="Этапы производства для `head_client` урезаны (`visible: false`).")

    doc.section("Источники", "Пять систем в едином слое (слайд 1). Только чтение.")
    doc.call("GET", "/api/sources")
    doc.call("GET", "/api/events", params={"type": "annotation", "limit": 3})

    doc.section("Конструктор", "Роль builder: узлы, KPI, связи и веса за минуты (раздел 8.1).")
    doc.call("POST", "/api/builder/glossary", "builder", body={
        "key": "incoming_defect_share", "title": "Входной брак материалов", "source": "erp",
        "owner": "Зам. по производству", "unit": "%", "direction": "lower_better", "priority": "quality",
        "tile": "quality", "stage": 5, "display": {"relative": "pct_of_target", "natural": "%"},
        "thresholds": {"default": {"target": 1.0, "warn": 2.0, "crit": 3.0}},
    })
    new = doc.call("POST", "/api/builder/nodes", "builder",
                   body={"name": "Закупки", "type": "department", "owner": "Зам. по производству"})
    doc.call("POST", f"/api/builder/nodes/{new['id']}/kpis", "builder",
             body={"name": "incoming_defect_share", "metric": "incoming_defect_share", "pinned": True})
    doc.call("POST", "/api/builder/links", "builder", body={
        "from_node": assembly, "from_kpi": "defect_rate", "to_node": new["id"],
        "to_kpi": "incoming_defect_share", "weight": 0.2, "note": "Брак материалов поставщика"},
        note="Остальные веса KPI пропорционально умножились на 0,8 (`kpi_links`).")
    links = client.get("/api/links", params={"from_node": support, "from_kpi": "defect_tickets_share"},
                       headers={"X-User": "builder"}).json()
    doc.call("PUT", f"/api/builder/kpis/{support}/defect_tickets_share/weights", "builder",
             body={"weights": {link["id"]: weight for link, weight in zip(links, (0.6, 0.25, 0.15))}})
    doc.call("GET", "/api/builder/validate", "builder")
    doc.call("GET", "/api/builder/export", "builder", params={"format": "yaml"},
             note="`format=json` (по умолчанию) — тот же документ объектом.")
    exported = client.get("/api/builder/export", headers={"X-User": "builder"}).json()
    doc.call("POST", "/api/builder/import", "builder", body=exported, params={"dry_run": "true"},
             note="Тело — документ `org.yaml` (JSON или YAML с `Content-Type: application/x-yaml`).")

    doc.section("Контроль качества", "Роль qc: очередь, ввод точек, флажки, личная статистика.")
    doc.call("GET", "/api/me/queue", "qc_otk")
    doc.call("GET", "/api/me/stats", "qc_otk")
    doc.call("POST", f"/api/qc/kpi/{otk_person}/tasks_done/points", "qc_otk",
             body={"ts": "2026-11-30T08:30:00+03:00", "value": 41})
    doc.call("POST", f"/api/qc/node/{otk_person}/flags", "qc_otk",
             body={"ts": "2026-11-30T08:30:00+03:00", "kind": "info", "label": "Обучение по новой обложке"})

    doc.section("Люди", "«Подчинённые: кто чем занимается» (роль admin).")
    doc.call("GET", f"/api/nodes/{production}/people", "head_prod")

    doc.section("Словарь", "Единый словарь метрик (слайд 5).")
    glossary = client.get("/api/glossary", headers={"X-User": "director"}).json()
    sample = {**{k: v for k, v in glossary.items() if k != "metrics"},
              "metrics": {"defect_rate": glossary["metrics"]["defect_rate"],
                          "…": f"ещё {len(glossary['metrics']) - 1} метрик"}}
    doc.parts.append("\n### GET /api/glossary\nОтвет сокращён до одной метрики.\n\n```bash\n"
                     f'curl -s -H "X-User: director" "{BASE}/api/glossary"\n```\n')
    doc.parts.append("```json\n" + json.dumps(sample, ensure_ascii=False, indent=2) + "\n```\n")

    doc.section("Журнал", "Единый журнал (слайд 5): директор видит всё, admin — свою зону, остальные — свои записи.")
    doc.call("GET", "/api/audit", params={"limit": 3})

    doc.section("Демо", "Воспроизводимый сценарий для жюри (admin и builder).")
    doc.call("GET", "/api/demo/clock")
    doc.call("POST", "/api/demo/reset", note="Пересоздаёт `data/` из `config/`: все правки выше стираются.")
    doc.call("GET", "/health", None)
    return "".join(doc.parts)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="photoprint-docs-") as tmp:
        app = create_app(ROOT / "config", Path(tmp) / "data", web_dir=Path(tmp) / "no-web")
        app.state.ws.demo.reset()
        text = build(TestClient(app))
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT}: {len(text.splitlines())} строк")


if __name__ == "__main__":
    main()
