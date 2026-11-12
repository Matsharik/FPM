"""Ф2: словарь метрик — загрузка, валидация, профили сезона, запрет денег (Р7)."""

from __future__ import annotations

import pytest
import yaml

from core.errors import BadRequest, ConfigError, Conflict, NotFound
from core.glossary import Glossary, Thresholds, apply_overrides, check_overrides, is_money_unit
from core.settings import load_settings
from network.jsonio import read_json
from network.status import severity, threshold_status

BASE = {
    "title": "Доля брака",
    "source": "erp",
    "unit": "%",
    "direction": "lower_better",
    "thresholds": {"default": {"target": 2.0, "warn": 3.5, "crit": 5.0}},
}


@pytest.fixture
def settings(config_dir):
    return load_settings(config_dir / "settings.yaml")


def write_glossary(tmp_path, metrics) -> str:
    path = tmp_path / "glossary.yaml"
    path.write_text(yaml.safe_dump(metrics, allow_unicode=True), encoding="utf-8")
    return path


# --- демо-словарь ------------------------------------------------------------


def test_demo_glossary_is_valid_and_complete(ws):
    metrics = ws.glossary.metrics
    required = {
        # поддержка
        "tickets_inbound", "tickets_unanswered", "reply_1min_share", "sla_topics_share",
        "defect_tickets_share", "mary_closed_share", "wismo_share",
        # модерация
        "moderation_queue_time", "layout_reject_share",
        # производство
        "site_load", "wip_orders", "on_time_24h_share", "on_time_72h_share", "pay_to_carrier_time",
        "defect_rate", "confirmed_defect_share", "equipment_downtime",
        # доставка
        "delivery_on_time_share", "pvz_unclaimed",
        # продажи и маркетинг
        "orders_rhythm", "repeat_customers_share", "leads",
        # финансы
        "paid_orders_share", "overdue_settlements_share", "cost_to_plan_index",
        # HR
        "shift_staffing", "shift_load", "open_vacancies", "hired_per_day", "fired_per_day",
        "trained_share", "timesheet_deviations",
        # сотрудник
        "tasks_done", "personal_efficiency",
    }
    assert required <= set(metrics)
    assert all(metric.synthetic for metric in metrics.values())
    assert all(metric.money_factor is None for metric in metrics.values())
    assert not any(is_money_unit(metric.unit) for metric in metrics.values())
    assert {metric.source for metric in metrics.values()} == {"crm", "support", "erp", "finance", "hr"}
    tiles = {metric.tile for metric in metrics.values() if metric.tile}
    assert tiles == {t.key for t in ws.settings.tiles}  # у каждой из 8 плиток есть метрики


def test_deadline_metrics_carry_customer_numbers(ws):
    production = ws.glossary.get("production_time").thresholds["default"]
    assert (production.target, production.crit) == (24, 72)  # «за один день» и публичные «до 3 дней»
    carrier = ws.glossary.get("pay_to_carrier_time").thresholds["default"]
    assert carrier.target == 22.87  # 22 ч 52 мин
    defect = ws.glossary.get("defect_rate")
    assert defect.thresholds["default"].model_dump() == {"target": 2.0, "warn": 3.5, "crit": 5.0}
    assert defect.thresholds["season"].model_dump() == {"target": 2.5, "warn": 4.0, "crit": 6.0}


# --- пороги, severity, статус ------------------------------------------------


def test_severity_and_status_lower_better():
    th = Thresholds(target=2.0, warn=3.5, crit=5.0)
    assert th.severity(1.5, "lower_better") == 0.0
    assert th.severity(2.0, "lower_better") == 0.0
    assert th.severity(3.5, "lower_better") == 0.5
    assert th.severity(6.4, "lower_better") == 1.0
    assert [th.status(v, "lower_better") for v in (2.0, 3.4, 3.5, 4.99, 5.0, 6.4)] == [
        "green", "green", "yellow", "yellow", "red", "red",
    ]
    assert [th.level(v, "lower_better") for v in (1.0, 4.0, 6.4)] == ["ok", "warn", "crit"]


def test_severity_and_status_higher_better():
    assert severity(95, 95, 85, "higher_better") == 0.0
    assert severity(90, 95, 85, "higher_better") == 0.5
    assert severity(70, 95, 85, "higher_better") == 1.0
    assert [threshold_status(v, 90, 85, "higher_better") for v in (96, 90.1, 90, 85.1, 85, 60)] == [
        "green", "green", "yellow", "yellow", "red", "red",
    ]


def test_season_profile_and_overrides(ws):
    glossary = ws.glossary
    assert glossary.profile(11) == "default" and glossary.profile(12) == "season"
    assert glossary.profile(6) == "season" and glossary.profile(9) == "default"

    november, profile = glossary.thresholds("defect_rate", {}, 11)
    assert (november.crit, profile) == (5.0, "default")
    december, profile = glossary.thresholds("defect_rate", {}, 12)
    assert (december.crit, profile) == (6.0, "season")
    # у метрики без сезонного профиля в сезон действуют обычные пороги
    same, profile = glossary.thresholds("defect_tickets_share", {}, 12)
    assert (same.crit, profile) == (8.0, "default")
    assert glossary.thresholds(None, {}, 11) == (None, "default")
    assert glossary.thresholds("hired_per_day", {}, 11) == (None, "default")  # порогов нет

    overrides = {"crit": 5.5, "season": {"crit": 7.0}}
    assert glossary.thresholds("defect_rate", overrides, 11)[0].crit == 5.5
    assert glossary.thresholds("defect_rate", overrides, 12)[0].crit == 7.0


def test_overrides_validation(ws):
    metric = ws.glossary.get("defect_rate")
    assert check_overrides(metric, {"warn": 3.0}) == {"warn": 3.0}
    assert check_overrides(metric, None) == {}
    for bad in ({"limit": 1}, {"crit": "много"}, {"season": {"limit": 1}}, {"crit": 1.0}, {"default": 5}):
        with pytest.raises(BadRequest) as info:
            check_overrides(metric, bad)
        assert info.value.code == "invalid_overrides"
    with pytest.raises(BadRequest):
        check_overrides(None, {"crit": 6})  # без словарной метрики переопределять нечего
    with pytest.raises(ValueError):
        apply_overrides(Thresholds(target=2, warn=3, crit=5), {"target": 9}, "default", "lower_better")


# --- валидация словаря -------------------------------------------------------


@pytest.mark.parametrize(
    ("patch", "fragment"),
    [
        ({"thresholds": {"default": {"target": 5, "warn": 3, "crit": 2}}}, "target ≤ warn ≤ crit"),
        ({"direction": "higher_better"}, "target ≥ warn ≥ crit"),
        ({"thresholds": {"season": {"target": 2, "warn": 3, "crit": 5}}}, "нужен профиль default"),
        ({"thresholds": {"default": {"target": 2, "warn": 3, "crit": 5}, "night": {"target": 2, "warn": 3, "crit": 5}}}, "неизвестный профиль"),
        ({"thresholds": {"default": {"target": 0, "warn": 3, "crit": 5}}}, "target = 0"),
        ({"thresholds": {}}, "требует порогов"),
        ({"source": "excel"}, "source"),
        ({"aggregation": "median"}, "aggregation"),
        ({"tile": "марс"}, "неизвестная плитка"),
        ({"stage": 9}, "stage"),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_bad_metric_is_rejected_with_reason(tmp_path, settings, patch, fragment):
    path = write_glossary(tmp_path, {"defect_rate": {**BASE, **patch}})
    with pytest.raises(ConfigError) as info:
        Glossary(path, tmp_path / "data", settings)
    assert "glossary.yaml" in info.value.message and "defect_rate" in info.value.message
    assert fragment in info.value.message


def test_bad_key_and_shape(tmp_path, settings):
    with pytest.raises(ConfigError, match="ключ метрики"):
        Glossary(write_glossary(tmp_path, {"Доля брака": BASE}), tmp_path / "data", settings)
    with pytest.raises(ConfigError, match="ожидался объект"):
        Glossary(write_glossary(tmp_path, ["defect_rate"]), tmp_path / "data", settings)
    with pytest.raises(ConfigError, match="не найден"):
        Glossary(tmp_path / "нет.yaml", tmp_path / "data", settings)


# --- деньги (Р7) -------------------------------------------------------------


@pytest.mark.parametrize("unit", ["BYN", "RUB", "₽", "руб", "руб.", "тыс. руб", "USD", "EUR", "$", "byn/шт", "usd"])
def test_money_units_are_detected(unit):
    assert is_money_unit(unit)


@pytest.mark.parametrize("unit", ["%", "шт", "ч", "мин", "индекс", "чел", "доля", "", None, "eurobox", "шт/ч"])
def test_ordinary_units_are_not_money(unit):
    assert not is_money_unit(unit)


@pytest.mark.parametrize(
    "patch",
    [
        {"unit": "BYN"},
        {"unit": "руб."},
        {"display": {"relative": "as_is", "natural": "₽"}},
        {"money_factor": 12.5},
    ],
)
def test_glossary_with_money_fails_to_load(tmp_path, settings, patch):
    path = write_glossary(tmp_path, {"revenue": {**BASE, **patch}})
    with pytest.raises(ConfigError) as info:
        Glossary(path, tmp_path / "data", settings)
    message = info.value.message
    assert "revenue" in message and "allow_money" in message


def test_money_is_one_flag_away(tmp_path, settings):
    allowed = settings.model_copy(update={"allow_money": True})
    path = write_glossary(tmp_path, {"revenue": {**BASE, "unit": "BYN", "money_factor": 12.5}})
    glossary = Glossary(path, tmp_path / "data", allowed)
    assert glossary.get("revenue").money_factor == 12.5


# --- правка через API-слой: рабочая копия, а не исходник ---------------------


def test_edits_go_to_runtime_copy(ws, data_dir, config_dir):
    source = (config_dir / "glossary.yaml").read_bytes()
    version = ws.glossary.version
    ws.glossary.add("incoming_material_defect_rate", {
        "title": "Входной брак материалов", "source": "erp", "unit": "%",
        "direction": "lower_better", "thresholds": {"default": {"target": 1, "warn": 2, "crit": 3}},
    })
    ws.glossary.patch("defect_rate", {"thresholds": {"default": {"target": 2, "warn": 3, "crit": 4}}})
    assert ws.glossary.version == version + 2

    assert (config_dir / "glossary.yaml").read_bytes() == source  # исходник не тронут
    stored = read_json(data_dir / "glossary.json")
    assert stored["incoming_material_defect_rate"]["title"] == "Входной брак материалов"
    assert stored["defect_rate"]["thresholds"] == {"default": {"target": 2.0, "warn": 3.0, "crit": 4.0}}

    from core.workspace import Workspace

    again = Workspace(ws.config_dir, ws.data_dir)  # перезапуск читает рабочую копию
    assert again.glossary.get("defect_rate").thresholds["default"].crit == 4.0
    again.glossary.restore_source()
    assert again.glossary.get("defect_rate").thresholds["default"].crit == 5.0
    assert again.glossary.find("incoming_material_defect_rate") is None


def test_edit_errors(ws, data_dir):
    with pytest.raises(Conflict):
        ws.glossary.add("defect_rate", BASE)
    with pytest.raises(NotFound):
        ws.glossary.patch("нет_такой", {"title": "x"})
    with pytest.raises(BadRequest) as info:
        ws.glossary.patch("defect_rate", {"unit": "BYN"})
    assert info.value.code == "money_forbidden"
    with pytest.raises(BadRequest):
        ws.glossary.add("revenue", {**BASE, "unit": "руб"})
    with pytest.raises(BadRequest):
        ws.glossary.patch("defect_rate", {"thresholds": {"default": {"target": 9, "warn": 3, "crit": 5}}})
    assert ws.glossary.get("defect_rate").unit == "%"
    assert not (data_dir / "glossary.json").exists()  # неудачные правки ничего не записали
