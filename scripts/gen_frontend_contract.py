"""Собрать ``docs/FRONTEND_CONTRACT.md`` настоящими HTTP-запросами к запущенному серверу.

    python run.py --reset --port 8790             # в отдельном окне
    python scripts/gen_frontend_contract.py --base http://127.0.0.1:8790

Скрипт сам делает ``POST /api/demo/reset`` и проходит экраны фронтенда: каждый
пример в документе — настоящий ответ сервера (длинные списки сокращены, это
помечено «… ещё N»). Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "FRONTEND_CONTRACT.md"
ROLES = ("director", "head_client", "head_prod", "qc_otk", "builder")
LIMIT = 2


def shrink(value: Any, limit: int = LIMIT) -> Any:
    if isinstance(value, list):
        items = [shrink(item, limit) for item in value[:limit]]
        if len(value) > limit:
            items.append(f"… ещё {len(value) - limit}")
        return items
    if isinstance(value, dict):
        return {key: shrink(item, limit) for key, item in value.items()}
    return value


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, user: str | None = "director", body: Any = None,
             params: dict[str, Any] | None = None) -> tuple[int, Any]:
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        headers = {"Accept": "application/json"}
        if user:
            headers["X-User"] = user
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw, status = response.read(), response.status
        except urllib.error.HTTPError as error:
            raw, status = error.read(), error.code
        text = raw.decode("utf-8")
        try:
            return status, json.loads(text) if text else None
        except json.JSONDecodeError:
            return status, text


class Doc:
    def __init__(self, api: Api) -> None:
        self.api = api
        self.lines: list[str] = []

    def text(self, value: str) -> None:
        self.lines.append(value.rstrip() + "\n")

    def example(self, method: str, path: str, user: str | None = "director", body: Any = None,
                params: dict[str, Any] | None = None, title: str = "", limit: int = LIMIT,
                pick: Any = None) -> Any:
        """Запрос, его curl и настоящий ответ (``pick`` — функция, выбирающая часть ответа)."""
        status, data = self.api.call(method, path, user, body, params)
        query = ("?" + urllib.parse.urlencode(params)) if params else ""
        head = f"**{title}** " if title else ""
        self.lines.append(f"\n{head}`{method} {path}{query}` от `{user or '— без X-User'}` → **{status}**\n\n")
        curl = ["curl -s"]
        if method != "GET":
            curl.append(f"-X {method}")
        if user:
            curl.append(f'-H "X-User: {user}"')
        if body is not None:
            curl.append('-H "Content-Type: application/json; charset=utf-8" -d @body.json')
            self.lines.append("```json\n// body.json\n" + json.dumps(body, ensure_ascii=False, indent=2) + "\n```\n")
        curl.append(f'"{self.api.base}{path}{query}"')
        self.lines.append("```bash\n" + " ".join(curl) + "\n```\n")
        shown = pick(data) if pick and status < 400 else data
        if isinstance(shown, str):
            lines = shown.splitlines()
            shown_text = "\n".join(lines[:30] + ([f"# … ещё {len(lines) - 30} строк"] if len(lines) > 30 else []))
            self.lines.append("```yaml\n" + shown_text + "\n```\n")
        else:
            self.lines.append("```json\n" + json.dumps(shrink(shown, limit), ensure_ascii=False, indent=2) + "\n```\n")
        return data

    def table(self, header: list[str], rows: list[list[Any]]) -> None:
        self.lines.append("\n| " + " | ".join(header) + " |\n|" + "---|" * len(header) + "\n")
        for row in rows:
            self.lines.append("| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |\n")
        self.lines.append("\n")


def status_of(api: Api, method: str, path: str, user: str | None, **kw: Any) -> str:
    status, body = api.call(method, path, user, **kw)
    code = body.get("error", {}).get("code") if isinstance(body, dict) and status >= 400 else None
    return f"{status}" + (f" `{code}`" if code else "")


def build(api: Api) -> str:
    sections: dict[str, Doc] = {}

    def section(key: str) -> Doc:
        sections[key] = Doc(api)
        return sections[key]

    status, reset = api.call("POST", "/api/demo/reset", "director")
    assert status == 200, reset
    ids = {node["name"]: node["id"] for node in api.call("GET", "/api/nodes", "director")[1]}
    support, assembly, production, otk = ids["Поддержка"], ids["Сборка"], ids["Производство"], ids["ОТК"]
    ivanova, finance = ids["Контролёр ОТК Иванова"], ids["Финансы"]
    clock = api.call("GET", "/api/demo/clock", "director")[1]

    # --- ошибки (до изменений стенда) ---
    d = section("errors")
    d.example("GET", "/api/overview", None, title="Нет X-User")
    d.example("GET", "/api/overview", "nobody", title="Неизвестный логин")
    d.example("GET", f"/api/nodes/{assembly}", "head_client", title="Чужая зона")
    d.example("POST", "/api/builder/nodes", "qc_otk", body={"name": "x"}, title="Роли действие не разрешено")
    d.example("GET", "/api/deviations/DEV-9999", "director", title="Нет объекта")
    d.example("GET", "/api/overview", "director", params={"units": "money"}, title="Деньги выключены")
    d.example("PATCH", "/api/deviations/DEV-0001", "director", body={"status": "verified"},
              title="Недопустимый переход")
    d.example("GET", "/api/orders", "director", params={"stage": 9}, title="Ошибка валидации (422 pydantic)")

    # --- вход ---
    d = section("login")
    d.example("GET", "/api/auth/users", None, limit=10)
    d.example("GET", "/api/me", "head_prod", limit=30)
    rows = []
    for role in ROLES:
        me = api.call("GET", "/api/me", role)[1]
        rows.append([role, me["role"], len(me["zone"]), me["sees_everything"], ", ".join(me["permissions"]) or "—"])
    d.table(["логин", "роль", "узлов в зоне", "sees_everything", "permissions"], rows)

    # --- обзор ---
    d = section("overview")
    d.example("GET", "/api/overview", "director", limit=8,
              pick=lambda b: {**b, "tiles": [b["tiles"][4]] + [f"… ещё {len(b['tiles']) - 1} плиток той же формы"]})
    rows = []
    for role in ("director", "head_client", "head_prod", "qc_otk"):
        body = api.call("GET", "/api/overview", role)[1]
        cells = [f"{t['key']}: {t['status']}/{t['kpis']}" for t in body["tiles"]]
        rows.append([role, body["zone_nodes"], "; ".join(cells), body["portfolio"]["total"]])
    d.table(["логин", "узлов в зоне", "плитка: статус / число KPI", "карточек в портфеле"], rows)
    d.example("GET", "/api/overview", "qc_otk", title="Пустые плитки у qc_otk",
              pick=lambda b: [t for t in b["tiles"] if t["kpis"] == 0][:1])

    # --- граф ---
    d = section("graph")
    d.example("GET", "/api/graph", "head_prod", limit=2,
              pick=lambda b: {"nodes": [n for n in b["nodes"] if n.get("boundary")] + ["… и узлы зоны"],
                              "links": [l for l in b["links"] if l["from_node"] == support][:2] + ["…"],
                              **{k: v for k, v in b.items() if k not in ("nodes", "links")}})
    rows = []
    for role in ("director", "head_client", "head_prod", "qc_otk"):
        body = api.call("GET", "/api/graph", role)[1]
        zone = [n for n in body["nodes"] if not n.get("boundary")]
        up = [n["name"] for n in body["nodes"] if n.get("boundary") == "upstream"]
        down = [n["name"] for n in body["nodes"] if n.get("boundary") == "downstream"]
        rows.append([role, len(zone), ", ".join(up) or "—", ", ".join(down) or "—", len(body["links"])])
    d.table(["логин", "узлов зоны", "серые сверху (upstream)", "серые снизу (downstream)", "связей"], rows)
    d.example("GET", "/api/analysis/contributions", "director", params={"node": support, "kpi": "defect_tickets_share"},
              limit=3)
    d.example("GET", "/api/analysis/contributions", "head_client",
              params={"node": support, "kpi": "defect_tickets_share"}, limit=3,
              title="Та же строка вкладов у head_client (цели вне зоны)")

    # --- карточка узла ---
    d = section("node")
    d.example("GET", f"/api/nodes/{assembly}", "head_prod", limit=2)
    d.example("GET", f"/api/nodes/{assembly}/kpis", "head_prod", params={"units": "natural"}, limit=1)
    d.example("GET", f"/api/kpi/{assembly}/defect_rate", "head_prod",
              params={"from": "2026-11-09T00:00:00+03:00", "agg": "day"}, limit=3,
              pick=lambda b: {**b, "points": b["points"][-3:],
                              "flags": [f for f in b["flags"] if f["kind"] == "annotation"] +
                                       [f for f in b["flags"] if f["kind"] != "annotation"]})
    d.example("GET", f"/api/kpi/{assembly}/defect_rate/forecast", "head_prod", params={"horizon": 7}, limit=2)
    d.example("GET", "/api/events", "head_prod", params={"type": "annotation"}, limit=2)
    d.table(["логин", f"GET /api/nodes/{assembly} (Сборка)", f"GET /api/kpi/{assembly}/defect_rate"], [
        [role, status_of(api, "GET", f"/api/nodes/{assembly}", role),
         status_of(api, "GET", f"/api/kpi/{assembly}/defect_rate", role)]
        for role in ("director", "head_client", "head_prod", "qc_otk")])
    d.example("GET", f"/api/kpi/{ivanova}/tasks_done", "qc_otk",
              params={"from": "2030-01-01T00:00:00+03:00"}, title="Пустой ряд (период без данных)")

    # --- карточка отклонения (до решения) ---
    d = section("deviation")
    d.example("GET", "/api/deviations/DEV-0001", "director", limit=3)
    d.example("GET", "/api/deviations/DEV-0001", "head_client", limit=3,
              title="Та же карточка у head_client (первопричина вне зоны)",
              pick=lambda b: {"cause": b["cause"], "signal": b["signal"], "affected_orders": b["affected_orders"]})
    d.table(["логин", "GET /api/deviations/DEV-0001", "портфель: карточек", "затронутых заказов"], [
        [role, status_of(api, "GET", "/api/deviations/DEV-0001", role),
         api.call("GET", "/api/deviations", role)[1]["summary"]["total"],
         (api.call("GET", "/api/deviations/DEV-0001/orders", role)[1] or {}).get("count", "—")
         if api.call("GET", "/api/deviations/DEV-0001/orders", role)[0] == 200 else "403"]
        for role in ("director", "head_client", "head_prod", "qc_otk")])
    d.example("GET", "/api/deviations/DEV-0001/suggest", "director", limit=3)
    d.example("GET", "/api/deviations/DEV-0001/orders", "director", limit=5)
    d.example("GET", "/api/deviations", "director", params={"status": "verified"}, title="Пустой фильтр портфеля",
              limit=3)
    d.example("GET", "/api/analysis/trace", "director", params={"node": support, "kpi": "defect_tickets_share"},
              limit=2)

    # --- поток заказов ---
    d = section("flow")
    d.example("GET", "/api/flow/summary", "director", limit=8,
              pick=lambda b: {**b, "stages": b["stages"][4:6]})
    orders = api.call("GET", "/api/orders", "director",
                      params={"product_line": "Выпускные альбомы", "stage": 5, "status": "defect"})[1]
    order_id = orders["items"][0]["order_id"]
    d.example("GET", "/api/orders", "director", params={"product_line": "Выпускные альбомы", "stage": 5,
                                                        "status": "defect", "limit": 2}, limit=8)
    d.example("GET", f"/api/orders/{order_id}", "director", limit=8,
              pick=lambda b: {**b, "stages": b["stages"][4:7]})
    d.example("GET", f"/api/orders/{order_id}", "head_client", limit=8, title="Тот же заказ у head_client",
              pick=lambda b: {**b, "stages": b["stages"][4:7]})
    rows = []
    for role in ("director", "head_client", "head_prod", "qc_otk"):
        summary = api.call("GET", "/api/flow/summary", role)[1]
        visible = [str(s["stage"]) for s in summary["stages"] if s["visible"]]
        rows.append([role, api.call("GET", "/api/orders", role)[1]["total"], ", ".join(visible) or "—",
                     status_of(api, "GET", f"/api/orders/{order_id}", role)])
    d.table(["логин", "заказов в списке", "этапы с цифрами в /flow/summary", f"GET /api/orders/{order_id}"], rows)
    d.example("GET", "/api/orders", "qc_otk", title="Пустой список (у ОТК нет своих этапов)")
    d.example("GET", "/api/sources", "director", limit=3, pick=lambda b: b[:1] + [f"… ещё {len(b) - 1} источника"])

    # --- подчинённые ---
    d = section("people")
    d.example("GET", f"/api/nodes/{production}/people", "head_prod", limit=2)
    d.table(["логин", f"GET /api/nodes/{production}/people"],
            [[role, status_of(api, "GET", f"/api/nodes/{production}/people", role)]
             for role in ("director", "head_client", "head_prod", "qc_otk")])
    d.example("GET", f"/api/nodes/{finance}/people", "director", title="Пустое состояние (у «Финансов» нет сотрудников)")
    d.example("GET", "/api/me/queue", "qc_otk", limit=2)
    d.example("GET", "/api/me/stats", "qc_otk", limit=2)

    # --- словарь ---
    d = section("glossary")
    d.example("GET", "/api/glossary", "qc_otk",
              pick=lambda b: {**{k: v for k, v in b.items() if k != "metrics"},
                              "metrics": {"defect_rate": b["metrics"]["defect_rate"],
                                          "…": f"ещё {len(b['metrics']) - 1} метрик"}})

    # --- демо-сценарий (меняет стенд) ---
    d = section("scenario")
    d.example("POST", "/api/demo/reset", "director", title="Шаг 0. Сброс")
    d.example("GET", "/api/overview", "director", title="Шаг 1. Обзор",
              pick=lambda b: [{"key": t["key"], "status": t["status"], "open_deviations": t["open_deviations"]}
                              for t in b["tiles"]], limit=8)
    d.example("GET", "/api/analysis/trace", "director", params={"node": support, "kpi": "defect_tickets_share"},
              title="Шаг 2. Trace", pick=lambda b: {"root_cause": b["root_cause"], "stopped_reason": b["stopped_reason"],
                                                     "path": [(s["node_name"], s["kpi"]) for s in b["steps"]],
                                                     "alternatives_last": [a["to_node_name"] for a in b["steps"][-1]["alternatives"]]})
    d.example("GET", "/api/deviations/DEV-0001", "director", title="Шаг 3. Карточка",
              pick=lambda b: {"status": b["status"], "signal": b["signal"], "dims": b["context"]["dims"],
                              "root": b["cause"]["root"], "affected": b["affected_orders"]["count"]})
    suggestion = d.example("GET", "/api/deviations/DEV-0001/suggest", "director", title="Шаг 4. Подсказка",
                           pick=lambda b: b["suggestions"][0])["suggestions"][0]
    assign = {"status": "assigned", "action": {"text": suggestion["action"], "owner_login": "head_prod",
                                               "due_at": suggestion["due_at"], "playbook_ref": suggestion["id"]}}
    d.example("PATCH", "/api/deviations/DEV-0001", "director", body=assign, title="Шаг 5. Назначить действие",
              pick=lambda b: {"status": b["status"], "action": b["action"], "history": b["history"][-1]})
    d.example("POST", "/api/admin/deviations/DEV-0001/recheck", "director", title="Шаг 6. Перепроверка сразу — pending",
              pick=lambda b: {"recheck": {k: b["recheck"][k] for k in ("result", "passed", "elapsed_days", "min_days")},
                              "status": b["deviation"]["status"]})
    d.example("POST", "/api/demo/advance", "director", params={"days": 7}, title="Шаг 7. Перемотка на 7 суток",
              limit=10)
    d.example("POST", "/api/admin/deviations/DEV-0001/recheck", "director", title="Шаг 8. Перепроверка — passed",
              pick=lambda b: {"recheck": b["recheck"], "status": b["deviation"]["status"],
                              "rechecks_total": len(b["deviation"]["rechecks"])})
    d.example("GET", "/api/deviations", "director", title="Шаг 9. Портфель", pick=lambda b: b["summary"])
    d.example("GET", "/api/deviations/DEV-0001", "head_client", title="Шаг 10. Та же карточка у head_client",
              pick=lambda b: {"status": b["status"], "rechecks": b["rechecks"][-1:]})

    # --- журнал (после действий) ---
    d = section("audit")
    d.example("GET", "/api/audit", "director", params={"limit": 3}, limit=3)
    d.example("GET", "/api/audit", "head_client", params={"limit": 3}, limit=3, title="head_client: своя зона")
    d.example("GET", "/api/audit", "qc_otk", title="qc_otk: только свои записи (пока пусто)")
    d.table(["логин", "записей видно (total)"],
            [[role, api.call("GET", "/api/audit", role, params={"limit": 1})[1]["total"]] for role in ROLES])

    # --- конструктор ---
    d = section("builder")
    d.example("GET", "/api/builder/validate", "builder")
    metric = {"key": "incoming_defect_share", "title": "Входной брак материалов", "source": "erp",
              "owner": "Зам. по производству", "unit": "%", "direction": "lower_better", "priority": "quality",
              "tile": "quality", "stage": 5, "display": {"relative": "pct_of_target", "natural": "%"},
              "thresholds": {"default": {"target": 1.0, "warn": 2.0, "crit": 3.0}}}
    d.example("POST", "/api/builder/glossary", "builder", body=metric, limit=3)
    node = d.example("POST", "/api/builder/nodes", "builder",
                     body={"name": "Закупки", "type": "department", "owner": "Зам. по производству"})
    d.example("POST", f"/api/builder/nodes/{node['id']}/kpis", "builder",
              body={"name": "incoming_defect_share", "metric": "incoming_defect_share", "pinned": True})
    d.example("POST", "/api/builder/links", "builder", limit=6, body={
        "from_node": assembly, "from_kpi": "defect_rate", "to_node": node["id"],
        "to_kpi": "incoming_defect_share", "weight": 0.2, "note": "Брак материалов поставщика"})
    d.example("GET", "/api/builder/validate", "builder", title="validate после: KPI без данных — предупреждение")
    d.example("GET", "/api/builder/export", "builder", params={"format": "yaml"})
    exported = api.call("GET", "/api/builder/export", "builder")[1]
    d.example("POST", "/api/builder/import", "builder", body={"schema_version": 2, "nodes": exported["nodes"][:1],
                                                              "links": []},
              params={"dry_run": "true"}, limit=3, title="import dry_run: документ из одного узла")
    d.table(["логин", "GET /api/builder/validate", "POST /api/builder/nodes"],
            [[role, status_of(api, "GET", "/api/builder/validate", role),
              status_of(api, "POST", "/api/builder/nodes", role, body={"name": "проверка прав"})
              if role != "builder" else "201"] for role in ("director", "head_prod", "qc_otk", "builder")])

    # --- демо-время ---
    d = section("demo")
    d.example("GET", "/api/demo/clock", "qc_otk")
    d.example("POST", "/api/demo/advance", "director", params={"days": 90}, title="Слишком большая перемотка")
    d.table(["логин", "POST /api/demo/advance?days=1"],
            [[role, status_of(api, "POST", "/api/demo/advance", role, params={"days": 1})]
             for role in ("qc_otk", "head_client")])
    d.example("POST", "/api/demo/reset", "builder", title="Сброс (после него стенд как после run.py --reset)")

    return assemble(sections, clock, reset, ids, order_id)


def assemble(s: dict[str, Doc], clock: dict, reset: dict, ids: dict[str, int], order_id: str) -> str:
    def body(key: str) -> str:
        return "".join(s[key].lines)

    id_rows = "\n".join(f"| {name} | {ids[name]} |" for name in (
        "Фотопринт", "Работа с клиентами", "Поддержка", "Производство", "Сборка", "ОТК", "Смены",
        "Финансы", "Контролёр ОТК Иванова"))
    return f"""# FRONTEND_CONTRACT — контракт бэкенда для фронтенда (по экранам)

Сгенерировано `python scripts/gen_frontend_contract.py` настоящими HTTP-запросами к серверу
`python run.py` после `POST /api/demo/reset`. Время стенда после сброса — `{clock['now']}`.
Каждый ответ ниже — реальный; длинные списки сокращены (`"… ещё N"`), выборка полей помечена в тексте.
Полная схема — `docs/openapi.json` и `/docs`; все режимы — `docs/api.md`.

Стенд после сброса: узлов {reset['nodes']}, связей {reset['links']}, заказов в плане {reset['orders']},
событий {reset['events']}, карточка {', '.join(reset['deviations'])}. id узлов после сброса всегда одинаковы:

| узел | id |
|---|---|
{id_rows}

## Общее для всех экранов

- **Заголовок `X-User: <login>` обязателен** на всех `/api/*`, кроме `GET /api/auth/users` (и `GET /health`).
  Без него — `401 unauthorized`, неизвестный логин — `401 unknown_user`. Паролей нет.
- Тело запросов — JSON в UTF-8, `Content-Type: application/json; charset=utf-8`.
  Исключение: `POST /api/builder/import` принимает и YAML (`application/x-yaml`).
- Время — ISO-8601 с поясом. Ряды KPI отдают время в UTC (`…Z`), события и карточки — с `+03:00`:
  сравнивайте как моменты, а не как строки.
- Единицы: `units=natural` (по умолчанию) или `relative`. `money` всегда даёт `400 money_disabled`.
- Права роли — `GET /api/me` → `permissions`: прячьте кнопки, которых нет в этом списке.

### Формат ошибок

Один формат для всех кодов, включая 422 pydantic: `{{"error": {{"code", "message", "details"}}}}`.
{body('errors')}
## 1. Выбор пользователя / вход

Эндпоинты: `GET /api/auth/users` (без `X-User`) → список для выбора; `GET /api/me` → профиль, права, зона.
Выбранный логин фронтенд хранит сам и подставляет в `X-User` каждого запроса.
{body('login')}
## 2. Главный экран (8 плиток)

Эндпоинт: `GET /api/overview?units=natural|relative`. Всегда 8 плиток в порядке `order`
(срок → качество → себестоимость). Плитка: худший статус KPI зоны, `main_kpi` (значение, `delta_week`,
`trend`, `trend_quality`), `forecast_risk` (ближайшее пересечение порога на 14 суток), открытые отклонения;
`portfolio` — сводка решений.

**Пустое состояние:** если в зоне нет KPI плитки — `status: "unknown"`, `kpis: 0`, `main_kpi: null`,
`forecast_risk.at_risk: false`. Плитку всё равно рисовать (8 штук всегда).

**Различия по ролям** (настоящие ответы):
{body('overview')}
## 3. Карта организации / граф

Эндпоинты: `GET /api/graph?units=…` (узлы зоны, связи, серые граничные узлы),
`GET /api/analysis/contributions?node=&kpi=` (вклады связей KPI, строка `summary`).

- Узел зоны: полный, `clickable: true`, KPI со значениями, `status`, `deep_status`.
- `boundary: "upstream"` — чужой узел, чей KPI ссылается в зону: `clickable: false`, `status: null`,
  в `kpis` только этот KPI с названием и статусом, без значений.
- `boundary: "downstream"` — чужой узел, на который ссылается KPI зоны: `clickable: false`, тип, владелец,
  общий статус, `kpis: []`.
- Связь к чужому узлу: без `to_kpi`, `contribution`, `share`. В `contributions` у таких связей `visible: false`,
  а число скрытых — в `hidden_links`.
{body('graph')}
## 4. Карточка узла: KPI, ряды, аннотации, прогноз

Эндпоинты: `GET /api/nodes/{{id}}` (узел и связи; открытие пишется в журнал),
`GET /api/nodes/{{id}}/kpis?units=`, `GET /api/kpi/{{node}}/{{kpi}}?from=&to=&agg=raw|day&units=`
(точки и флажки; аннотации — флажки `kind: "annotation"`, `ref` = id события),
`GET /api/kpi/{{node}}/{{kpi}}/forecast?horizon=7|14|21`, `GET /api/events?type=annotation&node=`.

**Пустое состояние:** период без точек — `points: []`; KPI без данных — `value: null`, `status: "unknown"`,
`stale: true`; прогноз при меньше 7 сутках — `enough_data: false`, `points: []`.
Узел вне зоны — `403 out_of_zone` (кликабельность смотрите в графе заранее).
{body('node')}
## 5. Карточка отклонения: сигнал → контекст → причина → действие → перепроверка

Эндпоинты: `GET /api/deviations?status=&node=&owner=` (портфель + `summary`), `GET /api/deviations/{{id}}`,
`GET …/suggest` (1–3 шаблона действия), `GET …/orders` (затронутые заказы), `GET /api/analysis/trace`,
`PATCH /api/deviations/{{id}}` (статус, действие, гипотеза; admin), `POST /api/admin/deviations/{{id}}/recheck`
(admin), `POST /api/qc/deviations/{{id}}/done` (исполнитель).

Поля карточки по шагам цепочки: `signal` (сигнал) → `context` (плитка, этап, профиль сезона, `dims`, окно)
→ `cause` (снимок trace, `root`, `confidence`) → `action` (текст, `owner_login`/`owner_node`, `due_at`)
→ `rechecks[]` (каждая перепроверка добавляется) → `status`. `current` — состояние KPI сейчас.

Переходы: `open → assigned | escalated | closed`; `assigned → assigned | in_progress | done | escalated | closed`;
`in_progress → assigned | done | escalated | closed`; `done → in_progress | closed`; `failed → assigned | escalated | closed`;
`escalated → assigned | closed`; `verified → closed`. `verified`/`failed` ставит только перепроверка.
Неверный переход — `409 invalid_transition`. Перепроверка раньше 3 суток — `result: "pending"`, статус не меняется.

**Видимость:** карточку видит тот, у кого в зоне узел сигнала, узел первопричины или кто исполнитель.
Шаги trace и цифры вне зоны — `null`.
{body('deviation')}
## 6. Поток заказов (8 этапов × 4 поля)

Эндпоинты: `GET /api/flow/summary`, `GET /api/orders?stage=&status=&product_line=&brand=&segment=&customer_id=&issue=&from=&to=&limit=&offset=`,
`GET /api/orders/{{id}}`, источники — `GET /api/sources`, `GET /api/events`.

У каждого этапа всегда есть 4 поля: `event_id`, `status`, `owner`, `result_check`. Статусы этапа:
`pending` (не начат: `event_id: null`, времени нет), `in_progress` (итог проверки `null`), `done`, `late`, `defect`.
Заказ виден, если хотя бы один этап принадлежит узлу зоны; чужой этап — `visible: false`, без события,
`result_check: null`, времени и проблемы. В `/flow/summary` чужой этап — с `null` вместо цифр.
{body('flow')}
## 7. Подчинённые

Эндпоинты: `GET /api/nodes/{{id}}/people` (admin; узлы `person` в зоне ниже узла, их действия и личные KPI);
для qc — `GET /api/me/queue` и `GET /api/me/stats`.
{body('people')}
## 8. Словарь

Эндпоинт: `GET /api/glossary` — одинаков для всех ролей. Правка — `POST/PATCH /api/builder/glossary` (builder).
{body('glossary')}
## 9. Журнал

Эндпоинт: `GET /api/audit?user=&action=&object_type=&object_id=&node=&limit=&offset=` — новые сверху.
Директор видит всё, admin — записи о своей зоне и свои, qc и builder — только свои. У чужих записей,
задевающих узлы вне зоны, `details: {{}}` и `details_hidden: true`.
Примеры сняты после шагов демо-сценария (раздел «Демо-сценарий»).
{body('audit')}
## 10. Конструктор (builder)

Эндпоинты: `POST/PATCH/DELETE /api/builder/nodes…`, `POST/PATCH/DELETE /api/builder/nodes/{{id}}/kpis…`,
`POST/PATCH/DELETE /api/builder/links…`, `PUT /api/builder/kpis/{{node}}/{{kpi}}/weights?normalize=`,
`POST/PATCH /api/builder/glossary`, `GET /api/builder/validate`, `GET /api/builder/export?format=json|yaml`,
`POST /api/builder/import?dry_run=true`. Ответ на правку связи — `{{link, kpi_links}}`: перерисовывайте веса
всех связей KPI из `kpi_links` (они нормируются автоматически). Другим ролям всё это — `403 forbidden`.
{body('builder')}
## 11. Управление демо-временем

Эндпоинты: `GET /api/demo/clock` (все роли), `POST /api/demo/advance?days=1..60` и `POST /api/demo/reset`
(admin и builder). После перемотки и сброса перечитайте всё: статусы, карточки, заказы и журнал меняются.
{body('demo')}
## Подводные камни для фронтенда

1. **`X-User` обязателен везде**, кроме `GET /api/auth/users` и `/health`. Ставьте его в общий HTTP-клиент;
   401 означает «пользователь не выбран».
2. **Серые граничные узлы** (`boundary: upstream|downstream`, `clickable: false`) рисуются, но не открываются:
   `GET /api/nodes/{{id}}` по ним — 403. У upstream `status: null` (общего статуса нет), виден один KPI без
   значения; у downstream есть общий статус, KPI нет.
3. **`access: "none"`** у связи — причинная связь без доступа: по ней не строится зона. Межфункциональные
   связи (Поддержка → Сборка, ОТК, Склад; Сборка → Смены; Поддержка → Pick-Pack) именно такие. Узел по такой
   связи может оказаться серым даже у руководителя, который видит источник связи.
4. **План заказов — 15 суток вперёд.** Заказы созданы при сиде на 45 суток назад и 15 вперёд и открываются по
   часам стенда. Перемотка дальше 15 суток не даёт новых заказов, а незавершённые этапы будут числиться
   просроченными. Заказы не зависят от того, назначено ли действие по карточке.
5. **D73: скрытые вклады влияют на путь trace.** Trace выбирает связь по всем вкладам, включая узлы вне зоны;
   цифры скрыты, но сам факт, что путь ушёл в серый узел (`stopped_reason: "out_of_zone"`), виден.
   Не подписывайте такой шаг как «причина найдена у вас».
6. **Деньги выключены.** Режима `money` нет: `units=money` → 400. Финансы — только доли и индексы.
   Не делайте переключатель на деньги.
7. **Кириллица.** Тела запросов — UTF-8. В Git Bash `curl -d '…кириллица…'` портит текст — тело из файла
   (`-d @body.json`). Имена узлов в query (`/api/nodes?name=…`) кодируйте через `encodeURIComponent`.
8. **Время рядов в UTC (`Z`)**, событий и карточек — в `+03:00`. Сутки стенда — местные (+03:00).
9. **Часы стоят.** «Сейчас» — `GET /api/demo/clock`, а не время браузера. Точки и события позже часов не отдаются.
10. **Одинаковые id после сброса**, но после правок конструктора и импорта id новых узлов растут и не переиспользуются.
11. **Перепроверка в первые 3 суток** после назначения даёт `pending` без смены статуса — покажите это как
    «рано проверять», а не как ошибку.

## Демо-сценарий по шагам (конкретные id и настоящие ответы)

Узлы: Поддержка = {ids['Поддержка']}, Сборка = {ids['Сборка']}, Производство = {ids['Производство']};
карточка `DEV-0001`; заказ со браком в сегменте сценария — `{order_id}`.
{body('scenario')}
## Чего фронтенд НЕ может получить от бэкенда сейчас

- **Денежные суммы** в любом виде (выключено по ТЗ).
- **Настоящий вход**: паролей, токенов, сессий и SSO нет — только `X-User`.
- **Живые данные источников**: CRM, Mary, ERP, 1С и HR — mock, события созданы сидом; push-уведомлений,
  WebSocket и SSE нет — только опрос (polling).
- **Новые заказы дальше 15 суток** после сброса и заказы, реагирующие на назначенное действие.
- **История правок карточки «до/после»**: в `history` только имена изменённых полей; прежнее действие
  после нового назначения не хранится.
- **Причину остановки trace без учёта скрытых вкладов** (D73) и признак «у цели нет данных» у связи.
- **Отмену импорта**: импорт конфигурации не транзакционный, отката нет.
- **Агрегатов по заказам за произвольный период** (кроме фильтров списка) и выгрузки в Excel/CSV.
- **Переводов и локализации**: тексты ответов и ошибок — только на русском.
- **Статического фронтенда**: бэкенд только монтирует папку `web/`, если она появится.
"""


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Собрать docs/FRONTEND_CONTRACT.md с запущенного сервера")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)
    text = build(Api(args.base))
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT}: {len(text.splitlines())} строк")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
