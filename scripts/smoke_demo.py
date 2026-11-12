"""Главный приёмочный тест: весь демо-сценарий через HTTP с проверками.

    python scripts/smoke_demo.py            # сервер уже запущен: python run.py
    python scripts/smoke_demo.py --start    # поднять свой сервер во временной папке
    python scripts/smoke_demo.py --base http://127.0.0.1:8000

Сценарий: вход → обзор → источники и поток → trace → карточка → затронутые
заказы → подсказка → назначение действия → зоны → перемотка → перепроверка →
журнал → конструктор («Закупки») → деньги выключены. Перед сценарием стенд
сбрасывается (``POST /api/demo/reset``), поэтому цифры одинаковы на любой
машине. Печатает OK/FAIL по шагам; код выхода 1, если хоть один шаг упал.

Только стандартная библиотека: скрипт работает в окружении из requirements.txt.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, user: str | None = "director", body: Any = None,
             params: dict[str, Any] | None = None) -> tuple[int, Any]:
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None
        headers = {"Accept": "application/json"}
        if user:
            headers["X-User"] = user
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            raw, status = error.read(), error.code
        text = raw.decode("utf-8") if raw else ""
        try:
            return status, json.loads(text) if text else None
        except json.JSONDecodeError:
            return status, text

    def get(self, path: str, user: str | None = "director", **params: Any) -> Any:
        status, body = self.call("GET", path, user, params=params or None)
        if status != 200:
            raise AssertionError(f"GET {path} → {status}: {body}")
        return body


class Run:
    def __init__(self) -> None:
        self.failed = 0
        self.passed = 0

    def step(self, title: str, action: Callable[[], str | None]) -> None:
        try:
            note = action()
        except Exception as exc:  # шаг упал — сценарий идёт дальше, итог покажет FAIL
            self.failed += 1
            print(f"FAIL  {title}: {exc}", flush=True)
            return
        self.passed += 1
        print(f"OK    {title}" + (f" — {note}" if note else ""), flush=True)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def scenario(api: Client) -> int:
    run = Run()
    state: dict[str, Any] = {}

    def node_id(name: str) -> int:
        nodes = api.get("/api/nodes", "director", name=name)
        return next(node["id"] for node in nodes if node["name"] == name)

    def health() -> str:
        check(api.get("/health", None) == {"status": "ok"}, "сервер не отвечает")
        status, _ = api.call("GET", "/api/overview", None)
        check(status == 401, f"без X-User ожидался 401, получено {status}")
        return "без X-User — 401"

    def login() -> str:
        users = [u["login"] for u in api.get("/api/auth/users", None)]
        check(users == ["director", "head_client", "head_prod", "qc_otk", "builder"], f"логины: {users}")
        status, reset = api.call("POST", "/api/demo/reset", "director")
        check(status == 200 and reset["deviations"] == ["DEV-0001"], f"reset: {status} {reset}")
        me = api.get("/api/me", "director")
        check(me["sees_everything"] is True, "директор должен видеть всё")
        return f"5 ролей, сброс: узлов {reset['nodes']}, заказов {reset['orders']}, событий {reset['events']}"

    def overview() -> str:
        body = api.get("/api/overview", "director")
        tiles = {tile["key"]: tile for tile in body["tiles"]}
        check(len(tiles) == 8, f"плиток {len(tiles)}")
        check(all(tile["main_kpi"] for tile in tiles.values()), "у плитки нет главного KPI")
        check(tiles["quality"]["status"] == "red" and tiles["quality"]["open_deviations"] == 1, "плитка «Качество»")
        return f"8 плиток, «Качество» красная, открыто отклонений: {body['portfolio']['open']}"

    def sources() -> str:
        items = api.get("/api/sources", "director")
        check([s["key"] for s in items] == ["crm", "support", "erp", "finance", "hr"], "источники")
        check(all(s["events"] > 0 for s in items), "у источника нет событий")
        flow = api.get("/api/flow/summary", "director")
        check(len(flow["stages"]) == 8, "этапов не 8")
        order = api.get(f"/api/orders/{api.get('/api/orders', 'director', limit=1)['items'][0]['order_id']}")
        for stage in order["stages"]:
            check(all(key in stage for key in ("event_id", "status", "owner", "result_check")), "4 поля этапа")
        return f"5 источников, {flow['orders_total']} заказов × 8 этапов × 4 поля"

    def trace() -> str:
        state["support"], state["assembly"] = node_id("Поддержка"), node_id("Сборка")
        body = api.get("/api/analysis/trace", "director", node=state["support"], kpi="defect_tickets_share")
        root = body["root_cause"]
        check((root["node_name"], root["kpi"]) == ("Сборка", "defect_rate"), f"первопричина {root}")
        last = body["steps"][-1]
        alternatives = [a["to_node_name"] for a in last["alternatives"]]
        check("Смены" in alternatives, f"альтернативы последнего шага: {alternatives}")
        summary = api.get("/api/analysis/contributions", "director", node=state["support"],
                          kpi="defect_tickets_share")["summary"]
        api.get(f"/api/nodes/{state['assembly']}", "director")  # открытие деталей узла пишется в журнал
        return f"Поддержка → Сборка / defect_rate; {summary}"

    def card() -> str:
        body = api.get("/api/deviations/DEV-0001", "director")
        check(body["status"] == "open" and body["cause"]["root"]["node_name"] == "Сборка", "карточка")
        check(body["context"]["dims"].get("product_line") == "Выпускные альбомы", f"dims {body['context']['dims']}")
        orders = api.get("/api/deviations/DEV-0001/orders", "director")
        check(orders["count"] > 0, "нет затронутых заказов")
        return f"сигнал {body['signal']['value']} при crit {body['signal']['threshold']}, затронуто заказов: {orders['count']}"

    def suggest() -> str:
        body = api.get("/api/deviations/DEV-0001/suggest", "director")
        check(1 <= len(body["suggestions"]) <= 3, "подсказок не 1–3")
        state["suggestion"] = body["suggestions"][0]
        return state["suggestion"]["title"]

    def assign() -> str:
        suggestion = state["suggestion"]
        status, body = api.call("PATCH", "/api/deviations/DEV-0001", "director", {
            "status": "assigned",
            "action": {"text": suggestion["action"], "owner_login": "head_prod",
                       "due_at": suggestion["due_at"], "playbook_ref": suggestion["id"]},
        })
        check(status == 200 and body["status"] == "assigned", f"{status} {body}")
        return f"исполнитель head_prod, срок {body['action']['due_at']}"

    def zones() -> str:
        status, _ = api.call("GET", f"/api/nodes/{state['assembly']}", "head_client")
        check(status == 403, f"head_client открыл «Сборку»: {status}")
        graph = api.get("/api/graph", "head_prod")
        support = next(n for n in graph["nodes"] if n["name"] == "Поддержка")
        check(support.get("boundary") == "upstream" and len(support["kpis"]) == 1, "Поддержка у head_prod")
        status, _ = api.call("POST", "/api/builder/nodes", "qc_otk", {"name": "x"})
        check(status == 403, "qc не должен менять структуру")
        return "чужая «Сборка» — 403, «Поддержка» у производства серая с одним KPI, qc не меняет структуру"

    def advance() -> str:
        status, body = api.call("POST", "/api/demo/advance", "director", params={"days": 7})
        check(status == 200, f"{status} {body}")
        branch = body["branches"].get("Поддержка/defect_tickets_share")
        check(branch == "with_action", f"ветка {branch}")
        return f"+7 суток, ветка with_action, сейчас {body['now']}"

    def recheck() -> str:
        status, body = api.call("POST", "/api/admin/deviations/DEV-0001/recheck", "director")
        check(status == 200, f"{status} {body}")
        record = body["recheck"]
        check(record["passed"] is True and body["deviation"]["status"] == "verified", f"перепроверка {record}")
        status, again = api.call("POST", "/api/admin/deviations/DEV-0001/recheck", "director")
        check(status == 200 and len(again["deviation"]["rechecks"]) == 2, "повторная перепроверка не добавилась")
        return (f"baseline {record['baseline']['value']} → after {record['after']['value']}, "
                f"improvement {record['improvement']}, verified; повтор добавлен в историю")

    def audit() -> str:
        items = api.get("/api/audit", "director", limit=200)["items"]
        actions = {item["action"] for item in items}
        for needed in ("deviation.update", "demo.advance", "deviation.recheck", "deviation.open", "node.open"):
            check(needed in actions, f"нет записи {needed}")
        own = api.get("/api/audit", "qc_otk")["items"]
        check(all(item["user"] == "qc_otk" for item in own), "qc видит чужие записи")
        return f"записей: {len(items)}+, qc видит только свои"

    def builder() -> str:
        metric = {
            "key": "incoming_defect_share", "title": "Входной брак материалов", "source": "erp",
            "owner": "Зам. по производству", "unit": "%", "direction": "lower_better", "priority": "quality",
            "tile": "quality", "stage": 5, "display": {"relative": "pct_of_target", "natural": "%"},
            "thresholds": {"default": {"target": 1.0, "warn": 2.0, "crit": 3.0}},
        }
        status, _ = api.call("POST", "/api/builder/glossary", "builder", metric)
        check(status == 201, f"метрика: {status}")
        status, node = api.call("POST", "/api/builder/nodes", "builder",
                                {"name": "Закупки", "type": "department", "owner": "Зам. по производству"})
        check(status == 201, f"узел: {status}")
        status, _ = api.call("POST", f"/api/builder/nodes/{node['id']}/kpis", "builder",
                             {"name": "incoming_defect_share", "metric": "incoming_defect_share", "pinned": True})
        check(status == 201, f"KPI: {status}")
        status, link = api.call("POST", "/api/builder/links", "builder", {
            "from_node": state["assembly"], "from_kpi": "defect_rate", "to_node": node["id"],
            "to_kpi": "incoming_defect_share", "weight": 0.2, "note": "Брак материалов поставщика"})
        check(status == 201, f"связь: {status} {link}")
        weights = sorted(round(item["weight"], 6) for item in link["kpi_links"])
        check(weights == [0.2, 0.2, 0.2, 0.2, 0.2], f"веса после добавления: {weights}")
        api.call("POST", f"/api/qc/kpi/{node['id']}/incoming_defect_share/points", "director",
                 {"ts": api.get("/api/demo/clock", "director")["now"], "value": 4.0})
        summary = api.get("/api/analysis/contributions", "director", node=state["assembly"], kpi="defect_rate")["summary"]
        check("Закупки" in summary, f"вклад: {summary}")
        report = api.get("/api/builder/validate", "builder")
        check(report["ok"] is True, f"validate: {report}")
        exported = api.get("/api/builder/export", "builder")
        status, plan = api.call("POST", "/api/builder/import", "builder", exported, params={"dry_run": "true"})
        check(status == 200 and plan["changes"]["changed"] is False, "export → import не идентичны")
        return f"«Закупки» с весом 0,2, остальные ×0,8; {summary}; validate ok, export → import без изменений"

    def money() -> str:
        status, body = api.call("GET", "/api/overview", "director", params={"units": "money"})
        check(status == 400 and body["error"]["code"] == "money_disabled", f"{status} {body}")
        return "режим money выключен (400 money_disabled)"

    for title, action in [
        ("Сервер и строгий X-User", health),
        ("Вход: пользователи, сброс стенда, профиль директора", login),
        ("Обзор: 8 плиток", overview),
        ("Источники и поток заказов", sources),
        ("Расследование: trace к первопричине", trace),
        ("Карточка DEV-0001 и затронутые заказы", card),
        ("Подсказка действия (playbook)", suggest),
        ("Назначение действия: владелец и срок", assign),
        ("Зоны доступа и матрица прав", zones),
        ("Демо-время: перемотка на 7 суток", advance),
        ("Повторная проверка результата", recheck),
        ("Журнал", audit),
        ("Конструктор: сценарий «Закупки», validate, export → import", builder),
        ("Деньги выключены по ТЗ", money),
    ]:
        run.step(title, action)
    print(f"\nИтог: {run.passed} OK, {run.failed} FAIL", flush=True)
    return 1 if run.failed else 0


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port: int, data: str) -> subprocess.Popen:
    env = dict(os.environ, PYTHONUTF8="1")
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "run.py"), "--port", str(port), "--data", data],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    api = Client(f"http://127.0.0.1:{port}")
    for _ in range(240):
        if process.poll() is not None:
            raise SystemExit("сервер не запустился (см. python run.py)")
        try:
            if api.get("/health", None) == {"status": "ok"}:
                return process
        except Exception:
            time.sleep(0.5)
    process.terminate()
    raise SystemExit("сервер не ответил за 2 минуты")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Демо-сценарий «Фотопринт» через HTTP")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="адрес запущенного сервера")
    parser.add_argument("--start", action="store_true", help="поднять свой сервер во временной папке")
    args = parser.parse_args(argv)
    if not args.start:
        return scenario(Client(args.base))
    with tempfile.TemporaryDirectory(prefix="photoprint-smoke-") as tmp:
        port = free_port()
        print(f"Запускаю сервер на порту {port}, данные — {tmp}", flush=True)
        process = start_server(port, str(Path(tmp) / "data"))
        try:
            return scenario(Client(f"http://127.0.0.1:{port}"))
        finally:
            process.terminate()
            process.wait(timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
