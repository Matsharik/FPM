# API трекера «Фотопринт» — контракт для фронтенда

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
curl -s -X POST http://127.0.0.1:8000/api/builder/nodes \
  -H "X-User: builder" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```

В PowerShell:

```powershell
$body = '{"name": "Закупки", "type": "department"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/builder/nodes `
  -Headers @{ "X-User" = "builder" } -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

## Вход
Режим для всех: выбор пользователя и его профиль (слайд 5 ТЗ).

### GET /api/auth/users
```bash
curl -s "http://127.0.0.1:8000/api/auth/users"
```
Ответ `200`:

```json
[
  {
    "login": "director",
    "name": "Генеральный директор",
    "role": "admin",
    "scope_roots": [
      {
        "id": 1,
        "name": "Фотопринт"
      }
    ],
    "node": null
  },
  {
    "login": "head_client",
    "name": "Зам. по работе с клиентами",
    "role": "admin",
    "scope_roots": [
      {
        "id": 2,
        "name": "Работа с клиентами"
      }
    ],
    "node": null
  },
  {
    "login": "head_prod",
    "name": "Зам. по производству",
    "role": "admin",
    "scope_roots": [
      {
        "id": 9,
        "name": "Производство"
      }
    ],
    "node": null
  },
  {
    "login": "qc_otk",
    "name": "Контролёр ОТК",
    "role": "qc",
    "scope_roots": [
      {
        "id": 12,
        "name": "ОТК"
      }
    ],
    "node": {
      "id": 17,
      "name": "Контролёр ОТК Иванова"
    }
  },
  {
    "login": "builder",
    "name": "Методолог",
    "role": "builder",
    "scope_roots": [
      {
        "id": 1,
        "name": "Фотопринт"
      }
    ],
    "node": null
  }
]
```

### GET /api/me
```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8000/api/me"
```
Ответ `200`:

```json
{
  "login": "head_prod",
  "name": "Зам. по производству",
  "role": "admin",
  "scope_roots": [
    {
      "id": 9,
      "name": "Производство"
    }
  ],
  "node": null,
  "permissions": [
    "demo.control",
    "deviations.done",
    "… ещё 5"
  ],
  "sees_everything": false,
  "zone": [
    9,
    10,
    "… ещё 9"
  ]
}
```

## Обзор (главный экран)
8 плиток в зоне пользователя и сводка портфеля решений (слайд 3).

### GET /api/overview
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/overview"
```
Ответ `200`:

```json
{
  "now": "2026-11-23T09:00:00+03:00",
  "user": "director",
  "units": "natural",
  "zone_nodes": 24,
  "tiles": [
    {
      "key": "orders",
      "title": "Заказы · ритм",
      "stage": 3,
      "priority": "time",
      "order": 1,
      "status": "green",
      "kpis": 5,
      "kpi_statuses": {
        "red": 0,
        "yellow": 0,
        "green": 5,
        "unknown": 0
      },
      "main_kpi": {
        "node_id": 1,
        "node_name": "Фотопринт",
        "kpi": "orders_rhythm",
        "title": "Ритм заказов (к плану)",
        "value": 99.03,
        "value_date": "2026-11-22",
        "unit": "индекс",
        "status": "green",
        "severity": 0.0485,
        "delta_week": -2.98,
        "trend": "flat",
        "trend_quality": "stable"
      },
      "forecast_risk": {
        "at_risk": false,
        "horizon": 14,
        "in_days": null,
        "date": null,
        "level": null,
        "node_id": null,
        "node_name": null,
        "kpi": null,
        "title": null
      },
      "open_deviations": 0,
      "deviation_ids": []
    },
    {
      "key": "moderation",
      "title": "Модерация · очередь",
      "stage": 4,
      "priority": "time",
      "order": 2,
      "status": "green",
      "kpis": 2,
      "kpi_statuses": {
        "red": 0,
        "yellow": 0,
        "green": 2,
        "unknown": 0
      },
      "main_kpi": {
        "node_id": 7,
        "node_name": "Модерация",
        "kpi": "moderation_queue_time",
        "title": "Время в очереди модерации",
        "value": 1.64,
        "value_date": "2026-11-22",
        "unit": "ч",
        "status": "green",
        "severity": 0.0,
        "delta_week": -0.03,
        "trend": "flat",
        "trend_quality": "stable"
      },
      "forecast_risk": {
        "at_risk": false,
        "horizon": 14,
        "in_days": null,
        "date": null,
        "level": null,
        "node_id": null,
        "node_name": null,
        "kpi": null,
        "title": null
      },
      "open_deviations": 0,
      "deviation_ids": []
    },
    "… ещё 6"
  ],
  "portfolio": {
    "total": 1,
    "open": 1,
    "overdue": 0,
    "verified": 0,
    "failed": 0,
    "rechecks": 0,
    "recheck_success_rate": null,
    "by_status": {
      "open": 1,
      "assigned": 0,
      "in_progress": 0,
      "done": 0,
      "verified": 0,
      "failed": 0,
      "escalated": 0,
      "closed": 0
    }
  }
}
```

## Граф KPI
Узлы зоны, связи с весами и долями, серые граничные узлы.

### GET /api/graph
У `head_prod` «Поддержка» — граничный узел сверху (`boundary: upstream`) с одним KPI.
```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8000/api/graph"
```
Ответ `200`:

```json
{
  "units": "natural",
  "roots": [
    9
  ],
  "zone_size": 11,
  "nodes": [
    {
      "id": 1,
      "name": "Фотопринт",
      "type": "system",
      "description": "",
      "owner": "Генеральный директор",
      "attrs": {},
      "tile": null,
      "stage": null,
      "tags": {},
      "synthetic": true,
      "flags": [],
      "status": null,
      "deep_status": null,
      "scope_root": false,
      "boundary": "upstream",
      "clickable": false,
      "kpis": [
        {
          "name": "on_time_72h_share",
          "metric": null,
          "title": "Доля заказов в срок 72 ч",
          "compute": null,
          "pinned": null,
          "unit": null,
          "value": null,
          "value_date": null,
          "status": "green",
          "severity": null,
          "stale": null
        }
      ]
    },
    {
      "id": 5,
      "name": "Поддержка",
      "type": "department",
      "description": "",
      "owner": "Зам. по работе с клиентами",
      "attrs": {},
      "tile": null,
      "stage": null,
      "tags": {},
      "synthetic": true,
      "flags": [],
      "status": null,
      "deep_status": null,
      "scope_root": false,
      "boundary": "upstream",
      "clickable": false,
      "kpis": [
        {
          "name": "defect_tickets_share",
          "metric": null,
          "title": "Доля обращений по браку",
          "compute": null,
          "pinned": null,
          "unit": null,
          "value": null,
          "value_date": null,
          "status": "red",
          "severity": null,
          "stale": null
        }
      ]
    },
    "… ещё 12"
  ],
  "links": [
    {
      "id": "L-0002",
      "from_node": 1,
      "from_kpi": "on_time_72h_share",
      "to_node": 9,
      "to_kpi": null,
      "weight": 0.45,
      "access": "inherit",
      "note": "",
      "flags": [],
      "boundary": "upstream",
      "contribution": null,
      "share": null
    },
    {
      "id": "L-0012",
      "from_node": 9,
      "from_kpi": "on_time_24h_share",
      "to_node": 10,
      "to_kpi": null,
      "weight": 0.3,
      "access": "inherit",
      "note": "",
      "flags": [],
      "boundary": null,
      "contribution": 0.0045,
      "share": 0.013867
    },
    {
      "id": "L-0013",
      "from_node": 9,
      "from_kpi": "on_time_24h_share",
      "to_node": 11,
      "to_kpi": null,
      "weight": 0.3,
      "access": "inherit",
      "note": "",
      "flags": [],
      "boundary": null,
      "contribution": 0.3,
      "share": 0.924499
    },
    "… ещё 25"
  ]
}
```

### GET /api/nodes/11
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/nodes/11"
```
Ответ `200`:

```json
{
  "id": 11,
  "name": "Сборка",
  "type": "department",
  "description": "",
  "owner": "Зам. по производству",
  "attrs": {
    "assumed": true
  },
  "parameters": {},
  "tile": "production",
  "stage": 5,
  "tags": {
    "function": "production"
  },
  "kpis": [
    {
      "name": "defect_rate",
      "metric": "defect_rate",
      "compute": "measured",
      "pinned": true,
      "overrides": {},
      "unit": "%"
    },
    {
      "name": "site_load",
      "metric": "site_load",
      "compute": "measured",
      "pinned": false,
      "overrides": {},
      "unit": "%"
    }
  ],
  "flags": [],
  "synthetic": true,
  "created_by": "seed",
  "status": "red",
  "links_out": [
    {
      "id": "L-0022",
      "from_node": 11,
      "from_kpi": "defect_rate",
      "to_node": 14,
      "to_kpi": "personal_efficiency",
      "weight": 0.25,
      "access": "inherit",
      "note": "",
      "flags": [],
      "created_by": "seed",
      "created_at": "2026-11-23T09:00:00+03:00"
    },
    {
      "id": "L-0023",
      "from_node": 11,
      "from_kpi": "defect_rate",
      "to_node": 15,
      "to_kpi": "personal_efficiency",
      "weight": 0.25,
      "access": "inherit",
      "note": "",
      "flags": [],
      "created_by": "seed",
      "created_at": "2026-11-23T09:00:00+03:00"
    },
    "… ещё 5"
  ],
  "links_in": [
    {
      "id": "L-0013",
      "from_node": 9,
      "from_kpi": "on_time_24h_share",
      "to_node": 11,
      "to_kpi": null,
      "weight": 0.3,
      "access": "inherit",
      "note": "",
      "flags": [],
      "created_by": "seed",
      "created_at": "2026-11-23T09:00:00+03:00"
    },
    {
      "id": "L-0018",
      "from_node": 5,
      "from_kpi": "defect_tickets_share",
      "to_node": 11,
      "to_kpi": "defect_rate",
      "weight": 0.6,
      "access": "none",
      "note": "Обращения по браку зависят от брака сборки",
      "flags": [],
      "created_by": "seed",
      "created_at": "2026-11-23T09:00:00+03:00"
    },
    "… ещё 2"
  ]
}
```

### GET /api/analysis/contributions?node=5&kpi=defect_tickets_share
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/analysis/contributions?node=5&kpi=defect_tickets_share"
```
Ответ `200`:

```json
{
  "node_id": 5,
  "node_name": "Поддержка",
  "kpi": "defect_tickets_share",
  "title": "Доля обращений по браку",
  "status": "red",
  "severity": 1.0,
  "total_contribution": 0.65,
  "hidden_links": 0,
  "summary": "Доля обращений по браку: Сборка 92%, ОТК 8%",
  "links": [
    {
      "link_id": "L-0018",
      "to_node": 11,
      "to_node_name": "Сборка",
      "owner": "Зам. по производству",
      "to_kpi": "defect_rate",
      "target_kpi": "defect_rate",
      "weight": 0.6,
      "access": "none",
      "status": "red",
      "visible": true,
      "severity": 1.0,
      "contribution": 0.6,
      "share": 0.923077
    },
    {
      "link_id": "L-0019",
      "to_node": 12,
      "to_node_name": "ОТК",
      "owner": "Зам. по производству",
      "to_kpi": "defect_escape_rate",
      "target_kpi": "defect_escape_rate",
      "weight": 0.25,
      "access": "none",
      "status": "green",
      "visible": true,
      "severity": 0.2,
      "contribution": 0.05,
      "share": 0.076923
    },
    {
      "link_id": "L-0020",
      "to_node": 13,
      "to_node_name": "Склад и отгрузка",
      "owner": "Зам. по производству",
      "to_kpi": null,
      "target_kpi": "delivery_on_time_share",
      "weight": 0.15,
      "access": "none",
      "status": "green",
      "visible": true,
      "severity": 0.0,
      "contribution": 0.0,
      "share": 0.0
    }
  ]
}
```

## Детали
KPI узла, ряды с флажками и аннотациями, прогноз, режим единиц.

### GET /api/nodes/11/kpis?units=relative
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/nodes/11/kpis?units=relative"
```
Ответ `200`:

```json
[
  {
    "node_id": 11,
    "name": "defect_rate",
    "metric": "defect_rate",
    "title": "Доля брака",
    "compute": "measured",
    "pinned": true,
    "units": "relative",
    "unit": "% к цели",
    "value": 320.0,
    "value_date": "2026-11-22",
    "status": "red",
    "severity": 1.0,
    "level": "crit",
    "status_source": "thresholds",
    "profile": "default",
    "thresholds": {
      "target": 100.0,
      "warn": 175.0,
      "crit": 250.0
    },
    "direction": "lower_better",
    "priority": "quality",
    "tile": "quality",
    "stage": 5,
    "source": "erp",
    "tags": {},
    "days": 365,
    "stale": false
  },
  {
    "node_id": 11,
    "name": "site_load",
    "metric": "site_load",
    "title": "Загрузка участка",
    "compute": "measured",
    "pinned": false,
    "units": "relative",
    "unit": "% к цели",
    "value": 97.8588,
    "value_date": "2026-11-22",
    "status": "green",
    "severity": 0.0,
    "level": "ok",
    "status_source": "thresholds",
    "profile": "default",
    "thresholds": {
      "target": 100.0,
      "warn": 111.7647,
      "crit": 123.5294
    },
    "direction": "lower_better",
    "priority": "cost",
    "tile": "production",
    "stage": 5,
    "source": "erp",
    "tags": {},
    "days": 365,
    "stale": false
  }
]
```

### GET /api/kpi/11/defect_rate?from=2026-11-10T00:00:00+03:00&to=2026-11-23T09:00:00+03:00&agg=day
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/kpi/11/defect_rate?from=2026-11-10T00:00:00+03:00&to=2026-11-23T09:00:00+03:00&agg=day"
```
Ответ `200`:

```json
{
  "node_id": 11,
  "name": "defect_rate",
  "metric": "defect_rate",
  "title": "Доля брака",
  "compute": "measured",
  "pinned": true,
  "units": "natural",
  "unit": "%",
  "value": 6.4,
  "value_date": "2026-11-22",
  "status": "red",
  "severity": 1.0,
  "level": "crit",
  "status_source": "thresholds",
  "profile": "default",
  "thresholds": {
    "target": 2.0,
    "warn": 3.5,
    "crit": 5.0
  },
  "direction": "lower_better",
  "priority": "quality",
  "tile": "quality",
  "stage": 5,
  "source": "erp",
  "tags": {},
  "days": 365,
  "stale": false,
  "agg": "day",
  "points": [
    {
      "ts": "2026-11-09T21:00:00Z",
      "value": 1.63
    },
    {
      "ts": "2026-11-10T21:00:00Z",
      "value": 1.81
    },
    {
      "ts": "2026-11-11T21:00:00Z",
      "value": 1.68
    },
    "… ещё 10"
  ],
  "flags": [
    {
      "ts": "2026-11-10T21:00:00Z",
      "kind": "annotation",
      "values": [],
      "label": "Запуск новой обложки",
      "ref": "E-000974"
    }
  ]
}
```

### GET /api/kpi/11/defect_rate/forecast?horizon=14
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/kpi/11/defect_rate/forecast?horizon=14"
```
Ответ `200`:

```json
{
  "node_id": 11,
  "kpi": "defect_rate",
  "title": "Доля брака",
  "method": "linear_trend+weekday_seasonality",
  "method_text": "Линейный тренд (наименьшие квадраты) по последним 28 суткам плюс средние отклонения по дням недели; коридор ±1σ остатков. Простая модель без внешних данных.",
  "horizon": 14,
  "lookback_days": 28,
  "units": "natural",
  "unit": "%",
  "direction": "lower_better",
  "status_now": "red",
  "history_from": "2026-10-26",
  "history_to": "2026-11-22",
  "history_days": 28,
  "stale": false,
  "enough_data": true,
  "seasonal": true,
  "trend_per_day": 0.1466,
  "sigma": 0.8575,
  "points": [
    {
      "date": "2026-11-23",
      "ts": "2026-11-22T21:00:00Z",
      "value": 4.8482,
      "lower": 3.9907,
      "upper": 5.7057
    },
    {
      "date": "2026-11-24",
      "ts": "2026-11-23T21:00:00Z",
      "value": 4.8882,
      "lower": 4.0307,
      "upper": 5.7457
    },
    {
      "date": "2026-11-25",
      "ts": "2026-11-24T21:00:00Z",
      "value": 5.0532,
      "lower": 4.1957,
      "upper": 5.9107
    },
    "… ещё 11"
  ],
  "crossings": {
    "warn": {
      "date": "2026-11-23",
      "in_days": 0,
      "value": 4.8482,
      "threshold": 3.5,
      "profile": "default",
      "already": true
    },
    "crit": {
      "date": "2026-11-25",
      "in_days": 2,
      "value": 5.0532,
      "threshold": 5.0,
      "profile": "default",
      "already": true
    }
  }
}
```

## Расследование
Сигнал → контекст → причина (слайд 4).

### GET /api/analysis/trace?node=5&kpi=defect_tickets_share
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/analysis/trace?node=5&kpi=defect_tickets_share"
```
Ответ `200`:

```json
{
  "start": {
    "node_id": 5,
    "kpi": "defect_tickets_share"
  },
  "steps": [
    {
      "depth": 0,
      "node_id": 5,
      "node_name": "Поддержка",
      "node_type": "department",
      "owner": "Зам. по работе с клиентами",
      "visible": true,
      "kpi": "defect_tickets_share",
      "title": "Доля обращений по браку",
      "status": "red",
      "severity": 1.0,
      "value": 9.0,
      "value_date": "2026-11-22",
      "unit": "%",
      "via": null,
      "chosen": {
        "link_id": "L-0018",
        "to_node": 11,
        "to_node_name": "Сборка",
        "owner": "Зам. по производству",
        "to_kpi": "defect_rate",
        "target_kpi": "defect_rate",
        "weight": 0.6,
        "access": "none",
        "status": "red",
        "visible": true,
        "severity": 1.0,
        "contribution": 0.6,
        "share": 0.923077
      },
      "alternatives": [
        {
          "link_id": "L-0019",
          "to_node": 12,
          "to_node_name": "ОТК",
          "owner": "Зам. по производству",
          "to_kpi": "defect_escape_rate",
          "target_kpi": "defect_escape_rate",
          "weight": 0.25,
          "access": "none",
          "status": "green",
          "visible": true,
          "severity": 0.2,
          "contribution": 0.05,
          "share": 0.076923
        }
      ]
    },
    {
      "depth": 1,
      "node_id": 11,
      "node_name": "Сборка",
      "node_type": "department",
      "owner": "Зам. по производству",
      "visible": true,
      "kpi": "defect_rate",
      "title": "Доля брака",
      "status": "red",
      "severity": 1.0,
      "value": 6.4,
      "value_date": "2026-11-22",
      "unit": "%",
      "via": {
        "link_id": "L-0018",
        "to_node": 11,
        "to_node_name": "Сборка",
        "owner": "Зам. по производству",
        "to_kpi": "defect_rate",
        "target_kpi": "defect_rate",
        "weight": 0.6,
        "access": "none",
        "status": "red",
        "visible": true,
        "severity": 1.0,
        "contribution": 0.6,
        "share": 0.923077
      },
      "chosen": null,
      "alternatives": [
        {
          "link_id": "L-0025",
          "to_node": 23,
          "to_node_name": "Смены",
          "owner": "HR",
          "to_kpi": "shift_load",
          "target_kpi": "shift_load",
          "weight": 0.25,
          "access": "none",
          "status": "yellow",
          "visible": true,
          "severity": 0.48,
          "contribution": 0.12,
          "share": 1.0
        }
      ]
    }
  ],
  "root_cause": {
    "node_id": 11,
    "node_name": "Сборка",
    "kpi": "defect_rate",
    "visible": true
  },
  "stopped_reason": "below_threshold",
  "min_contribution": 0.15
}
```

### GET /api/deviations/DEV-0001
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/deviations/DEV-0001"
```
Ответ `200`:

```json
{
  "id": "DEV-0001",
  "node_id": 5,
  "node_name": "Поддержка",
  "kpi": "defect_tickets_share",
  "title": "Доля обращений по браку",
  "status": "open",
  "created_at": "2026-11-23T09:00:00+03:00",
  "signal": {
    "ts": "2026-11-23T09:00:00+03:00",
    "day": "2026-11-22",
    "value": 9.0,
    "status": "red",
    "level": "crit",
    "threshold": 8.0,
    "detected_by": "auto"
  },
  "context": {
    "tile": "quality",
    "stage": 7,
    "season_profile": "default",
    "dims": {
      "product_line": "Выпускные альбомы",
      "brand": "ФФ РФ"
    },
    "window": {
      "from": "2026-11-16T00:00:00+03:00",
      "to": "2026-11-23T00:00:00+03:00"
    }
  },
  "cause": {
    "trace": [
      {
        "depth": 0,
        "node_id": 5,
        "node_name": "Поддержка",
        "node_type": "department",
        "owner": "Зам. по работе с клиентами",
        "visible": true,
        "kpi": "defect_tickets_share",
        "title": "Доля обращений по браку",
        "status": "red",
        "severity": 1.0,
        "value": 9.0,
        "value_date": "2026-11-22",
        "unit": "%",
        "via": null,
        "chosen": {
          "link_id": "L-0018",
          "to_node": 11,
          "to_node_name": "Сборка",
          "owner": "Зам. по производству",
          "to_kpi": "defect_rate",
          "target_kpi": "defect_rate",
          "weight": 0.6,
          "access": "none",
          "status": "red",
          "visible": true,
          "severity": 1.0,
          "contribution": 0.6,
          "share": 0.923077
        },
        "alternatives": [
          {
            "link_id": "L-0019",
            "to_node": 12,
            "to_node_name": "ОТК",
            "owner": "Зам. по производству",
            "to_kpi": "defect_escape_rate",
            "target_kpi": "defect_escape_rate",
            "weight": 0.25,
            "access": "none",
            "status": "green",
            "visible": true,
            "severity": 0.2,
            "contribution": 0.05,
            "share": 0.076923
          }
        ]
      },
      {
        "depth": 1,
        "node_id": 11,
        "node_name": "Сборка",
        "node_type": "department",
        "owner": "Зам. по производству",
        "visible": true,
        "kpi": "defect_rate",
        "title": "Доля брака",
        "status": "red",
        "severity": 1.0,
        "value": 6.4,
        "value_date": "2026-11-22",
        "unit": "%",
        "via": {
          "link_id": "L-0018",
          "to_node": 11,
          "to_node_name": "Сборка",
          "owner": "Зам. по производству",
          "to_kpi": "defect_rate",
          "target_kpi": "defect_rate",
          "weight": 0.6,
          "access": "none",
          "status": "red",
          "visible": true,
          "severity": 1.0,
          "contribution": 0.6,
          "share": 0.923077
        },
        "chosen": null,
        "alternatives": [
          {
            "link_id": "L-0025",
            "to_node": 23,
            "to_node_name": "Смены",
            "owner": "HR",
            "to_kpi": "shift_load",
            "target_kpi": "shift_load",
            "weight": 0.25,
            "access": "none",
            "status": "yellow",
            "visible": true,
            "severity": 0.48,
            "contribution": 0.12,
            "share": 1.0
          }
        ]
      }
    ],
    "root": {
      "node_id": 11,
      "node_name": "Сборка",
      "kpi": "defect_rate"
    },
    "stopped_reason": "below_threshold",
    "hypothesis": "",
    "confidence": "high",
    "confidence_basis": {
      "node_id": 12,
      "kpi": "confirmed_defect_share",
      "value": 73.05,
      "status": "green"
    },
    "set_by": null
  },
  "action": {
    "text": "",
    "owner_login": null,
    "owner_node": null,
    "due_at": null,
    "playbook_ref": null,
    "assigned_at": null,
    "assigned_by": null,
    "first_assigned_at": null,
    "done_at": null,
    "done_by": null
  },
  "rechecks": [],
  "resolution": null,
  "affected_orders": {
    "count": 8,
    "sample": [
      "ORD-000119",
      "ORD-000121",
      "… ещё 6"
    ],
    "dims": {
      "product_line": "Выпускные альбомы",
      "brand": "ФФ РФ"
    },
    "stage": 7,
    "window": {
      "from": "2026-11-16T00:00:00+03:00",
      "to": "2026-11-23T00:00:00+03:00"
    }
  },
  "history": [
    {
      "ts": "2026-11-23T09:00:00+03:00",
      "user": "system",
      "change": "created",
      "detected_by": "auto"
    }
  ],
  "synthetic": true,
  "overdue": false,
  "current": {
    "value": 9.0,
    "value_date": "2026-11-22",
    "status": "red",
    "severity": 1.0
  }
}
```

## Решения (портфель)
Главный критерий: решение сохранено и перепроверено.

### GET /api/deviations
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/deviations"
```
Ответ `200`:

```json
{
  "items": [
    {
      "id": "DEV-0001",
      "node_id": 5,
      "node_name": "Поддержка",
      "kpi": "defect_tickets_share",
      "title": "Доля обращений по браку",
      "status": "open",
      "created_at": "2026-11-23T09:00:00+03:00",
      "signal": {
        "ts": "2026-11-23T09:00:00+03:00",
        "day": "2026-11-22",
        "value": 9.0,
        "status": "red",
        "level": "crit",
        "threshold": 8.0,
        "detected_by": "auto"
      },
      "context": {
        "tile": "quality",
        "stage": 7,
        "season_profile": "default",
        "dims": {
          "product_line": "Выпускные альбомы",
          "brand": "ФФ РФ"
        },
        "window": {
          "from": "2026-11-16T00:00:00+03:00",
          "to": "2026-11-23T00:00:00+03:00"
        }
      },
      "cause": {
        "trace": [
          {
            "depth": 0,
            "node_id": 5,
            "node_name": "Поддержка",
            "node_type": "department",
            "owner": "Зам. по работе с клиентами",
            "visible": true,
            "kpi": "defect_tickets_share",
            "title": "Доля обращений по браку",
            "status": "red",
            "severity": 1.0,
            "value": 9.0,
            "value_date": "2026-11-22",
            "unit": "%",
            "via": null,
            "chosen": {
              "link_id": "L-0018",
              "to_node": 11,
              "to_node_name": "Сборка",
              "owner": "Зам. по производству",
              "to_kpi": "defect_rate",
              "target_kpi": "defect_rate",
              "weight": 0.6,
              "access": "none",
              "status": "red",
              "visible": true,
              "severity": 1.0,
              "contribution": 0.6,
              "share": 0.923077
            },
            "alternatives": [
              {
                "link_id": "L-0019",
                "to_node": 12,
                "to_node_name": "ОТК",
                "owner": "Зам. по производству",
                "to_kpi": "defect_escape_rate",
                "target_kpi": "defect_escape_rate",
                "weight": 0.25,
                "access": "none",
                "status": "green",
                "visible": true,
                "severity": 0.2,
                "contribution": 0.05,
                "share": 0.076923
              }
            ]
          },
          {
            "depth": 1,
            "node_id": 11,
            "node_name": "Сборка",
            "node_type": "department",
            "owner": "Зам. по производству",
            "visible": true,
            "kpi": "defect_rate",
            "title": "Доля брака",
            "status": "red",
            "severity": 1.0,
            "value": 6.4,
            "value_date": "2026-11-22",
            "unit": "%",
            "via": {
              "link_id": "L-0018",
              "to_node": 11,
              "to_node_name": "Сборка",
              "owner": "Зам. по производству",
              "to_kpi": "defect_rate",
              "target_kpi": "defect_rate",
              "weight": 0.6,
              "access": "none",
              "status": "red",
              "visible": true,
              "severity": 1.0,
              "contribution": 0.6,
              "share": 0.923077
            },
            "chosen": null,
            "alternatives": [
              {
                "link_id": "L-0025",
                "to_node": 23,
                "to_node_name": "Смены",
                "owner": "HR",
                "to_kpi": "shift_load",
                "target_kpi": "shift_load",
                "weight": 0.25,
                "access": "none",
                "status": "yellow",
                "visible": true,
                "severity": 0.48,
                "contribution": 0.12,
                "share": 1.0
              }
            ]
          }
        ],
        "root": {
          "node_id": 11,
          "node_name": "Сборка",
          "kpi": "defect_rate"
        },
        "stopped_reason": "below_threshold",
        "hypothesis": "",
        "confidence": "high",
        "confidence_basis": {
          "node_id": 12,
          "kpi": "confirmed_defect_share",
          "value": 73.05,
          "status": "green"
        },
        "set_by": null
      },
      "action": {
        "text": "",
        "owner_login": null,
        "owner_node": null,
        "due_at": null,
        "playbook_ref": null,
        "assigned_at": null,
        "assigned_by": null,
        "first_assigned_at": null,
        "done_at": null,
        "done_by": null
      },
      "rechecks": [],
      "resolution": null,
      "affected_orders": {
        "count": 8,
        "sample": [
          "ORD-000119",
          "ORD-000121",
          "… ещё 6"
        ],
        "dims": {
          "product_line": "Выпускные альбомы",
          "brand": "ФФ РФ"
        },
        "stage": 7,
        "window": {
          "from": "2026-11-16T00:00:00+03:00",
          "to": "2026-11-23T00:00:00+03:00"
        }
      },
      "history": [
        {
          "ts": "2026-11-23T09:00:00+03:00",
          "user": "system",
          "change": "created",
          "detected_by": "auto"
        }
      ],
      "synthetic": true,
      "overdue": false,
      "current": {
        "value": 9.0,
        "value_date": "2026-11-22",
        "status": "red",
        "severity": 1.0
      }
    }
  ],
  "summary": {
    "total": 1,
    "open": 1,
    "overdue": 0,
    "verified": 0,
    "failed": 0,
    "rechecks": 0,
    "recheck_success_rate": null,
    "by_status": {
      "open": 1,
      "assigned": 0,
      "in_progress": 0,
      "done": 0,
      "verified": 0,
      "failed": 0,
      "escalated": 0,
      "closed": 0
    }
  }
}
```

### GET /api/deviations/DEV-0001/suggest
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/deviations/DEV-0001/suggest"
```
Ответ `200`:

```json
{
  "deviation_id": "DEV-0001",
  "root": {
    "node_id": 11,
    "node_name": "Сборка",
    "kpi": "defect_rate",
    "metric": "defect_rate",
    "node_type": "department"
  },
  "suggestions": [
    {
      "id": "PB-DEFECT-BATCH",
      "title": "Проверить партию материала и усилить выходной контроль",
      "action": "Проверить партию материала, запущенную перед ростом брака; на время проверки усилить выборочный контроль ОТК на участке",
      "owner_hint": "Зам. по производству",
      "due_days": 3,
      "due_at": "2026-11-26T09:00:00+03:00",
      "recheck_window_days": 7,
      "score": 5
    },
    {
      "id": "PB-DEFECT-LOAD",
      "title": "Снизить нагрузку смены на участке",
      "action": "Перераспределить заказы между сменами, чтобы нагрузка вернулась к норме; проверить укомплектованность смены",
      "owner_hint": "Зам. по производству",
      "due_days": 2,
      "due_at": "2026-11-25T09:00:00+03:00",
      "recheck_window_days": 7,
      "score": 4
    },
    "… ещё 1"
  ]
}
```

### GET /api/deviations/DEV-0001/orders
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/deviations/DEV-0001/orders"
```
Ответ `200`:

```json
{
  "count": 8,
  "sample": [
    "ORD-000119",
    "ORD-000121",
    "… ещё 6"
  ],
  "dims": {
    "product_line": "Выпускные альбомы",
    "brand": "ФФ РФ"
  },
  "stage": 7,
  "window": {
    "from": "2026-11-16T00:00:00+03:00",
    "to": "2026-11-23T00:00:00+03:00"
  }
}
```

### PATCH /api/deviations/DEV-0001
Тело запроса:

```json
{
  "status": "assigned",
  "action": {
    "text": "Проверить партию материала, запущенную перед ростом брака; на время проверки усилить выборочный контроль ОТК на участке",
    "owner_login": "head_prod",
    "due_at": "2026-11-26T09:00:00+03:00",
    "playbook_ref": "PB-DEFECT-BATCH"
  }
}
```
```bash
curl -s -X PATCH -H "X-User: director" "http://127.0.0.1:8000/api/deviations/DEV-0001" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```
Ответ `200`:

```json
{
  "id": "DEV-0001",
  "node_id": 5,
  "node_name": "Поддержка",
  "kpi": "defect_tickets_share",
  "title": "Доля обращений по браку",
  "status": "assigned",
  "created_at": "2026-11-23T09:00:00+03:00",
  "signal": {
    "ts": "2026-11-23T09:00:00+03:00",
    "day": "2026-11-22",
    "value": 9.0,
    "status": "red",
    "level": "crit",
    "threshold": 8.0,
    "detected_by": "auto"
  },
  "context": {
    "tile": "quality",
    "stage": 7,
    "season_profile": "default",
    "dims": {
      "product_line": "Выпускные альбомы",
      "brand": "ФФ РФ"
    },
    "window": {
      "from": "2026-11-16T00:00:00+03:00",
      "to": "2026-11-23T00:00:00+03:00"
    }
  },
  "cause": {
    "trace": [
      {
        "depth": 0,
        "node_id": 5,
        "node_name": "Поддержка",
        "node_type": "department",
        "owner": "Зам. по работе с клиентами",
        "visible": true,
        "kpi": "defect_tickets_share",
        "title": "Доля обращений по браку",
        "status": "red",
        "severity": 1.0,
        "value": 9.0,
        "value_date": "2026-11-22",
        "unit": "%",
        "via": null,
        "chosen": {
          "link_id": "L-0018",
          "to_node": 11,
          "to_node_name": "Сборка",
          "owner": "Зам. по производству",
          "to_kpi": "defect_rate",
          "target_kpi": "defect_rate",
          "weight": 0.6,
          "access": "none",
          "status": "red",
          "visible": true,
          "severity": 1.0,
          "contribution": 0.6,
          "share": 0.923077
        },
        "alternatives": [
          {
            "link_id": "L-0019",
            "to_node": 12,
            "to_node_name": "ОТК",
            "owner": "Зам. по производству",
            "to_kpi": "defect_escape_rate",
            "target_kpi": "defect_escape_rate",
            "weight": 0.25,
            "access": "none",
            "status": "green",
            "visible": true,
            "severity": 0.2,
            "contribution": 0.05,
            "share": 0.076923
          }
        ]
      },
      {
        "depth": 1,
        "node_id": 11,
        "node_name": "Сборка",
        "node_type": "department",
        "owner": "Зам. по производству",
        "visible": true,
        "kpi": "defect_rate",
        "title": "Доля брака",
        "status": "red",
        "severity": 1.0,
        "value": 6.4,
        "value_date": "2026-11-22",
        "unit": "%",
        "via": {
          "link_id": "L-0018",
          "to_node": 11,
          "to_node_name": "Сборка",
          "owner": "Зам. по производству",
          "to_kpi": "defect_rate",
          "target_kpi": "defect_rate",
          "weight": 0.6,
          "access": "none",
          "status": "red",
          "visible": true,
          "severity": 1.0,
          "contribution": 0.6,
          "share": 0.923077
        },
        "chosen": null,
        "alternatives": [
          {
            "link_id": "L-0025",
            "to_node": 23,
            "to_node_name": "Смены",
            "owner": "HR",
            "to_kpi": "shift_load",
            "target_kpi": "shift_load",
            "weight": 0.25,
            "access": "none",
            "status": "yellow",
            "visible": true,
            "severity": 0.48,
            "contribution": 0.12,
            "share": 1.0
          }
        ]
      }
    ],
    "root": {
      "node_id": 11,
      "node_name": "Сборка",
      "kpi": "defect_rate"
    },
    "stopped_reason": "below_threshold",
    "hypothesis": "",
    "confidence": "high",
    "confidence_basis": {
      "node_id": 12,
      "kpi": "confirmed_defect_share",
      "value": 73.05,
      "status": "green"
    },
    "set_by": null
  },
  "action": {
    "text": "Проверить партию материала, запущенную перед ростом брака; на время проверки усилить выборочный контроль ОТК на участке",
    "owner_login": "head_prod",
    "owner_node": null,
    "due_at": "2026-11-26T09:00:00+03:00",
    "playbook_ref": "PB-DEFECT-BATCH",
    "assigned_at": "2026-11-23T09:00:00+03:00",
    "assigned_by": "director",
    "first_assigned_at": "2026-11-23T09:00:00+03:00",
    "done_at": null,
    "done_by": null
  },
  "rechecks": [],
  "resolution": null,
  "affected_orders": {
    "count": 8,
    "sample": [
      "ORD-000119",
      "ORD-000121",
      "… ещё 6"
    ],
    "dims": {
      "product_line": "Выпускные альбомы",
      "brand": "ФФ РФ"
    },
    "stage": 7,
    "window": {
      "from": "2026-11-16T00:00:00+03:00",
      "to": "2026-11-23T00:00:00+03:00"
    }
  },
  "history": [
    {
      "ts": "2026-11-23T09:00:00+03:00",
      "user": "system",
      "change": "created",
      "detected_by": "auto"
    },
    {
      "ts": "2026-11-23T09:00:00+03:00",
      "user": "director",
      "change": "action",
      "fields": [
        "due_at",
        "owner_login",
        "… ещё 2"
      ]
    },
    "… ещё 1"
  ],
  "synthetic": true,
  "overdue": false,
  "current": {
    "value": 9.0,
    "value_date": "2026-11-22",
    "status": "red",
    "severity": 1.0
  }
}
```

### POST /api/demo/advance?days=7
Перемотка демо-времени (см. «Демо»).
```bash
curl -s -X POST -H "X-User: director" "http://127.0.0.1:8000/api/demo/advance?days=7"
```
Ответ `200`:

```json
{
  "now": "2026-11-30T09:00:00+03:00",
  "days": 7,
  "closed_days": [
    "2026-11-23",
    "2026-11-24",
    "… ещё 5"
  ],
  "points_written": 399,
  "branches": {
    "ОТК/defect_escape_rate": "with_action",
    "Поддержка/defect_tickets_share": "with_action",
    "Сборка/defect_rate": "with_action",
    "Смены/shift_load": "with_action"
  },
  "deviations_created": []
}
```

### POST /api/admin/deviations/DEV-0001/recheck
```bash
curl -s -X POST -H "X-User: director" "http://127.0.0.1:8000/api/admin/deviations/DEV-0001/recheck"
```
Ответ `200`:

```json
{
  "recheck": {
    "n": 1,
    "ts": "2026-11-30T09:00:00+03:00",
    "user": "director",
    "window_days": 7,
    "reference": "action",
    "reference_ts": "2026-11-23T09:00:00+03:00",
    "without_action": false,
    "elapsed_days": 7.0,
    "min_days": 3,
    "profile": "default",
    "target": 4.0,
    "baseline": {
      "from": "2026-11-16T09:00:00+03:00",
      "to": "2026-11-23T09:00:00+03:00",
      "days": 7,
      "value": 7.7825,
      "severity": 0.945625
    },
    "after": {
      "from": "2026-11-23T09:00:00+03:00",
      "to": "2026-11-30T09:00:00+03:00",
      "days": 6,
      "value": 4.436717,
      "severity": 0.109179
    },
    "improvement": 0.836446,
    "min_improvement": 0.5,
    "result": "passed",
    "passed": true,
    "rule": "improvement",
    "status_before": "assigned",
    "status_after": "verified"
  },
  "deviation": {
    "id": "DEV-0001",
    "node_id": 5,
    "node_name": "Поддержка",
    "kpi": "defect_tickets_share",
    "title": "Доля обращений по браку",
    "status": "verified",
    "created_at": "2026-11-23T09:00:00+03:00",
    "signal": {
      "ts": "2026-11-23T09:00:00+03:00",
      "day": "2026-11-22",
      "value": 9.0,
      "status": "red",
      "level": "crit",
      "threshold": 8.0,
      "detected_by": "auto"
    },
    "context": {
      "tile": "quality",
      "stage": 7,
      "season_profile": "default",
      "dims": {
        "product_line": "Выпускные альбомы",
        "brand": "ФФ РФ"
      },
      "window": {
        "from": "2026-11-16T00:00:00+03:00",
        "to": "2026-11-23T00:00:00+03:00"
      }
    },
    "cause": {
      "trace": [
        {
          "depth": 0,
          "node_id": 5,
          "node_name": "Поддержка",
          "node_type": "department",
          "owner": "Зам. по работе с клиентами",
          "visible": true,
          "kpi": "defect_tickets_share",
          "title": "Доля обращений по браку",
          "status": "red",
          "severity": 1.0,
          "value": 9.0,
          "value_date": "2026-11-22",
          "unit": "%",
          "via": null,
          "chosen": {
            "link_id": "L-0018",
            "to_node": 11,
            "to_node_name": "Сборка",
            "owner": "Зам. по производству",
            "to_kpi": "defect_rate",
            "target_kpi": "defect_rate",
            "weight": 0.6,
            "access": "none",
            "status": "red",
            "visible": true,
            "severity": 1.0,
            "contribution": 0.6,
            "share": 0.923077
          },
          "alternatives": [
            {
              "link_id": "L-0019",
              "to_node": 12,
              "to_node_name": "ОТК",
              "owner": "Зам. по производству",
              "to_kpi": "defect_escape_rate",
              "target_kpi": "defect_escape_rate",
              "weight": 0.25,
              "access": "none",
              "status": "green",
              "visible": true,
              "severity": 0.2,
              "contribution": 0.05,
              "share": 0.076923
            }
          ]
        },
        {
          "depth": 1,
          "node_id": 11,
          "node_name": "Сборка",
          "node_type": "department",
          "owner": "Зам. по производству",
          "visible": true,
          "kpi": "defect_rate",
          "title": "Доля брака",
          "status": "red",
          "severity": 1.0,
          "value": 6.4,
          "value_date": "2026-11-22",
          "unit": "%",
          "via": {
            "link_id": "L-0018",
            "to_node": 11,
            "to_node_name": "Сборка",
            "owner": "Зам. по производству",
            "to_kpi": "defect_rate",
            "target_kpi": "defect_rate",
            "weight": 0.6,
            "access": "none",
            "status": "red",
            "visible": true,
            "severity": 1.0,
            "contribution": 0.6,
            "share": 0.923077
          },
          "chosen": null,
          "alternatives": [
            {
              "link_id": "L-0025",
              "to_node": 23,
              "to_node_name": "Смены",
              "owner": "HR",
              "to_kpi": "shift_load",
              "target_kpi": "shift_load",
              "weight": 0.25,
              "access": "none",
              "status": "yellow",
              "visible": true,
              "severity": 0.48,
              "contribution": 0.12,
              "share": 1.0
            }
          ]
        }
      ],
      "root": {
        "node_id": 11,
        "node_name": "Сборка",
        "kpi": "defect_rate"
      },
      "stopped_reason": "below_threshold",
      "hypothesis": "",
      "confidence": "high",
      "confidence_basis": {
        "node_id": 12,
        "kpi": "confirmed_defect_share",
        "value": 73.05,
        "status": "green"
      },
      "set_by": null
    },
    "action": {
      "text": "Проверить партию материала, запущенную перед ростом брака; на время проверки усилить выборочный контроль ОТК на участке",
      "owner_login": "head_prod",
      "owner_node": null,
      "due_at": "2026-11-26T09:00:00+03:00",
      "playbook_ref": "PB-DEFECT-BATCH",
      "assigned_at": "2026-11-23T09:00:00+03:00",
      "assigned_by": "director",
      "first_assigned_at": "2026-11-23T09:00:00+03:00",
      "done_at": null,
      "done_by": null
    },
    "rechecks": [
      {
        "n": 1,
        "ts": "2026-11-30T09:00:00+03:00",
        "user": "director",
        "window_days": 7,
        "reference": "action",
        "reference_ts": "2026-11-23T09:00:00+03:00",
        "without_action": false,
        "elapsed_days": 7.0,
        "min_days": 3,
        "profile": "default",
        "target": 4.0,
        "baseline": {
          "from": "2026-11-16T09:00:00+03:00",
          "to": "2026-11-23T09:00:00+03:00",
          "days": 7,
          "value": 7.7825,
          "severity": 0.945625
        },
        "after": {
          "from": "2026-11-23T09:00:00+03:00",
          "to": "2026-11-30T09:00:00+03:00",
          "days": 6,
          "value": 4.436717,
          "severity": 0.109179
        },
        "improvement": 0.836446,
        "min_improvement": 0.5,
        "result": "passed",
        "passed": true,
        "rule": "improvement",
        "status_before": "assigned",
        "status_after": "verified"
      }
    ],
    "resolution": null,
    "affected_orders": {
      "count": 8,
      "sample": [
        "ORD-000119",
        "ORD-000121",
        "… ещё 6"
      ],
      "dims": {
        "product_line": "Выпускные альбомы",
        "brand": "ФФ РФ"
      },
      "stage": 7,
      "window": {
        "from": "2026-11-16T00:00:00+03:00",
        "to": "2026-11-23T00:00:00+03:00"
      }
    },
    "history": [
      {
        "ts": "2026-11-23T09:00:00+03:00",
        "user": "system",
        "change": "created",
        "detected_by": "auto"
      },
      {
        "ts": "2026-11-23T09:00:00+03:00",
        "user": "director",
        "change": "action",
        "fields": [
          "due_at",
          "owner_login",
          "… ещё 2"
        ]
      },
      "… ещё 2"
    ],
    "synthetic": true,
    "overdue": false,
    "current": {
      "value": 3.6399,
      "value_date": "2026-11-29",
      "status": "green",
      "severity": 0.0
    }
  }
}
```

## Поток заказов
8 этапов × событие, статус, владелец, проверяемый результат (слайд 2).

### GET /api/flow/summary
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/flow/summary"
```
Ответ `200`:

```json
{
  "now": "2026-11-30T09:00:00+03:00",
  "orders_total": 169,
  "in_progress": 18,
  "completed": 151,
  "stages": [
    {
      "stage": 1,
      "name": "Сигнал",
      "focus": "спрос / обращение",
      "source": "crm",
      "owner": {
        "node_id": 6,
        "node_name": "Лидогенерация",
        "login": null
      },
      "norm_hours": 2.0,
      "criterion": "обращение взято в работу в SLA",
      "visible": true,
      "orders": 169,
      "pending": 0,
      "in_work": 0,
      "overdue": 0,
      "done": 150,
      "late": 19,
      "defect": 0,
      "checked": 169,
      "passed_share": 0.8876,
      "problems": 19
    },
    {
      "stage": 2,
      "name": "Клиент",
      "focus": "контекст / история",
      "source": "crm",
      "owner": {
        "node_id": 4,
        "node_name": "Продажи",
        "login": null
      },
      "norm_hours": 4.0,
      "criterion": "карточка клиента и история заказов подтянуты",
      "visible": true,
      "orders": 169,
      "pending": 0,
      "in_work": 0,
      "overdue": 0,
      "done": 153,
      "late": 16,
      "defect": 0,
      "checked": 169,
      "passed_share": 0.9053,
      "problems": 16
    },
    "… ещё 6"
  ],
  "bottleneck": {
    "stage": 6,
    "name": "Доставка",
    "overdue": 0,
    "in_work": 6
  },
  "synthetic": true
}
```

### GET /api/orders?product_line=Выпускные альбомы&stage=5&status=defect
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/orders?product_line=Выпускные альбомы&stage=5&status=defect"
```
Ответ `200`:

```json
{
  "total": 10,
  "items": [
    {
      "order_id": "ORD-000147",
      "customer_id": "C-0011",
      "product_line": "Выпускные альбомы",
      "brand": "ФФ РФ",
      "segment": "B2B",
      "created_at": "2026-11-21T12:51:00+03:00",
      "status": "completed",
      "current_stage": null,
      "issues": [
        {
          "stage": 5,
          "issue": "брак"
        },
        {
          "stage": 7,
          "issue": "обращение по браку"
        }
      ],
      "stages": [
        {
          "stage": 1,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 2,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        "… ещё 6"
      ],
      "prev_order_id": "ORD-000142",
      "next_order_id": null,
      "synthetic": true
    },
    {
      "order_id": "ORD-000142",
      "customer_id": "C-0011",
      "product_line": "Выпускные альбомы",
      "brand": "ФФ РФ",
      "segment": "B2B",
      "created_at": "2026-11-18T20:22:00+03:00",
      "status": "completed",
      "current_stage": null,
      "issues": [
        {
          "stage": 5,
          "issue": "брак"
        },
        {
          "stage": 7,
          "issue": "обращение по браку"
        }
      ],
      "stages": [
        {
          "stage": 1,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 2,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        "… ещё 6"
      ],
      "prev_order_id": null,
      "next_order_id": "ORD-000147",
      "synthetic": true
    },
    "… ещё 8"
  ]
}
```

### GET /api/orders/ORD-000147
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/orders/ORD-000147"
```
Ответ `200`:

```json
{
  "order_id": "ORD-000147",
  "customer_id": "C-0011",
  "product_line": "Выпускные альбомы",
  "brand": "ФФ РФ",
  "segment": "B2B",
  "created_at": "2026-11-21T12:51:00+03:00",
  "status": "completed",
  "current_stage": null,
  "stages": [
    {
      "stage": 1,
      "name": "Сигнал",
      "source": "crm",
      "event_id": "E-001335",
      "status": "done",
      "owner": {
        "node_id": 6,
        "node_name": "Лидогенерация",
        "login": null
      },
      "result_check": {
        "criterion": "обращение взято в работу в SLA",
        "passed": true,
        "checked_at": "2026-11-21T13:44:00+03:00"
      },
      "issue": null,
      "started_at": "2026-11-21T12:51:00+03:00",
      "due_at": "2026-11-21T14:51:00+03:00",
      "finished_at": "2026-11-21T13:44:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    },
    {
      "stage": 2,
      "name": "Клиент",
      "source": "crm",
      "event_id": "E-001337",
      "status": "done",
      "owner": {
        "node_id": 4,
        "node_name": "Продажи",
        "login": null
      },
      "result_check": {
        "criterion": "карточка клиента и история заказов подтянуты",
        "passed": true,
        "checked_at": "2026-11-21T17:31:00+03:00"
      },
      "issue": null,
      "started_at": "2026-11-21T14:02:00+03:00",
      "due_at": "2026-11-21T18:02:00+03:00",
      "finished_at": "2026-11-21T17:31:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    },
    {
      "stage": 3,
      "name": "Заказ",
      "source": "erp",
      "event_id": "E-001339",
      "status": "done",
      "owner": {
        "node_id": 4,
        "node_name": "Продажи",
        "login": null
      },
      "result_check": {
        "criterion": "состав подтверждён, оплата получена",
        "passed": true,
        "checked_at": "2026-11-22T10:11:00+03:00"
      },
      "issue": null,
      "started_at": "2026-11-21T17:35:00+03:00",
      "due_at": "2026-11-22T17:35:00+03:00",
      "finished_at": "2026-11-22T10:11:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    },
    {
      "stage": 4,
      "name": "Проверка",
      "source": "erp",
      "event_id": "E-001359",
      "status": "done",
      "owner": {
        "node_id": 7,
        "node_name": "Модерация",
        "login": null
      },
      "result_check": {
        "criterion": "макет прошёл модерацию без ошибок",
        "passed": true,
        "checked_at": "2026-11-22T15:58:00+03:00"
      },
      "issue": null,
      "started_at": "2026-11-22T10:14:00+03:00",
      "due_at": "2026-11-22T18:14:00+03:00",
      "finished_at": "2026-11-22T15:58:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    },
    {
      "stage": 5,
      "name": "Производство",
      "source": "erp",
      "event_id": "E-001360",
      "status": "defect",
      "owner": {
        "node_id": 11,
        "node_name": "Сборка",
        "login": null
      },
      "result_check": {
        "criterion": "изготовлено за 24 ч и принято ОТК",
        "passed": false,
        "checked_at": "2026-11-23T19:20:00+03:00"
      },
      "issue": "брак",
      "started_at": "2026-11-22T16:00:00+03:00",
      "due_at": "2026-11-23T16:00:00+03:00",
      "finished_at": "2026-11-23T19:20:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    },
    {
      "stage": 6,
      "name": "Доставка",
      "source": "erp",
      "event_id": "E-001381",
      "status": "done",
      "owner": {
        "node_id": 13,
        "node_name": "Склад и отгрузка",
        "login": null
      },
      "result_check": {
        "criterion": "передан в ТК и доставлен в срок",
        "passed": true,
        "checked_at": "2026-11-24T23:30:00+03:00"
      },
      "issue": null,
      "started_at": "2026-11-23T19:52:00+03:00",
      "due_at": "2026-11-26T19:52:00+03:00",
      "finished_at": "2026-11-24T23:30:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    },
    {
      "stage": 7,
      "name": "Поддержка",
      "source": "support",
      "event_id": "E-001402",
      "status": "done",
      "owner": {
        "node_id": 5,
        "node_name": "Поддержка",
        "login": null
      },
      "result_check": {
        "criterion": "обращений нет или обращение решено в SLA",
        "passed": true,
        "checked_at": "2026-11-25T12:13:00+03:00"
      },
      "issue": "обращение по браку",
      "started_at": "2026-11-25T00:28:00+03:00",
      "due_at": "2026-11-26T00:28:00+03:00",
      "finished_at": "2026-11-25T12:13:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": true
    },
    {
      "stage": 8,
      "name": "Возврат",
      "source": "crm",
      "event_id": "E-001419",
      "status": "done",
      "owner": {
        "node_id": 4,
        "node_name": "Продажи",
        "login": null
      },
      "result_check": {
        "criterion": "следующий сценарий запущен в срок: предложение или рекламация",
        "passed": true,
        "checked_at": "2026-11-28T11:51:00+03:00"
      },
      "issue": null,
      "started_at": "2026-11-25T12:31:00+03:00",
      "due_at": "2026-11-28T12:31:00+03:00",
      "finished_at": "2026-11-28T11:51:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    }
  ],
  "issues": [
    {
      "stage": 5,
      "issue": "брак"
    },
    {
      "stage": 7,
      "issue": "обращение по браку"
    }
  ],
  "prev_order_id": "ORD-000142",
  "next_order_id": null,
  "synthetic": true,
  "schema_version": 1
}
```

### GET /api/orders/ORD-000147
Этапы производства для `head_client` урезаны (`visible: false`).
```bash
curl -s -H "X-User: head_client" "http://127.0.0.1:8000/api/orders/ORD-000147"
```
Ответ `200`:

```json
{
  "order_id": "ORD-000147",
  "customer_id": "C-0011",
  "product_line": "Выпускные альбомы",
  "brand": "ФФ РФ",
  "segment": "B2B",
  "created_at": "2026-11-21T12:51:00+03:00",
  "status": "completed",
  "current_stage": null,
  "stages": [
    {
      "stage": 1,
      "name": "Сигнал",
      "source": "crm",
      "event_id": "E-001335",
      "status": "done",
      "owner": {
        "node_id": 6,
        "node_name": "Лидогенерация",
        "login": null
      },
      "result_check": {
        "criterion": "обращение взято в работу в SLA",
        "passed": true,
        "checked_at": "2026-11-21T13:44:00+03:00"
      },
      "issue": null,
      "started_at": "2026-11-21T12:51:00+03:00",
      "due_at": "2026-11-21T14:51:00+03:00",
      "finished_at": "2026-11-21T13:44:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    },
    {
      "stage": 2,
      "name": "Клиент",
      "source": "crm",
      "event_id": "E-001337",
      "status": "done",
      "owner": {
        "node_id": 4,
        "node_name": "Продажи",
        "login": null
      },
      "result_check": {
        "criterion": "карточка клиента и история заказов подтянуты",
        "passed": true,
        "checked_at": "2026-11-21T17:31:00+03:00"
      },
      "issue": null,
      "started_at": "2026-11-21T14:02:00+03:00",
      "due_at": "2026-11-21T18:02:00+03:00",
      "finished_at": "2026-11-21T17:31:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    },
    "… ещё 6"
  ],
  "issues": [
    {
      "stage": 7,
      "issue": "обращение по браку"
    }
  ],
  "prev_order_id": "ORD-000142",
  "next_order_id": null,
  "synthetic": true,
  "schema_version": 1
}
```

## Источники
Пять систем в едином слое (слайд 1). Только чтение.

### GET /api/sources
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/sources"
```
Ответ `200`:

```json
[
  {
    "key": "crm",
    "title": "CRM",
    "system": "Битрикс24",
    "provides": [
      "клиенты",
      "сделки",
      "… ещё 2"
    ],
    "mode": "mock",
    "read_only": true,
    "connector": "в проде — коннектор только на чтение",
    "note": "",
    "events": 497,
    "last_event_at": "2026-11-30T03:42:00+03:00",
    "event_types": [
      "annotation",
      "crm.claim",
      "… ещё 3"
    ],
    "metrics": [
      "leads",
      "orders_rhythm",
      "… ещё 1"
    ],
    "kpis_in_zone": 8
  },
  {
    "key": "support",
    "title": "Поддержка",
    "system": "Mary (омниканал)",
    "provides": [
      "обращения",
      "темы",
      "… ещё 2"
    ],
    "mode": "mock",
    "read_only": true,
    "connector": "в проде — коннектор только на чтение",
    "note": "",
    "events": 157,
    "last_event_at": "2026-11-30T00:34:00+03:00",
    "event_types": [
      "support.survey",
      "support.ticket"
    ],
    "metrics": [
      "defect_tickets_share",
      "mary_closed_share",
      "… ещё 5"
    ],
    "kpis_in_zone": 8
  },
  "… ещё 3"
]
```

### GET /api/events?type=annotation&limit=3
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/events?type=annotation&limit=3"
```
Ответ `200`:

```json
{
  "total": 6,
  "items": [
    {
      "event_id": "E-000974",
      "ts": "2026-11-11T00:00:00+03:00",
      "source": "erp",
      "type": "annotation",
      "order_id": null,
      "customer_id": null,
      "node_id": null,
      "stage": null,
      "payload": {
        "label": "Запуск новой обложки",
        "targets": [
          {
            "node_id": 11,
            "node": "Сборка",
            "kpi": "defect_rate"
          },
          {
            "node_id": 5,
            "node": "Поддержка",
            "kpi": "defect_tickets_share"
          }
        ],
        "dims": {
          "product_line": "Выпускные альбомы",
          "brand": "ФФ РФ"
        }
      },
      "synthetic": true
    },
    {
      "event_id": "E-000694",
      "ts": "2026-11-03T00:00:00+03:00",
      "source": "crm",
      "type": "annotation",
      "order_id": null,
      "customer_id": null,
      "node_id": null,
      "stage": null,
      "payload": {
        "label": "Акция «образцы −50%»",
        "targets": [
          {
            "node_id": 4,
            "node": "Продажи",
            "kpi": "orders_rhythm"
          },
          {
            "node_id": 3,
            "node": "Маркетинг",
            "kpi": "leads"
          }
        ],
        "dims": {
          "product_line": "Образцы"
        }
      },
      "synthetic": true
    },
    "… ещё 1"
  ]
}
```

## Конструктор
Роль builder: узлы, KPI, связи и веса за минуты (раздел 8.1).

### POST /api/builder/glossary
Тело запроса:

```json
{
  "key": "incoming_defect_share",
  "title": "Входной брак материалов",
  "source": "erp",
  "owner": "Зам. по производству",
  "unit": "%",
  "direction": "lower_better",
  "priority": "quality",
  "tile": "quality",
  "stage": 5,
  "display": {
    "relative": "pct_of_target",
    "natural": "%"
  },
  "thresholds": {
    "default": {
      "target": 1.0,
      "warn": 2.0,
      "crit": 3.0
    }
  }
}
```
```bash
curl -s -X POST -H "X-User: builder" "http://127.0.0.1:8000/api/builder/glossary" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```
Ответ `201`:

```json
{
  "title": "Входной брак материалов",
  "definition": "",
  "formula": "",
  "source": "erp",
  "owner": "Зам. по производству",
  "unit": "%",
  "display": {
    "relative": "pct_of_target",
    "natural": "%"
  },
  "money_factor": null,
  "direction": "lower_better",
  "priority": "quality",
  "tile": "quality",
  "stage": 5,
  "thresholds": {
    "default": {
      "target": 1.0,
      "warn": 2.0,
      "crit": 3.0
    }
  },
  "aggregation": "mean",
  "status_window_days": null,
  "synthetic": true
}
```

### POST /api/builder/nodes
Тело запроса:

```json
{
  "name": "Закупки",
  "type": "department",
  "owner": "Зам. по производству"
}
```
```bash
curl -s -X POST -H "X-User: builder" "http://127.0.0.1:8000/api/builder/nodes" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```
Ответ `201`:

```json
{
  "id": 25,
  "name": "Закупки",
  "type": "department",
  "description": "",
  "owner": "Зам. по производству",
  "attrs": {},
  "parameters": {},
  "tile": null,
  "stage": null,
  "tags": {},
  "kpis": [],
  "flags": [],
  "synthetic": false,
  "created_by": "builder",
  "status": "unknown"
}
```

### POST /api/builder/nodes/25/kpis
Тело запроса:

```json
{
  "name": "incoming_defect_share",
  "metric": "incoming_defect_share",
  "pinned": true
}
```
```bash
curl -s -X POST -H "X-User: builder" "http://127.0.0.1:8000/api/builder/nodes/25/kpis" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```
Ответ `201`:

```json
{
  "name": "incoming_defect_share",
  "metric": "incoming_defect_share",
  "compute": "measured",
  "pinned": true,
  "overrides": {},
  "unit": "%"
}
```

### POST /api/builder/links
Остальные веса KPI пропорционально умножились на 0,8 (`kpi_links`).
Тело запроса:

```json
{
  "from_node": 11,
  "from_kpi": "defect_rate",
  "to_node": 25,
  "to_kpi": "incoming_defect_share",
  "weight": 0.2,
  "note": "Брак материалов поставщика"
}
```
```bash
curl -s -X POST -H "X-User: builder" "http://127.0.0.1:8000/api/builder/links" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```
Ответ `201`:

```json
{
  "link": {
    "id": "L-0056",
    "from_node": 11,
    "from_kpi": "defect_rate",
    "to_node": 25,
    "to_kpi": "incoming_defect_share",
    "weight": 0.2,
    "access": "inherit",
    "note": "Брак материалов поставщика",
    "flags": [],
    "created_by": "builder",
    "created_at": "2026-11-30T09:00:00+03:00"
  },
  "kpi_links": [
    {
      "id": "L-0022",
      "from_node": 11,
      "from_kpi": "defect_rate",
      "to_node": 14,
      "to_kpi": "personal_efficiency",
      "weight": 0.2,
      "access": "inherit",
      "note": "",
      "flags": [],
      "created_by": "seed",
      "created_at": "2026-11-23T09:00:00+03:00"
    },
    {
      "id": "L-0023",
      "from_node": 11,
      "from_kpi": "defect_rate",
      "to_node": 15,
      "to_kpi": "personal_efficiency",
      "weight": 0.2,
      "access": "inherit",
      "note": "",
      "flags": [],
      "created_by": "seed",
      "created_at": "2026-11-23T09:00:00+03:00"
    },
    {
      "id": "L-0024",
      "from_node": 11,
      "from_kpi": "defect_rate",
      "to_node": 16,
      "to_kpi": "personal_efficiency",
      "weight": 0.2,
      "access": "inherit",
      "note": "",
      "flags": [],
      "created_by": "seed",
      "created_at": "2026-11-23T09:00:00+03:00"
    },
    "… ещё 2"
  ]
}
```

### PUT /api/builder/kpis/5/defect_tickets_share/weights
Тело запроса:

```json
{
  "weights": {
    "L-0018": 0.6,
    "L-0019": 0.25,
    "L-0020": 0.15
  }
}
```
```bash
curl -s -X PUT -H "X-User: builder" "http://127.0.0.1:8000/api/builder/kpis/5/defect_tickets_share/weights" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```
Ответ `200`:

```json
[
  {
    "id": "L-0018",
    "from_node": 5,
    "from_kpi": "defect_tickets_share",
    "to_node": 11,
    "to_kpi": "defect_rate",
    "weight": 0.6,
    "access": "none",
    "note": "Обращения по браку зависят от брака сборки",
    "flags": [],
    "created_by": "seed",
    "created_at": "2026-11-23T09:00:00+03:00"
  },
  {
    "id": "L-0019",
    "from_node": 5,
    "from_kpi": "defect_tickets_share",
    "to_node": 12,
    "to_kpi": "defect_escape_rate",
    "weight": 0.25,
    "access": "none",
    "note": "Брак, пропущенный ОТК, доходит до клиента",
    "flags": [],
    "created_by": "seed",
    "created_at": "2026-11-23T09:00:00+03:00"
  },
  "… ещё 1"
]
```

### GET /api/builder/validate
```bash
curl -s -H "X-User: builder" "http://127.0.0.1:8000/api/builder/validate"
```
Ответ `200`:

```json
{
  "ok": true,
  "errors": 0,
  "warnings": 1,
  "problems": [
    {
      "code": "kpi_no_data",
      "severity": "warning",
      "message": "у KPI нет ни одной точки",
      "node_id": 25,
      "node_name": "Закупки",
      "kpi": "incoming_defect_share",
      "link_id": null
    }
  ]
}
```

### GET /api/builder/export?format=yaml
`format=json` (по умолчанию) — тот же документ объектом.
```bash
curl -s -H "X-User: builder" "http://127.0.0.1:8000/api/builder/export?format=yaml"
```
Ответ `200`:

```yaml
schema_version: 2
nodes:
- name: Фотопринт
  type: system
  description: ''
  owner: Генеральный директор
  attrs: {}
  tile: null
  stage: null
  tags: {}
  kpis:
  - name: on_time_72h_share
    metric: on_time_72h_share
    compute: measured
    pinned: true
    overrides: {}
    unit: ''
  - name: orders_rhythm
    metric: orders_rhythm
    compute: measured
    pinned: false
    overrides: {}
    unit: ''
- name: Работа с клиентами
  type: function
  description: ''
  owner: Зам. по работе с клиентами
  attrs: {}
  tile: null
  stage: null
  tags: {}
  kpis:
  - name: sla_topics_share
    metric: sla_topics_share
    compute: measured
    pinned: true
    overrides: {}
    unit: ''
  - name: orders_rhythm
    metric: orders_rhythm
    compute: measured
    pinned: false
    overrides: {}
    unit: ''
- name: Маркетинг
# … ещё 949 строк
```

### POST /api/builder/import?dry_run=true
Тело — документ `org.yaml` (JSON или YAML с `Content-Type: application/x-yaml`).
Тело запроса:

```json
{
  "schema_version": 2,
  "nodes": [
    {
      "name": "Фотопринт",
      "type": "system",
      "description": "",
      "owner": "Генеральный директор",
      "attrs": {},
      "tile": null,
      "stage": null,
      "tags": {},
      "kpis": [
        {
          "name": "on_time_72h_share",
          "metric": "on_time_72h_share",
          "compute": "measured",
          "pinned": true,
          "overrides": {},
          "unit": ""
        },
        {
          "name": "orders_rhythm",
          "metric": "orders_rhythm",
          "compute": "measured",
          "pinned": false,
          "overrides": {},
          "unit": ""
        }
      ]
    },
    {
      "name": "Работа с клиентами",
      "type": "function",
      "description": "",
      "owner": "Зам. по работе с клиентами",
      "attrs": {},
      "tile": null,
      "stage": null,
      "tags": {},
      "kpis": [
        {
          "name": "sla_topics_share",
          "metric": "sla_topics_share",
          "compute": "measured",
          "pinned": true,
          "overrides": {},
          "unit": ""
        },
        {
          "name": "orders_rhythm",
          "metric": "orders_rhythm",
          "compute": "measured",
          "pinned": false,
          "overrides": {},
          "unit": ""
        }
      ]
    },
    "… ещё 23"
  ],
  "links": [
    {
      "from": "Фотопринт",
      "kpi": "on_time_72h_share",
      "to": "Работа с клиентами",
      "to_kpi": null,
      "weight": 0.25,
      "access": "inherit",
      "note": ""
    },
    {
      "from": "Фотопринт",
      "kpi": "on_time_72h_share",
      "to": "Производство",
      "to_kpi": null,
      "weight": 0.45,
      "access": "inherit",
      "note": ""
    },
    {
      "from": "Фотопринт",
      "kpi": "on_time_72h_share",
      "to": "Финансы",
      "to_kpi": null,
      "weight": 0.1,
      "access": "inherit",
      "note": ""
    },
    "… ещё 53"
  ]
}
```
```bash
curl -s -X POST -H "X-User: builder" "http://127.0.0.1:8000/api/builder/import?dry_run=true" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```
Ответ `200`:

```json
{
  "dry_run": true,
  "applied": false,
  "changes": {
    "nodes": {
      "add": [],
      "remove": [],
      "update": []
    },
    "kpis": {
      "add": [],
      "remove": [],
      "update": []
    },
    "links": {
      "add": [],
      "remove": [],
      "update": []
    },
    "changed": false
  }
}
```

## Контроль качества
Роль qc: очередь, ввод точек, флажки, личная статистика.

### GET /api/me/queue
```bash
curl -s -H "X-User: qc_otk" "http://127.0.0.1:8000/api/me/queue"
```
Ответ `200`:

```json
{
  "my_actions": [],
  "deviations_on_my_nodes": [],
  "stale_kpis": []
}
```

### GET /api/me/stats
```bash
curl -s -H "X-User: qc_otk" "http://127.0.0.1:8000/api/me/stats"
```
Ответ `200`:

```json
{
  "login": "qc_otk",
  "date": "2026-11-30",
  "week_from": "2026-11-24",
  "actions_done_today": 0,
  "actions_done_week": 0,
  "points_today": 0,
  "points_week": 0,
  "node": {
    "id": 17,
    "name": "Контролёр ОТК Иванова"
  },
  "personal_kpis": [
    {
      "node_id": 17,
      "name": "tasks_done",
      "metric": "tasks_done",
      "title": "Выполнено задач за день",
      "compute": "measured",
      "pinned": false,
      "units": "natural",
      "unit": "шт",
      "value": 42.0,
      "value_date": "2026-11-29",
      "status": "green",
      "severity": 0.0,
      "level": "ok",
      "status_source": "thresholds",
      "profile": "default",
      "thresholds": {
        "target": 40.0,
        "warn": 30.0,
        "crit": 20.0
      },
      "direction": "higher_better",
      "priority": "other",
      "tile": "team",
      "stage": null,
      "source": "hr",
      "tags": {},
      "days": 372,
      "stale": false
    },
    {
      "node_id": 17,
      "name": "personal_efficiency",
      "metric": "personal_efficiency",
      "title": "Личная эффективность (индекс)",
      "compute": "measured",
      "pinned": false,
      "units": "natural",
      "unit": "индекс",
      "value": 99.42,
      "value_date": "2026-11-29",
      "status": "green",
      "severity": 0.029,
      "level": "ok",
      "status_source": "thresholds",
      "profile": "default",
      "thresholds": {
        "target": 100.0,
        "warn": 90.0,
        "crit": 80.0
      },
      "direction": "higher_better",
      "priority": "other",
      "tile": "team",
      "stage": null,
      "source": "hr",
      "tags": {},
      "days": 372,
      "stale": false
    }
  ]
}
```

### POST /api/qc/kpi/17/tasks_done/points
Тело запроса:

```json
{
  "ts": "2026-11-30T08:30:00+03:00",
  "value": 41
}
```
```bash
curl -s -X POST -H "X-User: qc_otk" "http://127.0.0.1:8000/api/qc/kpi/17/tasks_done/points" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```
Ответ `201`:

```json
{
  "ok": true,
  "point": {
    "ts": "2026-11-30T05:30:00Z",
    "value": 41.0
  },
  "deviations_created": []
}
```

### POST /api/qc/node/17/flags
Тело запроса:

```json
{
  "ts": "2026-11-30T08:30:00+03:00",
  "kind": "info",
  "label": "Обучение по новой обложке"
}
```
```bash
curl -s -X POST -H "X-User: qc_otk" "http://127.0.0.1:8000/api/qc/node/17/flags" -H "Content-Type: application/json; charset=utf-8" -d @body.json
```
Ответ `201`:

```json
{
  "ts": "2026-11-30T05:30:00Z",
  "kind": "info",
  "values": [],
  "label": "Обучение по новой обложке",
  "ref": null
}
```

## Люди
«Подчинённые: кто чем занимается» (роль admin).

### GET /api/nodes/9/people
```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8000/api/nodes/9/people"
```
Ответ `200`:

```json
{
  "node_id": 9,
  "node_name": "Производство",
  "units": "natural",
  "people": [
    {
      "id": 14,
      "name": "Сборщик 1",
      "owner": "Зам. по производству",
      "status": "green",
      "logins": [],
      "actions": [],
      "kpis": [
        {
          "node_id": 14,
          "name": "tasks_done",
          "metric": "tasks_done",
          "title": "Выполнено задач за день",
          "compute": "measured",
          "pinned": false,
          "units": "natural",
          "unit": "шт",
          "value": 42.0,
          "value_date": "2026-11-29",
          "status": "green",
          "severity": 0.0,
          "level": "ok",
          "status_source": "thresholds",
          "profile": "default",
          "thresholds": {
            "target": 40.0,
            "warn": 30.0,
            "crit": 20.0
          },
          "direction": "higher_better",
          "priority": "other",
          "tile": "team",
          "stage": null,
          "source": "hr",
          "tags": {},
          "days": 372,
          "stale": false
        },
        {
          "node_id": 14,
          "name": "personal_efficiency",
          "metric": "personal_efficiency",
          "title": "Личная эффективность (индекс)",
          "compute": "measured",
          "pinned": false,
          "units": "natural",
          "unit": "индекс",
          "value": 99.79,
          "value_date": "2026-11-29",
          "status": "green",
          "severity": 0.0105,
          "level": "ok",
          "status_source": "thresholds",
          "profile": "default",
          "thresholds": {
            "target": 100.0,
            "warn": 90.0,
            "crit": 80.0
          },
          "direction": "higher_better",
          "priority": "other",
          "tile": "team",
          "stage": null,
          "source": "hr",
          "tags": {},
          "days": 372,
          "stale": false
        }
      ]
    },
    {
      "id": 15,
      "name": "Сборщик 2",
      "owner": "Зам. по производству",
      "status": "green",
      "logins": [],
      "actions": [],
      "kpis": [
        {
          "node_id": 15,
          "name": "tasks_done",
          "metric": "tasks_done",
          "title": "Выполнено задач за день",
          "compute": "measured",
          "pinned": false,
          "units": "natural",
          "unit": "шт",
          "value": 42.0,
          "value_date": "2026-11-29",
          "status": "green",
          "severity": 0.0,
          "level": "ok",
          "status_source": "thresholds",
          "profile": "default",
          "thresholds": {
            "target": 40.0,
            "warn": 30.0,
            "crit": 20.0
          },
          "direction": "higher_better",
          "priority": "other",
          "tile": "team",
          "stage": null,
          "source": "hr",
          "tags": {},
          "days": 372,
          "stale": false
        },
        {
          "node_id": 15,
          "name": "personal_efficiency",
          "metric": "personal_efficiency",
          "title": "Личная эффективность (индекс)",
          "compute": "measured",
          "pinned": false,
          "units": "natural",
          "unit": "индекс",
          "value": 99.28,
          "value_date": "2026-11-29",
          "status": "green",
          "severity": 0.036,
          "level": "ok",
          "status_source": "thresholds",
          "profile": "default",
          "thresholds": {
            "target": 100.0,
            "warn": 90.0,
            "crit": 80.0
          },
          "direction": "higher_better",
          "priority": "other",
          "tile": "team",
          "stage": null,
          "source": "hr",
          "tags": {},
          "days": 372,
          "stale": false
        }
      ]
    },
    "… ещё 4"
  ]
}
```

## Словарь
Единый словарь метрик (слайд 5).

### GET /api/glossary
Ответ сокращён до одной метрики.

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/glossary"
```
```json
{
  "season_months": [
    5,
    6,
    7,
    12
  ],
  "current_profile": "default",
  "allow_money": false,
  "units": [
    "relative",
    "natural"
  ],
  "metrics": {
    "defect_rate": {
      "title": "Доля брака",
      "definition": "Доля изделий, отбракованных ОТК, от выпуска за сутки",
      "formula": "rejected_items / produced_items",
      "source": "erp",
      "owner": "Зам. по производству",
      "unit": "%",
      "display": {
        "relative": "pct_of_target",
        "natural": "%"
      },
      "money_factor": null,
      "direction": "lower_better",
      "priority": "quality",
      "tile": "quality",
      "stage": 5,
      "thresholds": {
        "default": {
          "target": 2.0,
          "warn": 3.5,
          "crit": 5.0
        },
        "season": {
          "target": 2.5,
          "warn": 4.0,
          "crit": 6.0
        }
      },
      "aggregation": "mean",
      "status_window_days": null,
      "synthetic": true
    },
    "…": "ещё 37 метрик"
  }
}
```

## Журнал
Единый журнал (слайд 5): директор видит всё, admin — свою зону, остальные — свои записи.

### GET /api/audit?limit=3
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/audit?limit=3"
```
Ответ `200`:

```json
{
  "total": 16,
  "items": [
    {
      "seq": 16,
      "ts": "2026-11-30T09:00:00+03:00",
      "user": "qc_otk",
      "role": "qc",
      "action": "flag.add",
      "object_type": "node",
      "object_id": 17,
      "details": {
        "ts": "2026-11-30T05:30:00Z",
        "kind": "info",
        "values": [],
        "label": "Обучение по новой обложке",
        "ref": null
      },
      "details_hidden": false,
      "nodes": [
        17
      ]
    },
    {
      "seq": 15,
      "ts": "2026-11-30T09:00:00+03:00",
      "user": "qc_otk",
      "role": "qc",
      "action": "points.add",
      "object_type": "kpi",
      "object_id": "17/tasks_done",
      "details": {
        "count": 1,
        "ts": "2026-11-30T05:30:00Z",
        "value": 41.0
      },
      "details_hidden": false,
      "nodes": [
        17
      ]
    },
    "… ещё 1"
  ]
}
```

## Демо
Воспроизводимый сценарий для жюри (admin и builder).

### GET /api/demo/clock
```bash
curl -s -H "X-User: director" "http://127.0.0.1:8000/api/demo/clock"
```
Ответ `200`:

```json
{
  "now": "2026-11-30T09:00:00+03:00",
  "today": "2026-11-30",
  "default_now": "2026-11-23T09:00:00+03:00",
  "season_profile": "default",
  "utc_offset": "+03:00"
}
```

### POST /api/demo/reset
Пересоздаёт `data/` из `config/`: все правки выше стираются.
```bash
curl -s -X POST -H "X-User: director" "http://127.0.0.1:8000/api/demo/reset"
```
Ответ `200`:

```json
{
  "now": "2026-11-23T09:00:00+03:00",
  "nodes": 24,
  "links": 55,
  "orders": 200,
  "events": 1866,
  "deviations": [
    "DEV-0001"
  ]
}
```

### GET /health
```bash
curl -s "http://127.0.0.1:8000/health"
```
Ответ `200`:

```json
{
  "status": "ok"
}
```
