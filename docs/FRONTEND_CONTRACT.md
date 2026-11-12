# FRONTEND_CONTRACT — контракт бэкенда для фронтенда (по экранам)

Сгенерировано `python scripts/gen_frontend_contract.py` настоящими HTTP-запросами к серверу
`python run.py` после `POST /api/demo/reset`. Время стенда после сброса — `2026-11-23T09:00:00+03:00`.
Каждый ответ ниже — реальный; длинные списки сокращены (`"… ещё N"`), выборка полей помечена в тексте.
Полная схема — `docs/openapi.json` и `/docs`; все режимы — `docs/api.md`.

Стенд после сброса: узлов 24, связей 55, заказов в плане 200,
событий 1866, карточка DEV-0001. id узлов после сброса всегда одинаковы:

| узел | id |
|---|---|
| Фотопринт | 1 |
| Работа с клиентами | 2 |
| Поддержка | 5 |
| Производство | 9 |
| Сборка | 11 |
| ОТК | 12 |
| Смены | 23 |
| Финансы | 20 |
| Контролёр ОТК Иванова | 17 |

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

Один формат для всех кодов, включая 422 pydantic: `{"error": {"code", "message", "details"}}`.

**Нет X-User** `GET /api/overview` от `— без X-User` → **401**

```bash
curl -s "http://127.0.0.1:8790/api/overview"
```
```json
{
  "error": {
    "code": "unauthorized",
    "message": "Не указан пользователь: передайте заголовок X-User (список — GET /api/auth/users)",
    "details": {}
  }
}
```

**Неизвестный логин** `GET /api/overview` от `nobody` → **401**

```bash
curl -s -H "X-User: nobody" "http://127.0.0.1:8790/api/overview"
```
```json
{
  "error": {
    "code": "unknown_user",
    "message": "Пользователь 'nobody' не найден (список — GET /api/auth/users)",
    "details": {
      "login": "nobody"
    }
  }
}
```

**Чужая зона** `GET /api/nodes/11` от `head_client` → **403**

```bash
curl -s -H "X-User: head_client" "http://127.0.0.1:8790/api/nodes/11"
```
```json
{
  "error": {
    "code": "out_of_zone",
    "message": "Узел 11 вне зоны доступа",
    "details": {
      "node_id": 11
    }
  }
}
```

**Роли действие не разрешено** `POST /api/builder/nodes` от `qc_otk` → **403**

```json
// body.json
{
  "name": "x"
}
```
```bash
curl -s -X POST -H "X-User: qc_otk" -H "Content-Type: application/json; charset=utf-8" -d @body.json "http://127.0.0.1:8790/api/builder/nodes"
```
```json
{
  "error": {
    "code": "forbidden",
    "message": "Роли qc действие недоступно: structure.write",
    "details": {
      "role": "qc",
      "action": "structure.write"
    }
  }
}
```

**Нет объекта** `GET /api/deviations/DEV-9999` от `director` → **404**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/deviations/DEV-9999"
```
```json
{
  "error": {
    "code": "deviation_not_found",
    "message": "карточка 'DEV-9999' не найдена",
    "details": {}
  }
}
```

**Деньги выключены** `GET /api/overview?units=money` от `director` → **400**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/overview?units=money"
```
```json
{
  "error": {
    "code": "money_disabled",
    "message": "режим money выключен: ТЗ допускает только статусы и доли без абсолютных сумм (settings.allow_money = false). Используйте relative или natural",
    "details": {}
  }
}
```

**Недопустимый переход** `PATCH /api/deviations/DEV-0001` от `director` → **409**

```json
// body.json
{
  "status": "verified"
}
```
```bash
curl -s -X PATCH -H "X-User: director" -H "Content-Type: application/json; charset=utf-8" -d @body.json "http://127.0.0.1:8790/api/deviations/DEV-0001"
```
```json
{
  "error": {
    "code": "invalid_transition",
    "message": "переход open → verified недопустим (verified и failed ставит только перепроверка)",
    "details": {
      "from": "open",
      "to": "verified",
      "allowed": [
        "assigned",
        "closed",
        "… ещё 1"
      ]
    }
  }
}
```

**Ошибка валидации (422 pydantic)** `GET /api/orders?stage=9` от `director` → **422**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/orders?stage=9"
```
```json
{
  "error": {
    "code": "validation_error",
    "message": "ошибка валидации запроса: query.stage: Input should be less than or equal to 8",
    "details": {
      "errors": [
        {
          "loc": [
            "query",
            "stage"
          ],
          "msg": "Input should be less than or equal to 8",
          "type": "less_than_equal"
        }
      ]
    }
  }
}
```

## 1. Выбор пользователя / вход

Эндпоинты: `GET /api/auth/users` (без `X-User`) → список для выбора; `GET /api/me` → профиль, права, зона.
Выбранный логин фронтенд хранит сам и подставляет в `X-User` каждого запроса.

`GET /api/auth/users` от `— без X-User` → **200**

```bash
curl -s "http://127.0.0.1:8790/api/auth/users"
```
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

`GET /api/me` от `head_prod` → **200**

```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8790/api/me"
```
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
    "deviations.manage",
    "deviations.recheck",
    "flags.write",
    "people.read",
    "points.write"
  ],
  "sees_everything": false,
  "zone": [
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19
  ]
}
```

| логин | роль | узлов в зоне | sees_everything | permissions |
|---|---|---|---|---|
| director | admin | 24 | True | demo.control, deviations.done, deviations.manage, deviations.recheck, flags.write, people.read, points.write |
| head_client | admin | 7 | False | demo.control, deviations.done, deviations.manage, deviations.recheck, flags.write, people.read, points.write |
| head_prod | admin | 11 | False | demo.control, deviations.done, deviations.manage, deviations.recheck, flags.write, people.read, points.write |
| qc_otk | qc | 4 | False | deviations.done, flags.write, points.write |
| builder | builder | 24 | False | config.io, demo.control, glossary.write, structure.write |


## 2. Главный экран (8 плиток)

Эндпоинт: `GET /api/overview?units=natural|relative`. Всегда 8 плиток в порядке `order`
(срок → качество → себестоимость). Плитка: худший статус KPI зоны, `main_kpi` (значение, `delta_week`,
`trend`, `trend_quality`), `forecast_risk` (ближайшее пересечение порога на 14 суток), открытые отклонения;
`portfolio` — сводка решений.

**Пустое состояние:** если в зоне нет KPI плитки — `status: "unknown"`, `kpis: 0`, `main_kpi: null`,
`forecast_risk.at_risk: false`. Плитку всё равно рисовать (8 штук всегда).

**Различия по ролям** (настоящие ответы):

`GET /api/overview` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/overview"
```
```json
{
  "now": "2026-11-23T09:00:00+03:00",
  "user": "director",
  "units": "natural",
  "zone_nodes": 24,
  "tiles": [
    {
      "key": "quality",
      "title": "Качество",
      "stage": null,
      "priority": "quality",
      "order": 5,
      "status": "red",
      "kpis": 4,
      "kpi_statuses": {
        "red": 2,
        "yellow": 0,
        "green": 2,
        "unknown": 0
      },
      "main_kpi": {
        "node_id": 5,
        "node_name": "Поддержка",
        "kpi": "defect_tickets_share",
        "title": "Доля обращений по браку",
        "value": 9.0,
        "value_date": "2026-11-22",
        "unit": "%",
        "status": "red",
        "severity": 1.0,
        "delta_week": 3.5,
        "trend": "up",
        "trend_quality": "worsening"
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
      "open_deviations": 1,
      "deviation_ids": [
        "DEV-0001"
      ]
    },
    "… ещё 7 плиток той же формы"
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

| логин | узлов в зоне | плитка: статус / число KPI | карточек в портфеле |
|---|---|---|---|
| director | 24 | orders: green/5; moderation: green/2; production: green/7; delivery: green/4; quality: red/4; support: green/7; clients: green/4; team: yellow/21 | 1 |
| head_client | 7 | orders: green/3; moderation: green/2; production: unknown/0; delivery: green/2; quality: red/1; support: green/7; clients: green/4; team: unknown/0 | 1 |
| head_prod | 11 | orders: unknown/0; moderation: unknown/0; production: green/6; delivery: green/2; quality: red/3; support: unknown/0; clients: unknown/0; team: green/12 | 1 |
| qc_otk | 4 | orders: unknown/0; moderation: unknown/0; production: unknown/0; delivery: unknown/0; quality: green/2; support: unknown/0; clients: unknown/0; team: green/6 | 0 |


**Пустые плитки у qc_otk** `GET /api/overview` от `qc_otk` → **200**

```bash
curl -s -H "X-User: qc_otk" "http://127.0.0.1:8790/api/overview"
```
```json
[
  {
    "key": "orders",
    "title": "Заказы · ритм",
    "stage": 3,
    "priority": "time",
    "order": 1,
    "status": "unknown",
    "kpis": 0,
    "kpi_statuses": {
      "red": 0,
      "yellow": 0,
      "green": 0,
      "unknown": 0
    },
    "main_kpi": null,
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
  }
]
```

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

`GET /api/graph` от `head_prod` → **200**

```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8790/api/graph"
```
```json
{
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
    "… ещё 2"
  ],
  "links": [
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
      "boundary": "upstream",
      "contribution": null,
      "share": null
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
      "boundary": "upstream",
      "contribution": null,
      "share": null
    },
    "… ещё 1"
  ],
  "units": "natural",
  "roots": [
    9
  ],
  "zone_size": 11
}
```

| логин | узлов зоны | серые сверху (upstream) | серые снизу (downstream) | связей |
|---|---|---|---|---|
| director | 24 | — | — | 55 |
| head_client | 7 | Фотопринт | Сборка, ОТК, Склад и отгрузка | 18 |
| head_prod | 11 | Фотопринт, Поддержка | Смены | 28 |
| qc_otk | 4 | Поддержка, Производство | — | 9 |


`GET /api/analysis/contributions?node=5&kpi=defect_tickets_share` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/analysis/contributions?node=5&kpi=defect_tickets_share"
```
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

**Та же строка вкладов у head_client (цели вне зоны)** `GET /api/analysis/contributions?node=5&kpi=defect_tickets_share` от `head_client` → **200**

```bash
curl -s -H "X-User: head_client" "http://127.0.0.1:8790/api/analysis/contributions?node=5&kpi=defect_tickets_share"
```
```json
{
  "node_id": 5,
  "node_name": "Поддержка",
  "kpi": "defect_tickets_share",
  "title": "Доля обращений по браку",
  "status": "red",
  "severity": 1.0,
  "total_contribution": 0.0,
  "hidden_links": 3,
  "summary": "",
  "links": [
    {
      "link_id": "L-0018",
      "to_node": 11,
      "to_node_name": "Сборка",
      "owner": "Зам. по производству",
      "to_kpi": null,
      "target_kpi": null,
      "weight": 0.6,
      "access": "none",
      "status": "red",
      "visible": false,
      "severity": null,
      "contribution": null,
      "share": null
    },
    {
      "link_id": "L-0019",
      "to_node": 12,
      "to_node_name": "ОТК",
      "owner": "Зам. по производству",
      "to_kpi": null,
      "target_kpi": null,
      "weight": 0.25,
      "access": "none",
      "status": "green",
      "visible": false,
      "severity": null,
      "contribution": null,
      "share": null
    },
    {
      "link_id": "L-0020",
      "to_node": 13,
      "to_node_name": "Склад и отгрузка",
      "owner": "Зам. по производству",
      "to_kpi": null,
      "target_kpi": null,
      "weight": 0.15,
      "access": "none",
      "status": "green",
      "visible": false,
      "severity": null,
      "contribution": null,
      "share": null
    }
  ]
}
```

## 4. Карточка узла: KPI, ряды, аннотации, прогноз

Эндпоинты: `GET /api/nodes/{id}` (узел и связи; открытие пишется в журнал),
`GET /api/nodes/{id}/kpis?units=`, `GET /api/kpi/{node}/{kpi}?from=&to=&agg=raw|day&units=`
(точки и флажки; аннотации — флажки `kind: "annotation"`, `ref` = id события),
`GET /api/kpi/{node}/{kpi}/forecast?horizon=7|14|21`, `GET /api/events?type=annotation&node=`.

**Пустое состояние:** период без точек — `points: []`; KPI без данных — `value: null`, `status: "unknown"`,
`stale: true`; прогноз при меньше 7 сутках — `enough_data: false`, `points: []`.
Узел вне зоны — `403 out_of_zone` (кликабельность смотрите в графе заранее).

`GET /api/nodes/11` от `head_prod` → **200**

```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8790/api/nodes/11"
```
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

`GET /api/nodes/11/kpis?units=natural` от `head_prod` → **200**

```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8790/api/nodes/11/kpis?units=natural"
```
```json
[
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
    "stale": false
  },
  "… ещё 1"
]
```

`GET /api/kpi/11/defect_rate?from=2026-11-09T00%3A00%3A00%2B03%3A00&agg=day` от `head_prod` → **200**

```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8790/api/kpi/11/defect_rate?from=2026-11-09T00%3A00%3A00%2B03%3A00&agg=day"
```
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
      "ts": "2026-11-19T21:00:00Z",
      "value": 5.52
    },
    {
      "ts": "2026-11-20T21:00:00Z",
      "value": 5.96
    },
    {
      "ts": "2026-11-21T21:00:00Z",
      "value": 6.4
    }
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

`GET /api/kpi/11/defect_rate/forecast?horizon=7` от `head_prod` → **200**

```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8790/api/kpi/11/defect_rate/forecast?horizon=7"
```
```json
{
  "node_id": 11,
  "kpi": "defect_rate",
  "title": "Доля брака",
  "method": "linear_trend+weekday_seasonality",
  "method_text": "Линейный тренд (наименьшие квадраты) по последним 28 суткам плюс средние отклонения по дням недели; коридор ±1σ остатков. Простая модель без внешних данных.",
  "horizon": 7,
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
    "… ещё 5"
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

`GET /api/events?type=annotation` от `head_prod` → **200**

```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8790/api/events?type=annotation"
```
```json
{
  "total": 3,
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
      "event_id": "E-000115",
      "ts": "2026-10-14T00:00:00+03:00",
      "source": "erp",
      "type": "annotation",
      "order_id": null,
      "customer_id": null,
      "node_id": null,
      "stage": null,
      "payload": {
        "label": "Смена перевозчика: Boxberry → Яндекс Доставка",
        "targets": [
          {
            "node_id": 13,
            "node": "Склад и отгрузка",
            "kpi": "pay_to_carrier_time"
          }
        ],
        "dims": {}
      },
      "synthetic": true
    },
    "… ещё 1"
  ]
}
```

| логин | GET /api/nodes/11 (Сборка) | GET /api/kpi/11/defect_rate |
|---|---|---|
| director | 200 | 200 |
| head_client | 403 `out_of_zone` | 403 `out_of_zone` |
| head_prod | 200 | 200 |
| qc_otk | 403 `out_of_zone` | 403 `out_of_zone` |


**Пустой ряд (период без данных)** `GET /api/kpi/17/tasks_done?from=2030-01-01T00%3A00%3A00%2B03%3A00` от `qc_otk` → **200**

```bash
curl -s -H "X-User: qc_otk" "http://127.0.0.1:8790/api/kpi/17/tasks_done?from=2030-01-01T00%3A00%3A00%2B03%3A00"
```
```json
{
  "node_id": 17,
  "name": "tasks_done",
  "metric": "tasks_done",
  "title": "Выполнено задач за день",
  "compute": "measured",
  "pinned": false,
  "units": "natural",
  "unit": "шт",
  "value": 43.0,
  "value_date": "2026-11-22",
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
  "days": 365,
  "stale": false,
  "agg": "raw",
  "points": [],
  "flags": []
}
```

## 5. Карточка отклонения: сигнал → контекст → причина → действие → перепроверка

Эндпоинты: `GET /api/deviations?status=&node=&owner=` (портфель + `summary`), `GET /api/deviations/{id}`,
`GET …/suggest` (1–3 шаблона действия), `GET …/orders` (затронутые заказы), `GET /api/analysis/trace`,
`PATCH /api/deviations/{id}` (статус, действие, гипотеза; admin), `POST /api/admin/deviations/{id}/recheck`
(admin), `POST /api/qc/deviations/{id}/done` (исполнитель).

Поля карточки по шагам цепочки: `signal` (сигнал) → `context` (плитка, этап, профиль сезона, `dims`, окно)
→ `cause` (снимок trace, `root`, `confidence`) → `action` (текст, `owner_login`/`owner_node`, `due_at`)
→ `rechecks[]` (каждая перепроверка добавляется) → `status`. `current` — состояние KPI сейчас.

Переходы: `open → assigned | escalated | closed`; `assigned → assigned | in_progress | done | escalated | closed`;
`in_progress → assigned | done | escalated | closed`; `done → in_progress | closed`; `failed → assigned | escalated | closed`;
`escalated → assigned | closed`; `verified → closed`. `verified`/`failed` ставит только перепроверка.
Неверный переход — `409 invalid_transition`. Перепроверка раньше 3 суток — `result: "pending"`, статус не меняется.

**Видимость:** карточку видит тот, у кого в зоне узел сигнала, узел первопричины или кто исполнитель.
Шаги trace и цифры вне зоны — `null`.

`GET /api/deviations/DEV-0001` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/deviations/DEV-0001"
```
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
      "ORD-000122",
      "… ещё 5"
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

**Та же карточка у head_client (первопричина вне зоны)** `GET /api/deviations/DEV-0001` от `head_client` → **200**

```bash
curl -s -H "X-User: head_client" "http://127.0.0.1:8790/api/deviations/DEV-0001"
```
```json
{
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
          "to_kpi": null,
          "target_kpi": null,
          "weight": 0.6,
          "access": "none",
          "status": "red",
          "visible": false,
          "severity": null,
          "contribution": null,
          "share": null
        },
        "alternatives": [
          {
            "link_id": "L-0019",
            "to_node": 12,
            "to_node_name": "ОТК",
            "owner": "Зам. по производству",
            "to_kpi": null,
            "target_kpi": null,
            "weight": 0.25,
            "access": "none",
            "status": "green",
            "visible": false,
            "severity": null,
            "contribution": null,
            "share": null
          }
        ]
      },
      {
        "depth": 1,
        "node_id": 11,
        "node_name": "Сборка",
        "node_type": "department",
        "owner": "Зам. по производству",
        "visible": false,
        "kpi": null,
        "title": null,
        "status": "red",
        "severity": null,
        "value": null,
        "value_date": null,
        "unit": null,
        "via": {
          "link_id": "L-0018",
          "to_node": 11,
          "to_node_name": "Сборка",
          "owner": "Зам. по производству",
          "to_kpi": null,
          "target_kpi": null,
          "weight": 0.6,
          "access": "none",
          "status": "red",
          "visible": false,
          "severity": null,
          "contribution": null,
          "share": null
        },
        "chosen": null,
        "alternatives": []
      }
    ],
    "root": {
      "node_id": 11,
      "node_name": "Сборка",
      "kpi": null
    },
    "stopped_reason": "below_threshold",
    "hypothesis": "",
    "confidence": "high",
    "confidence_basis": null,
    "set_by": null
  },
  "signal": {
    "ts": "2026-11-23T09:00:00+03:00",
    "day": "2026-11-22",
    "value": 9.0,
    "status": "red",
    "level": "crit",
    "threshold": 8.0,
    "detected_by": "auto"
  },
  "affected_orders": {
    "count": 8,
    "sample": [
      "ORD-000119",
      "ORD-000121",
      "ORD-000122",
      "… ещё 5"
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
}
```

| логин | GET /api/deviations/DEV-0001 | портфель: карточек | затронутых заказов |
|---|---|---|---|
| director | 200 | 1 | 8 |
| head_client | 200 | 1 | 8 |
| head_prod | 200 | 1 | 8 |
| qc_otk | 403 `out_of_zone` | 0 | 403 |


`GET /api/deviations/DEV-0001/suggest` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/deviations/DEV-0001/suggest"
```
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
    {
      "id": "PB-GENERIC",
      "title": "Разобрать причину с владельцем узла",
      "action": "Назначить ответственного, разобрать причину отклонения с владельцем узла первопричины и договориться о мере с проверяемым результатом",
      "owner_hint": null,
      "due_days": 3,
      "due_at": "2026-11-26T09:00:00+03:00",
      "recheck_window_days": 7,
      "score": 0
    }
  ]
}
```

`GET /api/deviations/DEV-0001/orders` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/deviations/DEV-0001/orders"
```
```json
{
  "count": 8,
  "sample": [
    "ORD-000119",
    "ORD-000121",
    "ORD-000122",
    "ORD-000130",
    "ORD-000132",
    "… ещё 3"
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

**Пустой фильтр портфеля** `GET /api/deviations?status=verified` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/deviations?status=verified"
```
```json
{
  "items": [],
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

`GET /api/analysis/trace?node=5&kpi=defect_tickets_share` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/analysis/trace?node=5&kpi=defect_tickets_share"
```
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

## 6. Поток заказов (8 этапов × 4 поля)

Эндпоинты: `GET /api/flow/summary`, `GET /api/orders?stage=&status=&product_line=&brand=&segment=&customer_id=&issue=&from=&to=&limit=&offset=`,
`GET /api/orders/{id}`, источники — `GET /api/sources`, `GET /api/events`.

У каждого этапа всегда есть 4 поля: `event_id`, `status`, `owner`, `result_check`. Статусы этапа:
`pending` (не начат: `event_id: null`, времени нет), `in_progress` (итог проверки `null`), `done`, `late`, `defect`.
Заказ виден, если хотя бы один этап принадлежит узлу зоны; чужой этап — `visible: false`, без события,
`result_check: null`, времени и проблемы. В `/flow/summary` чужой этап — с `null` вместо цифр.

`GET /api/flow/summary` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/flow/summary"
```
```json
{
  "now": "2026-11-23T09:00:00+03:00",
  "orders_total": 149,
  "in_progress": 14,
  "completed": 135,
  "stages": [
    {
      "stage": 5,
      "name": "Производство",
      "focus": "очередь / готовность",
      "source": "erp",
      "owner": {
        "node_id": 11,
        "node_name": "Сборка",
        "login": null
      },
      "norm_hours": 24.0,
      "criterion": "изготовлено за 24 ч и принято ОТК",
      "visible": true,
      "orders": 149,
      "pending": 1,
      "in_work": 2,
      "overdue": 0,
      "done": 115,
      "late": 20,
      "defect": 11,
      "checked": 146,
      "passed_share": 0.7877,
      "problems": 31
    },
    {
      "stage": 6,
      "name": "Доставка",
      "focus": "маршрут / срок",
      "source": "erp",
      "owner": {
        "node_id": 13,
        "node_name": "Склад и отгрузка",
        "login": null
      },
      "norm_hours": 72.0,
      "criterion": "передан в ТК и доставлен в срок",
      "visible": true,
      "orders": 149,
      "pending": 3,
      "in_work": 5,
      "overdue": 0,
      "done": 125,
      "late": 16,
      "defect": 0,
      "checked": 141,
      "passed_share": 0.8865,
      "problems": 16
    }
  ],
  "bottleneck": {
    "stage": 6,
    "name": "Доставка",
    "overdue": 0,
    "in_work": 5
  },
  "synthetic": true
}
```

`GET /api/orders?product_line=%D0%92%D1%8B%D0%BF%D1%83%D1%81%D0%BA%D0%BD%D1%8B%D0%B5+%D0%B0%D0%BB%D1%8C%D0%B1%D0%BE%D0%BC%D1%8B&stage=5&status=defect&limit=2` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/orders?product_line=%D0%92%D1%8B%D0%BF%D1%83%D1%81%D0%BA%D0%BD%D1%8B%D0%B5+%D0%B0%D0%BB%D1%8C%D0%B1%D0%BE%D0%BC%D1%8B&stage=5&status=defect&limit=2"
```
```json
{
  "total": 9,
  "items": [
    {
      "order_id": "ORD-000142",
      "customer_id": "C-0011",
      "product_line": "Выпускные альбомы",
      "brand": "ФФ РФ",
      "segment": "B2B",
      "created_at": "2026-11-18T20:22:00+03:00",
      "status": "in_progress",
      "current_stage": 8,
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
        {
          "stage": 3,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 4,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 5,
          "status": "defect",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 6,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 7,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 8,
          "status": "in_progress",
          "overdue": false,
          "visible": true
        }
      ],
      "prev_order_id": null,
      "next_order_id": "ORD-000147",
      "synthetic": true
    },
    {
      "order_id": "ORD-000140",
      "customer_id": "C-0012",
      "product_line": "Выпускные альбомы",
      "brand": "ФФ РФ",
      "segment": "B2B",
      "created_at": "2026-11-18T14:06:00+03:00",
      "status": "in_progress",
      "current_stage": 7,
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
        {
          "stage": 3,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 4,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 5,
          "status": "defect",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 6,
          "status": "done",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 7,
          "status": "in_progress",
          "overdue": false,
          "visible": true
        },
        {
          "stage": 8,
          "status": "pending",
          "overdue": false,
          "visible": true
        }
      ],
      "prev_order_id": "ORD-000113",
      "next_order_id": "ORD-000149",
      "synthetic": true
    }
  ]
}
```

`GET /api/orders/ORD-000142` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/orders/ORD-000142"
```
```json
{
  "order_id": "ORD-000142",
  "customer_id": "C-0011",
  "product_line": "Выпускные альбомы",
  "brand": "ФФ РФ",
  "segment": "B2B",
  "created_at": "2026-11-18T20:22:00+03:00",
  "status": "in_progress",
  "current_stage": 8,
  "stages": [
    {
      "stage": 5,
      "name": "Производство",
      "source": "erp",
      "event_id": "E-001310",
      "status": "defect",
      "owner": {
        "node_id": 11,
        "node_name": "Сборка",
        "login": null
      },
      "result_check": {
        "criterion": "изготовлено за 24 ч и принято ОТК",
        "passed": false,
        "checked_at": "2026-11-21T01:50:00+03:00"
      },
      "issue": "брак",
      "started_at": "2026-11-20T04:22:00+03:00",
      "due_at": "2026-11-21T04:22:00+03:00",
      "finished_at": "2026-11-21T01:50:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    },
    {
      "stage": 6,
      "name": "Доставка",
      "source": "erp",
      "event_id": "E-001323",
      "status": "done",
      "owner": {
        "node_id": 13,
        "node_name": "Склад и отгрузка",
        "login": null
      },
      "result_check": {
        "criterion": "передан в ТК и доставлен в срок",
        "passed": true,
        "checked_at": "2026-11-22T01:02:00+03:00"
      },
      "issue": null,
      "started_at": "2026-11-21T02:46:00+03:00",
      "due_at": "2026-11-24T02:46:00+03:00",
      "finished_at": "2026-11-22T01:02:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": false
    },
    {
      "stage": 7,
      "name": "Поддержка",
      "source": "support",
      "event_id": "E-001349",
      "status": "done",
      "owner": {
        "node_id": 5,
        "node_name": "Поддержка",
        "login": null
      },
      "result_check": {
        "criterion": "обращений нет или обращение решено в SLA",
        "passed": true,
        "checked_at": "2026-11-22T09:12:00+03:00"
      },
      "issue": "обращение по браку",
      "started_at": "2026-11-22T01:13:00+03:00",
      "due_at": "2026-11-23T01:13:00+03:00",
      "finished_at": "2026-11-22T09:12:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": true
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
  "prev_order_id": null,
  "next_order_id": "ORD-000147",
  "synthetic": true,
  "schema_version": 1
}
```

**Тот же заказ у head_client** `GET /api/orders/ORD-000142` от `head_client` → **200**

```bash
curl -s -H "X-User: head_client" "http://127.0.0.1:8790/api/orders/ORD-000142"
```
```json
{
  "order_id": "ORD-000142",
  "customer_id": "C-0011",
  "product_line": "Выпускные альбомы",
  "brand": "ФФ РФ",
  "segment": "B2B",
  "created_at": "2026-11-18T20:22:00+03:00",
  "status": "in_progress",
  "current_stage": 8,
  "stages": [
    {
      "stage": 5,
      "name": "Производство",
      "source": "erp",
      "event_id": null,
      "status": "defect",
      "owner": {
        "node_id": 11,
        "node_name": "Сборка",
        "login": null
      },
      "result_check": null,
      "issue": null,
      "started_at": null,
      "due_at": null,
      "finished_at": null,
      "overdue": null,
      "visible": false
    },
    {
      "stage": 6,
      "name": "Доставка",
      "source": "erp",
      "event_id": null,
      "status": "done",
      "owner": {
        "node_id": 13,
        "node_name": "Склад и отгрузка",
        "login": null
      },
      "result_check": null,
      "issue": null,
      "started_at": null,
      "due_at": null,
      "finished_at": null,
      "overdue": null,
      "visible": false
    },
    {
      "stage": 7,
      "name": "Поддержка",
      "source": "support",
      "event_id": "E-001349",
      "status": "done",
      "owner": {
        "node_id": 5,
        "node_name": "Поддержка",
        "login": null
      },
      "result_check": {
        "criterion": "обращений нет или обращение решено в SLA",
        "passed": true,
        "checked_at": "2026-11-22T09:12:00+03:00"
      },
      "issue": "обращение по браку",
      "started_at": "2026-11-22T01:13:00+03:00",
      "due_at": "2026-11-23T01:13:00+03:00",
      "finished_at": "2026-11-22T09:12:00+03:00",
      "overdue": false,
      "visible": true,
      "issue_on_start": true
    }
  ],
  "issues": [
    {
      "stage": 7,
      "issue": "обращение по браку"
    }
  ],
  "prev_order_id": null,
  "next_order_id": "ORD-000147",
  "synthetic": true,
  "schema_version": 1
}
```

| логин | заказов в списке | этапы с цифрами в /flow/summary | GET /api/orders/ORD-000142 |
|---|---|---|---|
| director | 149 | 1, 2, 3, 4, 5, 6, 7, 8 | 200 |
| head_client | 149 | 1, 2, 3, 4, 7, 8 | 200 |
| head_prod | 149 | 5, 6 | 200 |
| qc_otk | 0 | — | 403 `out_of_zone` |


**Пустой список (у ОТК нет своих этапов)** `GET /api/orders` от `qc_otk` → **200**

```bash
curl -s -H "X-User: qc_otk" "http://127.0.0.1:8790/api/orders"
```
```json
{
  "total": 0,
  "items": []
}
```

`GET /api/sources` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/sources"
```
```json
[
  {
    "key": "crm",
    "title": "CRM",
    "system": "Битрикс24",
    "provides": [
      "клиенты",
      "сделки",
      "коммуникации",
      "… ещё 1"
    ],
    "mode": "mock",
    "read_only": true,
    "connector": "в проде — коннектор только на чтение",
    "note": "",
    "events": 440,
    "last_event_at": "2026-11-23T03:42:00+03:00",
    "event_types": [
      "annotation",
      "crm.claim",
      "crm.customer_context",
      "… ещё 2"
    ],
    "metrics": [
      "leads",
      "orders_rhythm",
      "repeat_customers_share"
    ],
    "kpis_in_zone": 8
  },
  "… ещё 4 источника"
]
```

## 7. Подчинённые

Эндпоинты: `GET /api/nodes/{id}/people` (admin; узлы `person` в зоне ниже узла, их действия и личные KPI);
для qc — `GET /api/me/queue` и `GET /api/me/stats`.

`GET /api/nodes/9/people` от `head_prod` → **200**

```bash
curl -s -H "X-User: head_prod" "http://127.0.0.1:8790/api/nodes/9/people"
```
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
          "value": 43.0,
          "value_date": "2026-11-22",
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
          "days": 365,
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
          "value": 100.61,
          "value_date": "2026-11-22",
          "status": "green",
          "severity": 0.0,
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
          "days": 365,
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
          "value": 43.0,
          "value_date": "2026-11-22",
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
          "days": 365,
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
          "value": 100.48,
          "value_date": "2026-11-22",
          "status": "green",
          "severity": 0.0,
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
          "days": 365,
          "stale": false
        }
      ]
    },
    "… ещё 4"
  ]
}
```

| логин | GET /api/nodes/9/people |
|---|---|
| director | 200 |
| head_client | 403 `out_of_zone` |
| head_prod | 200 |
| qc_otk | 403 `forbidden` |


**Пустое состояние (у «Финансов» нет сотрудников)** `GET /api/nodes/20/people` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/nodes/20/people"
```
```json
{
  "node_id": 20,
  "node_name": "Финансы",
  "units": "natural",
  "people": []
}
```

`GET /api/me/queue` от `qc_otk` → **200**

```bash
curl -s -H "X-User: qc_otk" "http://127.0.0.1:8790/api/me/queue"
```
```json
{
  "my_actions": [],
  "deviations_on_my_nodes": [],
  "stale_kpis": []
}
```

`GET /api/me/stats` от `qc_otk` → **200**

```bash
curl -s -H "X-User: qc_otk" "http://127.0.0.1:8790/api/me/stats"
```
```json
{
  "login": "qc_otk",
  "date": "2026-11-23",
  "week_from": "2026-11-17",
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
      "value": 43.0,
      "value_date": "2026-11-22",
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
      "days": 365,
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
      "value": 100.33,
      "value_date": "2026-11-22",
      "status": "green",
      "severity": 0.0,
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
      "days": 365,
      "stale": false
    }
  ]
}
```

## 8. Словарь

Эндпоинт: `GET /api/glossary` — одинаков для всех ролей. Правка — `POST/PATCH /api/builder/glossary` (builder).

`GET /api/glossary` от `qc_otk` → **200**

```bash
curl -s -H "X-User: qc_otk" "http://127.0.0.1:8790/api/glossary"
```
```json
{
  "season_months": [
    5,
    6,
    "… ещё 2"
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
    "…": "ещё 36 метрик"
  }
}
```

## 9. Журнал

Эндпоинт: `GET /api/audit?user=&action=&object_type=&object_id=&node=&limit=&offset=` — новые сверху.
Директор видит всё, admin — записи о своей зоне и свои, qc и builder — только свои. У чужих записей,
задевающих узлы вне зоны, `details: {}` и `details_hidden: true`.
Примеры сняты после шагов демо-сценария (раздел «Демо-сценарий»).

`GET /api/audit?limit=3` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/audit?limit=3"
```
```json
{
  "total": 8,
  "items": [
    {
      "seq": 8,
      "ts": "2026-11-30T09:00:00+03:00",
      "user": "head_client",
      "role": "admin",
      "action": "deviation.open",
      "object_type": "deviation",
      "object_id": "DEV-0001",
      "details": {
        "status": "verified"
      },
      "details_hidden": false,
      "nodes": [
        5,
        11
      ]
    },
    {
      "seq": 7,
      "ts": "2026-11-30T09:00:00+03:00",
      "user": "director",
      "role": "admin",
      "action": "deviation.recheck",
      "object_type": "deviation",
      "object_id": "DEV-0001",
      "details": {
        "n": 2,
        "result": "passed",
        "passed": true,
        "baseline": 7.7825,
        "after": 4.436717
      },
      "details_hidden": false,
      "nodes": [
        5,
        11
      ]
    },
    {
      "seq": 6,
      "ts": "2026-11-30T09:00:00+03:00",
      "user": "director",
      "role": "admin",
      "action": "demo.advance",
      "object_type": "demo",
      "object_id": null,
      "details": {
        "now": "2026-11-30T09:00:00+03:00",
        "days": 7,
        "closed_days": [
          "2026-11-23",
          "2026-11-24",
          "2026-11-25",
          "… ещё 4"
        ],
        "points_written": 399,
        "branches": {
          "ОТК/defect_escape_rate": "with_action",
          "Поддержка/defect_tickets_share": "with_action",
          "Сборка/defect_rate": "with_action",
          "Смены/shift_load": "with_action"
        },
        "deviations_created": []
      },
      "details_hidden": false,
      "nodes": []
    }
  ]
}
```

**head_client: своя зона** `GET /api/audit?limit=3` от `head_client` → **200**

```bash
curl -s -H "X-User: head_client" "http://127.0.0.1:8790/api/audit?limit=3"
```
```json
{
  "total": 6,
  "items": [
    {
      "seq": 8,
      "ts": "2026-11-30T09:00:00+03:00",
      "user": "head_client",
      "role": "admin",
      "action": "deviation.open",
      "object_type": "deviation",
      "object_id": "DEV-0001",
      "details": {
        "status": "verified"
      },
      "details_hidden": false,
      "nodes": [
        5,
        11
      ]
    },
    {
      "seq": 7,
      "ts": "2026-11-30T09:00:00+03:00",
      "user": "director",
      "role": "admin",
      "action": "deviation.recheck",
      "object_type": "deviation",
      "object_id": "DEV-0001",
      "details": {},
      "details_hidden": true,
      "nodes": [
        5,
        11
      ]
    },
    {
      "seq": 5,
      "ts": "2026-11-23T09:00:00+03:00",
      "user": "director",
      "role": "admin",
      "action": "deviation.recheck",
      "object_type": "deviation",
      "object_id": "DEV-0001",
      "details": {},
      "details_hidden": true,
      "nodes": [
        5,
        11
      ]
    }
  ]
}
```

**qc_otk: только свои записи (пока пусто)** `GET /api/audit` от `qc_otk` → **200**

```bash
curl -s -H "X-User: qc_otk" "http://127.0.0.1:8790/api/audit"
```
```json
{
  "total": 0,
  "items": []
}
```

| логин | записей видно (total) |
|---|---|
| director | 8 |
| head_client | 6 |
| head_prod | 6 |
| qc_otk | 0 |
| builder | 0 |


## 10. Конструктор (builder)

Эндпоинты: `POST/PATCH/DELETE /api/builder/nodes…`, `POST/PATCH/DELETE /api/builder/nodes/{id}/kpis…`,
`POST/PATCH/DELETE /api/builder/links…`, `PUT /api/builder/kpis/{node}/{kpi}/weights?normalize=`,
`POST/PATCH /api/builder/glossary`, `GET /api/builder/validate`, `GET /api/builder/export?format=json|yaml`,
`POST /api/builder/import?dry_run=true`. Ответ на правку связи — `{link, kpi_links}`: перерисовывайте веса
всех связей KPI из `kpi_links` (они нормируются автоматически). Другим ролям всё это — `403 forbidden`.

`GET /api/builder/validate` от `builder` → **200**

```bash
curl -s -H "X-User: builder" "http://127.0.0.1:8790/api/builder/validate"
```
```json
{
  "ok": true,
  "errors": 0,
  "warnings": 0,
  "problems": []
}
```

`POST /api/builder/glossary` от `builder` → **201**

```json
// body.json
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
curl -s -X POST -H "X-User: builder" -H "Content-Type: application/json; charset=utf-8" -d @body.json "http://127.0.0.1:8790/api/builder/glossary"
```
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

`POST /api/builder/nodes` от `builder` → **201**

```json
// body.json
{
  "name": "Закупки",
  "type": "department",
  "owner": "Зам. по производству"
}
```
```bash
curl -s -X POST -H "X-User: builder" -H "Content-Type: application/json; charset=utf-8" -d @body.json "http://127.0.0.1:8790/api/builder/nodes"
```
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

`POST /api/builder/nodes/25/kpis` от `builder` → **201**

```json
// body.json
{
  "name": "incoming_defect_share",
  "metric": "incoming_defect_share",
  "pinned": true
}
```
```bash
curl -s -X POST -H "X-User: builder" -H "Content-Type: application/json; charset=utf-8" -d @body.json "http://127.0.0.1:8790/api/builder/nodes/25/kpis"
```
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

`POST /api/builder/links` от `builder` → **201**

```json
// body.json
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
curl -s -X POST -H "X-User: builder" -H "Content-Type: application/json; charset=utf-8" -d @body.json "http://127.0.0.1:8790/api/builder/links"
```
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
    {
      "id": "L-0025",
      "from_node": 11,
      "from_kpi": "defect_rate",
      "to_node": 23,
      "to_kpi": "shift_load",
      "weight": 0.2,
      "access": "none",
      "note": "Перегрузка смены повышает брак",
      "flags": [],
      "created_by": "seed",
      "created_at": "2026-11-23T09:00:00+03:00"
    },
    {
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
    }
  ]
}
```

**validate после: KPI без данных — предупреждение** `GET /api/builder/validate` от `builder` → **200**

```bash
curl -s -H "X-User: builder" "http://127.0.0.1:8790/api/builder/validate"
```
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

`GET /api/builder/export?format=yaml` от `builder` → **200**

```bash
curl -s -H "X-User: builder" "http://127.0.0.1:8790/api/builder/export?format=yaml"
```
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
# … ещё 964 строк
```

**import dry_run: документ из одного узла** `POST /api/builder/import?dry_run=true` от `builder` → **200**

```json
// body.json
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
    }
  ],
  "links": []
}
```
```bash
curl -s -X POST -H "X-User: builder" -H "Content-Type: application/json; charset=utf-8" -d @body.json "http://127.0.0.1:8790/api/builder/import?dry_run=true"
```
```json
{
  "dry_run": true,
  "applied": false,
  "changes": {
    "nodes": {
      "add": [],
      "remove": [
        "Работа с клиентами",
        "Маркетинг",
        "Продажи",
        "… ещё 21"
      ],
      "update": []
    },
    "kpis": {
      "add": [],
      "remove": [],
      "update": []
    },
    "links": {
      "add": [],
      "remove": [
        "Фотопринт/on_time_72h_share → Работа с клиентами",
        "Фотопринт/on_time_72h_share → Производство",
        "Фотопринт/on_time_72h_share → Финансы",
        "… ещё 53"
      ],
      "update": []
    },
    "changed": true
  }
}
```

| логин | GET /api/builder/validate | POST /api/builder/nodes |
|---|---|---|
| director | 403 `forbidden` | 403 `forbidden` |
| head_prod | 403 `forbidden` | 403 `forbidden` |
| qc_otk | 403 `forbidden` | 403 `forbidden` |
| builder | 200 | 201 |


## 11. Управление демо-временем

Эндпоинты: `GET /api/demo/clock` (все роли), `POST /api/demo/advance?days=1..60` и `POST /api/demo/reset`
(admin и builder). После перемотки и сброса перечитайте всё: статусы, карточки, заказы и журнал меняются.

`GET /api/demo/clock` от `qc_otk` → **200**

```bash
curl -s -H "X-User: qc_otk" "http://127.0.0.1:8790/api/demo/clock"
```
```json
{
  "now": "2026-11-30T09:00:00+03:00",
  "today": "2026-11-30",
  "default_now": "2026-11-23T09:00:00+03:00",
  "season_profile": "default",
  "utc_offset": "+03:00"
}
```

**Слишком большая перемотка** `POST /api/demo/advance?days=90` от `director` → **422**

```bash
curl -s -X POST -H "X-User: director" "http://127.0.0.1:8790/api/demo/advance?days=90"
```
```json
{
  "error": {
    "code": "validation_error",
    "message": "ошибка валидации запроса: query.days: Input should be less than or equal to 60",
    "details": {
      "errors": [
        {
          "loc": [
            "query",
            "days"
          ],
          "msg": "Input should be less than or equal to 60",
          "type": "less_than_equal"
        }
      ]
    }
  }
}
```

| логин | POST /api/demo/advance?days=1 |
|---|---|
| qc_otk | 403 `forbidden` |
| head_client | 200 |


**Сброс (после него стенд как после run.py --reset)** `POST /api/demo/reset` от `builder` → **200**

```bash
curl -s -X POST -H "X-User: builder" "http://127.0.0.1:8790/api/demo/reset"
```
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

## Подводные камни для фронтенда

1. **`X-User` обязателен везде**, кроме `GET /api/auth/users` и `/health`. Ставьте его в общий HTTP-клиент;
   401 означает «пользователь не выбран».
2. **Серые граничные узлы** (`boundary: upstream|downstream`, `clickable: false`) рисуются, но не открываются:
   `GET /api/nodes/{id}` по ним — 403. У upstream `status: null` (общего статуса нет), виден один KPI без
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

Узлы: Поддержка = 5, Сборка = 11, Производство = 9;
карточка `DEV-0001`; заказ со браком в сегменте сценария — `ORD-000142`.

**Шаг 0. Сброс** `POST /api/demo/reset` от `director` → **200**

```bash
curl -s -X POST -H "X-User: director" "http://127.0.0.1:8790/api/demo/reset"
```
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

**Шаг 1. Обзор** `GET /api/overview` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/overview"
```
```json
[
  {
    "key": "orders",
    "status": "green",
    "open_deviations": 0
  },
  {
    "key": "moderation",
    "status": "green",
    "open_deviations": 0
  },
  {
    "key": "production",
    "status": "green",
    "open_deviations": 0
  },
  {
    "key": "delivery",
    "status": "green",
    "open_deviations": 0
  },
  {
    "key": "quality",
    "status": "red",
    "open_deviations": 1
  },
  {
    "key": "support",
    "status": "green",
    "open_deviations": 0
  },
  {
    "key": "clients",
    "status": "green",
    "open_deviations": 0
  },
  {
    "key": "team",
    "status": "yellow",
    "open_deviations": 0
  }
]
```

**Шаг 2. Trace** `GET /api/analysis/trace?node=5&kpi=defect_tickets_share` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/analysis/trace?node=5&kpi=defect_tickets_share"
```
```json
{
  "root_cause": {
    "node_id": 11,
    "node_name": "Сборка",
    "kpi": "defect_rate",
    "visible": true
  },
  "stopped_reason": "below_threshold",
  "path": [
    [
      "Поддержка",
      "defect_tickets_share"
    ],
    [
      "Сборка",
      "defect_rate"
    ]
  ],
  "alternatives_last": [
    "Смены"
  ]
}
```

**Шаг 3. Карточка** `GET /api/deviations/DEV-0001` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/deviations/DEV-0001"
```
```json
{
  "status": "open",
  "signal": {
    "ts": "2026-11-23T09:00:00+03:00",
    "day": "2026-11-22",
    "value": 9.0,
    "status": "red",
    "level": "crit",
    "threshold": 8.0,
    "detected_by": "auto"
  },
  "dims": {
    "product_line": "Выпускные альбомы",
    "brand": "ФФ РФ"
  },
  "root": {
    "node_id": 11,
    "node_name": "Сборка",
    "kpi": "defect_rate"
  },
  "affected": 8
}
```

**Шаг 4. Подсказка** `GET /api/deviations/DEV-0001/suggest` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/deviations/DEV-0001/suggest"
```
```json
{
  "id": "PB-DEFECT-BATCH",
  "title": "Проверить партию материала и усилить выходной контроль",
  "action": "Проверить партию материала, запущенную перед ростом брака; на время проверки усилить выборочный контроль ОТК на участке",
  "owner_hint": "Зам. по производству",
  "due_days": 3,
  "due_at": "2026-11-26T09:00:00+03:00",
  "recheck_window_days": 7,
  "score": 5
}
```

**Шаг 5. Назначить действие** `PATCH /api/deviations/DEV-0001` от `director` → **200**

```json
// body.json
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
curl -s -X PATCH -H "X-User: director" -H "Content-Type: application/json; charset=utf-8" -d @body.json "http://127.0.0.1:8790/api/deviations/DEV-0001"
```
```json
{
  "status": "assigned",
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
  "history": {
    "ts": "2026-11-23T09:00:00+03:00",
    "user": "director",
    "change": "status",
    "from": "open",
    "to": "assigned",
    "comment": null
  }
}
```

**Шаг 6. Перепроверка сразу — pending** `POST /api/admin/deviations/DEV-0001/recheck` от `director` → **200**

```bash
curl -s -X POST -H "X-User: director" "http://127.0.0.1:8790/api/admin/deviations/DEV-0001/recheck"
```
```json
{
  "recheck": {
    "result": "pending",
    "passed": null,
    "elapsed_days": 0.0,
    "min_days": 3
  },
  "status": "assigned"
}
```

**Шаг 7. Перемотка на 7 суток** `POST /api/demo/advance?days=7` от `director` → **200**

```bash
curl -s -X POST -H "X-User: director" "http://127.0.0.1:8790/api/demo/advance?days=7"
```
```json
{
  "now": "2026-11-30T09:00:00+03:00",
  "days": 7,
  "closed_days": [
    "2026-11-23",
    "2026-11-24",
    "2026-11-25",
    "2026-11-26",
    "2026-11-27",
    "2026-11-28",
    "2026-11-29"
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

**Шаг 8. Перепроверка — passed** `POST /api/admin/deviations/DEV-0001/recheck` от `director` → **200**

```bash
curl -s -X POST -H "X-User: director" "http://127.0.0.1:8790/api/admin/deviations/DEV-0001/recheck"
```
```json
{
  "recheck": {
    "n": 2,
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
  "status": "verified",
  "rechecks_total": 2
}
```

**Шаг 9. Портфель** `GET /api/deviations` от `director` → **200**

```bash
curl -s -H "X-User: director" "http://127.0.0.1:8790/api/deviations"
```
```json
{
  "total": 1,
  "open": 0,
  "overdue": 0,
  "verified": 1,
  "failed": 0,
  "rechecks": 2,
  "recheck_success_rate": 1.0,
  "by_status": {
    "open": 0,
    "assigned": 0,
    "in_progress": 0,
    "done": 0,
    "verified": 1,
    "failed": 0,
    "escalated": 0,
    "closed": 0
  }
}
```

**Шаг 10. Та же карточка у head_client** `GET /api/deviations/DEV-0001` от `head_client` → **200**

```bash
curl -s -H "X-User: head_client" "http://127.0.0.1:8790/api/deviations/DEV-0001"
```
```json
{
  "status": "verified",
  "rechecks": [
    {
      "n": 2,
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
  ]
}
```

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
