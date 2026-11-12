"""Модели запросов и ответов API (они же — схема в OpenAPI)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["green", "yellow", "red", "unknown"]
NodeType = Literal[
    "system", "subsystem", "function", "department", "team", "person", "partner", "product_line"
]
Compute = Literal["measured", "weighted"]
Access = Literal["inherit", "none"]
AttrValue = bool | int | float | str

TS_EXAMPLE = "2026-11-22T00:00:00+03:00"


class OkOut(BaseModel):
    ok: bool = True


# --- флажки и точки ----------------------------------------------------------


class FlagIn(BaseModel):
    ts: str | datetime = Field(examples=[TS_EXAMPLE], description="ISO 8601 с часовым поясом")
    kind: str = Field(min_length=1, examples=["warning"])
    values: list[int] = Field(default_factory=list)
    label: str | None = Field(default=None, examples=["Новый материал обложки"])
    ref: str | None = Field(default=None, examples=["DEV-0001"], description="id карточки отклонения")


class FlagOut(BaseModel):
    ts: str = Field(examples=["2026-11-21T21:00:00Z"])
    kind: str = Field(examples=["warning"])
    values: list[int] = Field(default_factory=list)
    label: str | None = None
    ref: str | None = None


class FlagsRemoved(BaseModel):
    removed: int = Field(examples=[1])


class PointIn(BaseModel):
    ts: str | datetime = Field(examples=[TS_EXAMPLE], description="ISO 8601 с часовым поясом")
    value: float = Field(examples=[6.4])


class PointOut(BaseModel):
    ts: str = Field(examples=["2026-11-21T21:00:00Z"])
    value: float = Field(examples=[6.4])


class PointAdded(BaseModel):
    ok: bool = True
    point: PointOut
    deviations_created: list[str] = Field(
        default_factory=list, examples=[["DEV-0002"]], description="карточки, созданные автодетекцией"
    )


class PointsAdded(BaseModel):
    ok: bool = True
    added: int = Field(examples=[7])
    deviations_created: list[str] = Field(default_factory=list, examples=[["DEV-0002"]])


class SeriesOut(BaseModel):
    name: str = Field(examples=["defect_rate"])
    unit: str = Field(examples=["%"])
    tags: dict[str, str] = Field(default_factory=dict)
    points: list[PointOut]
    flags: list[FlagOut]


# --- узлы и KPI --------------------------------------------------------------


class KpiOut(BaseModel):
    name: str = Field(examples=["defect_rate"])
    metric: str | None = Field(default=None, examples=["defect_rate"], description="ключ словаря метрик")
    compute: Compute = "measured"
    pinned: bool = False
    overrides: dict[str, Any] = Field(default_factory=dict)
    unit: str = Field(default="", examples=["%"])


class KpiCreate(BaseModel):
    name: str = Field(min_length=1, examples=["defect_rate"])
    metric: str | None = Field(default=None, examples=["defect_rate"])
    compute: Compute = "measured"
    pinned: bool = False
    overrides: dict[str, Any] = Field(default_factory=dict)
    unit: str = Field(default="", examples=["%"])
    tags: dict[str, str] | None = None
    points: list[PointIn] = Field(default_factory=list)


class KpiPatch(BaseModel):
    metric: str | None = None
    compute: Compute | None = None
    pinned: bool | None = None
    overrides: dict[str, Any] | None = None
    unit: str | None = None


class NodeCreate(BaseModel):
    name: str = Field(min_length=1, examples=["Закупки"])
    description: str = ""
    type: NodeType = "department"
    owner: str = Field(default="", examples=["Зам. по производству"])
    attrs: dict[str, AttrValue] = Field(default_factory=dict, examples=[{"shift_mode": "2/2"}])
    parameters: dict[str, int] = Field(default_factory=dict)
    tile: str | None = Field(default=None, examples=["production"])
    stage: int | None = Field(default=None, ge=1, le=8)
    tags: dict[str, str] = Field(default_factory=dict)
    synthetic: bool = False


class NodePatch(BaseModel):
    """Передавайте только изменяемые поля; ``tile`` и ``stage`` можно сбросить, передав null."""

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    type: NodeType | None = None
    owner: str | None = None
    attrs: dict[str, AttrValue] | None = None
    tile: str | None = None
    stage: int | None = Field(default=None, ge=1, le=8)
    tags: dict[str, str] | None = None
    synthetic: bool | None = None


class NodeOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int = Field(examples=[12])
    name: str = Field(examples=["Сборка"])
    type: NodeType = "department"
    description: str = ""
    owner: str = ""
    attrs: dict[str, AttrValue] = Field(default_factory=dict)
    parameters: dict[str, int] = Field(default_factory=dict)
    tile: str | None = None
    stage: int | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    kpis: list[KpiOut] = Field(default_factory=list)
    flags: list[FlagOut] = Field(default_factory=list)
    synthetic: bool = False
    created_by: str | None = None
    status: Status = "unknown"


# --- связи -------------------------------------------------------------------


class LinkCreate(BaseModel):
    from_node: int = Field(examples=[3])
    from_kpi: str = Field(min_length=1, examples=["defect_tickets_share"])
    to_node: int = Field(examples=[12])
    to_kpi: str | None = Field(default=None, examples=["defect_rate"])
    weight: float | None = Field(
        default=None,
        gt=0,
        le=1,
        examples=[0.2],
        description="Без веса все связи KPI становятся равными 1/n",
    )
    access: Access = "inherit"
    note: str = ""


class LinkPatch(BaseModel):
    """Передавайте только изменяемые поля; ``to_kpi`` можно сбросить, передав null."""

    to_kpi: str | None = None
    weight: float | None = Field(default=None, gt=0, le=1)
    access: Access | None = None
    note: str | None = None


class LinkOut(BaseModel):
    id: str = Field(examples=["L-0007"])
    from_node: int
    from_kpi: str
    to_node: int
    to_kpi: str | None = None
    weight: float = Field(examples=[0.6])
    access: Access = "inherit"
    note: str = ""
    flags: list[FlagOut] = Field(default_factory=list)
    created_by: str | None = None
    created_at: str | None = None


class LinkChange(BaseModel):
    """Результат правки связи: сама связь и все связи того же KPI после нормировки весов."""

    link: LinkOut | None = None
    kpi_links: list[LinkOut]


class WeightsPut(BaseModel):
    weights: dict[str, float] = Field(
        examples=[{"L-0007": 0.6, "L-0008": 0.25, "L-0009": 0.15}],
        description="Полный набор: id связи -> вес. Сумма равна 1 (или normalize=true)",
    )


class NodeDetail(NodeOut):
    links_out: list[LinkOut] = Field(default_factory=list, description="Связи от KPI этого узла")
    links_in: list[LinkOut] = Field(default_factory=list, description="Связи, ведущие в этот узел")


# --- словарь, значения и статусы KPI ------------------------------------------

Units = Literal["relative", "natural", "money"]
Direction = Literal["lower_better", "higher_better"]
Priority = Literal["time", "quality", "cost", "other"]
Source = Literal["crm", "support", "erp", "finance", "hr"]
Aggregation = Literal["mean", "sum", "last"]
RelativeKind = Literal["pct_of_target", "index", "share", "as_is"]


class ThresholdsModel(BaseModel):
    target: float = Field(examples=[2.0])
    warn: float = Field(examples=[3.5])
    crit: float = Field(examples=[5.0])


class DisplayModel(BaseModel):
    relative: RelativeKind = "pct_of_target"
    natural: str = Field(default="", examples=["%"])


class MetricOut(BaseModel):
    title: str = Field(examples=["Доля брака"])
    definition: str = ""
    formula: str = ""
    source: Source
    owner: str = ""
    unit: str = Field(default="", examples=["%"])
    display: DisplayModel
    money_factor: float | None = None
    direction: Direction
    priority: Priority
    tile: str | None = None
    stage: int | None = None
    thresholds: dict[str, ThresholdsModel] = Field(
        default_factory=dict, description="Профили порогов: default и, если есть, season"
    )
    aggregation: Aggregation = "mean"
    status_window_days: int | None = None
    synthetic: bool = True


class MetricCreate(MetricOut):
    key: str = Field(examples=["incoming_material_defect_rate"], description="Ключ метрики в словаре")
    display: DisplayModel = Field(default_factory=DisplayModel)
    direction: Direction = "lower_better"
    priority: Priority = "other"


class MetricPatch(BaseModel):
    """Передавайте только изменяемые поля."""

    title: str | None = None
    definition: str | None = None
    formula: str | None = None
    source: Source | None = None
    owner: str | None = None
    unit: str | None = None
    display: DisplayModel | None = None
    money_factor: float | None = None
    direction: Direction | None = None
    priority: Priority | None = None
    tile: str | None = None
    stage: int | None = None
    thresholds: dict[str, ThresholdsModel] | None = None
    aggregation: Aggregation | None = None
    status_window_days: int | None = None
    synthetic: bool | None = None


class GlossaryOut(BaseModel):
    metrics: dict[str, MetricOut]
    season_months: list[int] = Field(examples=[[5, 6, 7, 12]])
    current_profile: Literal["default", "season"] = "default"
    allow_money: bool = False
    units: list[Units] = Field(examples=[["relative", "natural"]])


class KpiCard(BaseModel):
    """KPI узла: значение, статус и пороги в выбранных единицах."""

    node_id: int
    name: str = Field(examples=["defect_rate"])
    metric: str | None = None
    title: str = Field(examples=["Доля брака"])
    compute: Compute = "measured"
    pinned: bool = False
    units: Units = "natural"
    unit: str = Field(examples=["%"], description="Подпись единицы в выбранном режиме")
    value: float | None = Field(default=None, examples=[6.4])
    value_date: str | None = Field(default=None, examples=["2026-11-22"])
    status: Status
    severity: float = Field(ge=0, le=1, examples=[1.0])
    level: Literal["ok", "warn", "crit"] | None = None
    status_source: Literal["thresholds", "flags"] = "thresholds"
    profile: Literal["default", "season"] = "default"
    thresholds: ThresholdsModel | None = None
    direction: Direction = "lower_better"
    priority: Priority = "other"
    tile: str | None = None
    stage: int | None = None
    source: Source | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    days: int = Field(description="Число суток с данными")
    stale: bool = Field(description="Свежих данных нет дольше settings.stale_days")


class KpiSeries(KpiCard):
    agg: Literal["raw", "day"] = "raw"
    points: list[PointOut]
    flags: list[FlagOut]


# --- аналитика: вклад, trace, прогноз ------------------------------------------

StopReason = Literal["no_links", "below_threshold", "out_of_zone", "no_kpi", "max_depth"]


class ContributionOut(BaseModel):
    """Связь KPI и её вклад. У цели вне зоны KPI и цифры не отдаются (null)."""

    link_id: str = Field(examples=["L-0007"])
    to_node: int = Field(examples=[12])
    to_node_name: str = Field(examples=["Сборка"])
    owner: str = Field(default="", examples=["Зам. по производству"])
    to_kpi: str | None = Field(default=None, examples=["defect_rate"], description="как задано в связи")
    target_kpi: str | None = Field(
        default=None,
        examples=["defect_rate"],
        description="KPI цели в расчёте: to_kpi или худший KPI узла",
    )
    weight: float = Field(examples=[0.6])
    access: Access = "inherit"
    status: Status = Field(examples=["red"])
    visible: bool = Field(default=True, description="false — узел вне зоны пользователя")
    severity: float | None = Field(default=None, examples=[1.0])
    contribution: float | None = Field(default=None, examples=[0.6], description="weight × severity")
    share: float | None = Field(default=None, examples=[0.97], description="доля вклада среди связей KPI")


class ContributionsOut(BaseModel):
    node_id: int = Field(examples=[3])
    node_name: str = Field(examples=["Поддержка"])
    kpi: str = Field(examples=["defect_tickets_share"])
    title: str = Field(examples=["Доля обращений по браку"])
    status: Status
    severity: float = Field(examples=[1.0])
    total_contribution: float = Field(examples=[0.62], description="сумма вкладов видимых связей")
    hidden_links: int = Field(
        default=0, examples=[0], description="связей к узлам вне зоны: их вклад и доля не отдаются"
    )
    summary: str = Field(examples=["Доля обращений по браку: Сборка 97%, ОТК 3%"])
    links: list[ContributionOut]


class TraceStep(BaseModel):
    """Шаг trace. Граничный узел вне зоны: ``visible: false``, без KPI и цифр."""

    depth: int = Field(examples=[1])
    node_id: int = Field(examples=[12])
    node_name: str = Field(examples=["Сборка"])
    node_type: NodeType = "department"
    owner: str = Field(default="", examples=["Зам. по производству"])
    visible: bool = True
    kpi: str | None = Field(default=None, examples=["defect_rate"])
    title: str | None = Field(default=None, examples=["Доля брака"])
    status: Status
    severity: float | None = Field(default=None, examples=[1.0])
    value: float | None = Field(default=None, examples=[6.4])
    value_date: str | None = Field(default=None, examples=["2026-11-22"])
    unit: str | None = Field(default=None, examples=["%"])
    via: ContributionOut | None = Field(default=None, description="связь, по которой пришли")
    chosen: ContributionOut | None = Field(default=None, description="связь, по которой пошли дальше")
    alternatives: list[ContributionOut] = Field(
        default_factory=list,
        description=(
            "до двух связей, по которым не пошли: видимые с ненулевым вкладом (по вкладу), "
            "затем ведущие за зону (по id связи, без цифр)"
        ),
    )


class TraceRoot(BaseModel):
    node_id: int = Field(examples=[12])
    node_name: str = Field(examples=["Сборка"])
    kpi: str | None = Field(default=None, examples=["defect_rate"])
    visible: bool = True


class TraceStart(BaseModel):
    node_id: int = Field(examples=[3])
    kpi: str = Field(examples=["defect_tickets_share"])


class TraceOut(BaseModel):
    start: TraceStart
    steps: list[TraceStep]
    root_cause: TraceRoot
    stopped_reason: StopReason = Field(
        description=(
            "no_links — у KPI нет связей; below_threshold — вклад лучшей связи меньше "
            "min_contribution; out_of_zone — следующий узел вне зоны; no_kpi — у узла нет KPI"
        )
    )
    min_contribution: float = Field(examples=[0.15])


class ForecastPoint(BaseModel):
    date: str = Field(examples=["2026-11-23"])
    ts: str = Field(examples=["2026-11-22T21:00:00Z"], description="начало местных суток")
    value: float = Field(examples=[7.1])
    lower: float = Field(examples=[6.8], description="value − σ")
    upper: float = Field(examples=[7.4], description="value + σ")


class ForecastCrossing(BaseModel):
    date: str = Field(examples=["2026-11-25"])
    in_days: int = Field(examples=[2], description="через сколько суток от «сегодня» стенда")
    value: float = Field(examples=[5.2])
    threshold: float = Field(examples=[5.0])
    profile: Literal["default", "season"] = "default"
    already: bool = Field(default=False, description="порог пройден уже сейчас (не будущее пересечение)")


class ForecastCrossings(BaseModel):
    warn: ForecastCrossing | None = None
    crit: ForecastCrossing | None = None


class ForecastOut(BaseModel):
    node_id: int
    kpi: str = Field(examples=["defect_rate"])
    title: str = Field(examples=["Доля брака"])
    method: str = Field(examples=["linear_trend+weekday_seasonality"])
    method_text: str
    horizon: int = Field(examples=[14])
    lookback_days: int = Field(examples=[28])
    units: Units = "natural"
    unit: str = Field(examples=["%"])
    direction: Direction = "lower_better"
    status_now: Status
    history_from: str | None = Field(default=None, examples=["2026-10-26"])
    history_to: str | None = Field(default=None, examples=["2026-11-22"])
    history_days: int = Field(examples=[28])
    stale: bool = Field(default=False, description="последние сутки с данными старше settings.stale_days")
    enough_data: bool = Field(description="false — меньше 7 суток данных, прогноз не строится")
    seasonal: bool = Field(description="учтена ли недельная сезонность (нужно ≥ 14 суток)")
    trend_per_day: float | None = Field(default=None, examples=[0.12])
    sigma: float | None = Field(default=None, examples=[0.3])
    points: list[ForecastPoint]
    crossings: ForecastCrossings


# --- отклонения и решения ------------------------------------------------------

DeviationStatus = Literal[
    "open", "assigned", "in_progress", "done", "verified", "failed", "escalated", "closed"
]
Confidence = Literal["low", "medium", "high"]


class SignalOut(BaseModel):
    ts: str = Field(examples=["2026-11-23T09:00:00+03:00"], description="момент обнаружения")
    day: str | None = Field(default=None, examples=["2026-11-22"], description="сутки значения")
    value: float | None = Field(default=None, examples=[9.0])
    status: Status
    level: Literal["ok", "warn", "crit"] | None = None
    threshold: float | None = Field(default=None, examples=[8.0])
    detected_by: Literal["auto", "manual"] = "auto"


class ContextWindow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from", examples=["2026-11-16T00:00:00+03:00"])
    to: str = Field(examples=["2026-11-23T00:00:00+03:00"])


class ContextOut(BaseModel):
    tile: str | None = Field(default=None, examples=["support"])
    stage: int | None = Field(default=None, examples=[7])
    season_profile: Literal["default", "season"] = "default"
    dims: dict[str, Any] = Field(default_factory=dict, description="измерения из аннотаций (Ф6)")
    window: ContextWindow | None = None


class CauseRoot(BaseModel):
    node_id: int = Field(examples=[5])
    node_name: str = Field(examples=["Сборка"])
    kpi: str | None = Field(default=None, examples=["defect_rate"])


class ConfidenceBasis(BaseModel):
    node_id: int = Field(examples=[6])
    kpi: str = Field(examples=["confirmed_defect_share"])
    value: float | None = Field(default=None, examples=[76.1])
    status: Status


class CauseOut(BaseModel):
    trace: list[TraceStep] = Field(description="снимок trace на момент создания")
    root: CauseRoot
    stopped_reason: StopReason
    hypothesis: str = ""
    confidence: Confidence = "medium"
    confidence_basis: ConfidenceBasis | None = Field(
        default=None, description="KPI «доля подтверждённого брака», по которому оценена уверенность"
    )
    set_by: str | None = None


class ActionOut(BaseModel):
    text: str = Field(default="", examples=["Проверить партию материала обложки"])
    owner_login: str | None = Field(default=None, examples=["head_prod"])
    owner_node: int | None = Field(default=None, examples=[5])
    due_at: str | None = Field(default=None, examples=["2026-11-26T18:00:00+03:00"])
    playbook_ref: str | None = Field(default=None, examples=["PB-DEFECT-BATCH"])
    assigned_at: str | None = Field(
        default=None,
        description="точка отсчёта перепроверки; смена исполнителя или срока её не двигает",
    )
    assigned_by: str | None = None
    first_assigned_at: str | None = Field(
        default=None, description="первое назначение действия по карточке; к нему привязана демо-ветка"
    )
    done_at: str | None = None
    done_by: str | None = None


class RecheckWindow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from", examples=["2026-11-16T09:00:00+03:00"], description="начало окна (момент)")
    to: str = Field(examples=["2026-11-23T09:00:00+03:00"], description="конец окна (момент)")
    days: int = Field(examples=[7], description="суток с данными")
    value: float | None = Field(default=None, examples=[7.78], description="среднее дневных значений")
    severity: float | None = Field(default=None, examples=[0.95])


class RecheckOut(BaseModel):
    n: int = Field(examples=[1])
    ts: str
    user: str = Field(examples=["director"])
    window_days: int = Field(examples=[7], description="наибольшая длина окна «после»")
    reference: Literal["action", "signal"] = Field(description="от чего отсчитано окно")
    reference_ts: str
    without_action: bool = Field(
        default=False, description="действие не назначалось: verified невозможен, в долю успеха не входит"
    )
    elapsed_days: float | None = Field(default=None, examples=[7.0], description="прошло суток после точки отсчёта")
    min_days: int | None = Field(default=None, examples=[3], description="раньше этого срока итог — pending")
    profile: Literal["default", "season"] = "default"
    target: float | None = Field(examples=[4.0], description="null — KPI сигнала вне зоны пользователя")
    baseline: RecheckWindow | None = Field(default=None, description="нет при pending")
    after: RecheckWindow | None = Field(default=None, description="нет при pending")
    improvement: float | None = Field(default=None, examples=[0.84], description="падение severity")
    min_improvement: float = Field(examples=[0.5])
    result: Literal["passed", "failed", "pending"] = Field(
        default="pending", description="pending — прошло меньше min_days, статус карточки не изменён"
    )
    passed: bool | None = Field(default=None, description="null при pending")
    rule: Literal["target", "improvement"] | None = Field(
        default=None, description="target — after не хуже цели; improvement — severity упала достаточно"
    )
    status_before: DeviationStatus
    status_after: DeviationStatus


class AffectedOrders(BaseModel):
    count: int = Field(default=0, examples=[12], description="заказов, видимых пользователю")
    sample: list[str] = Field(default_factory=list, examples=[["ORD-000123"]], description="первые 20 id")
    dims: dict[str, str] = Field(
        default_factory=dict, examples=[{"product_line": "Выпускные альбомы", "brand": "ФФ РФ"}]
    )
    stage: int | None = Field(default=None, examples=[7], description="этап карточки")
    window: dict[str, str] | None = Field(default=None, description="окно сигнала (from/to)")


class HistoryEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str
    user: str
    change: str = Field(examples=["status"], description="created | status | action | hypothesis | confidence | recheck")


class CurrentKpi(BaseModel):
    """Состояние KPI сигнала сейчас; если узел сигнала вне зоны — только статус."""

    value: float | None = None
    value_date: str | None = None
    status: Status
    severity: float | None = None


class DeviationOut(BaseModel):
    id: str = Field(examples=["DEV-0001"])
    node_id: int = Field(examples=[3])
    node_name: str = Field(examples=["Поддержка"])
    kpi: str = Field(examples=["defect_tickets_share"])
    title: str = Field(examples=["Доля обращений по браку"])
    status: DeviationStatus
    created_at: str
    signal: SignalOut
    context: ContextOut
    cause: CauseOut
    action: ActionOut
    rechecks: list[RecheckOut] = Field(description="все перепроверки по порядку; не перезаписываются")
    resolution: Literal["self_resolved"] | None = Field(
        default=None, description="self_resolved — KPI пришёл в норму без назначенного действия, карточка закрыта"
    )
    affected_orders: AffectedOrders
    history: list[HistoryEntry]
    synthetic: bool = False
    overdue: bool = Field(description="срок действия прошёл, а действие не выполнено")
    current: CurrentKpi | None = Field(default=None, description="состояние KPI карточки сейчас")


class PortfolioSummary(BaseModel):
    total: int
    open: int = Field(description="не verified и не closed")
    overdue: int
    verified: int
    failed: int
    rechecks: int
    recheck_success_rate: float | None = Field(
        default=None,
        description=(
            "доля карточек, у которых последняя завершённая перепроверка назначенного действия прошла "
            "(без pending и без карточек без действия; повторные вызовы долю не двигают)"
        ),
    )
    by_status: dict[str, int]


class PortfolioOut(BaseModel):
    items: list[DeviationOut]
    summary: PortfolioSummary


class DeviationCreate(BaseModel):
    node_id: int = Field(examples=[5])
    kpi: str = Field(min_length=1, examples=["defect_rate"])
    hypothesis: str = Field(default="", examples=["Новый материал обложки"])


class ActionIn(BaseModel):
    """Передавайте только изменяемые поля действия."""

    text: str | None = Field(default=None, examples=["Проверить партию материала обложки"])
    owner_login: str | None = Field(default=None, examples=["head_prod"])
    owner_node: int | None = Field(default=None, examples=[5])
    due_at: str | None = Field(default=None, examples=["2026-11-26T18:00:00+03:00"])
    playbook_ref: str | None = Field(default=None, examples=["PB-DEFECT-BATCH"])


class DeviationPatch(BaseModel):
    """Переход в `assigned` требует text, владельца (owner_login или owner_node) и due_at."""

    status: DeviationStatus | None = Field(default=None, examples=["assigned"])
    action: ActionIn | None = None
    hypothesis: str | None = Field(default=None, examples=["Новый материал обложки"])
    confidence: Confidence | None = None
    comment: str | None = Field(default=None, description="комментарий к смене статуса")


class DoneIn(BaseModel):
    comment: str | None = Field(default=None, examples=["Партия заменена"])


class RecheckResult(BaseModel):
    recheck: RecheckOut
    deviation: DeviationOut


class Suggestion(BaseModel):
    id: str = Field(examples=["PB-DEFECT-BATCH"])
    title: str
    action: str
    owner_hint: str | None = None
    due_days: int = Field(examples=[3])
    due_at: str = Field(description="срок, если назначить сейчас")
    recheck_window_days: int = Field(examples=[7])
    score: int = Field(description="сколько условий правила совпало (метрика 4, тип узла 2, тег 1)")


class SuggestRoot(CauseRoot):
    metric: str | None = Field(default=None, examples=["defect_rate"])
    node_type: NodeType = "department"


class SuggestOut(BaseModel):
    deviation_id: str = Field(examples=["DEV-0001"])
    root: SuggestRoot
    suggestions: list[Suggestion]


# --- демо ----------------------------------------------------------------------


class ClockOut(BaseModel):
    now: str = Field(examples=["2026-11-23T09:00:00+03:00"])
    today: str = Field(examples=["2026-11-23"])
    default_now: str = Field(examples=["2026-11-23T09:00:00+03:00"])
    season_profile: Literal["default", "season"] = "default"
    utc_offset: str = Field(examples=["+03:00"])


class AdvanceOut(BaseModel):
    now: str = Field(examples=["2026-11-30T09:00:00+03:00"])
    days: int = Field(examples=[7])
    closed_days: list[str] = Field(description="сутки, за которые дописаны точки")
    points_written: int
    branches: dict[str, str] = Field(
        examples=[{"Сборка/defect_rate": "with_action"}], description="ветка будущего по KPI сценария"
    )
    deviations_created: list[str]


class ResetOut(BaseModel):
    now: str
    nodes: int
    links: int
    orders: int = Field(examples=[200], description="заказов в плане, включая будущие (D86)")
    events: int = Field(examples=[1866], description="событий источников, включая будущие")
    deviations: list[str] = Field(examples=[["DEV-0001"]])


# --- вход, профиль и видимый граф ----------------------------------------------

Role = Literal["admin", "qc", "builder"]
Boundary = Literal["upstream", "downstream"]


class NodeRefOut(BaseModel):
    id: int | None = Field(examples=[4], description="null — узла с таким именем в сети нет")
    name: str = Field(examples=["Производство"])


class UserOut(BaseModel):
    login: str = Field(examples=["head_prod"])
    name: str = Field(examples=["Зам. по производству"])
    role: Role
    scope_roots: list[NodeRefOut] = Field(description="Верхние узлы зоны")
    node: NodeRefOut | None = Field(default=None, description="Узел самого пользователя")


class MeOut(UserOut):
    permissions: list[str] = Field(
        examples=[["deviations.done", "flags.write", "points.write"]],
        description="Действия, разрешённые роли (матрица прав)",
    )
    sees_everything: bool = Field(description="Корневой admin: весь журнал без фильтра по зоне")
    zone: list[int] = Field(description="id узлов зоны")


class GraphKpi(BaseModel):
    """KPI узла на графе. У граничного узла сверху — только название и статус."""

    name: str = Field(examples=["defect_rate"])
    metric: str | None = None
    title: str = Field(examples=["Доля брака"])
    compute: Compute | None = None
    pinned: bool | None = None
    unit: str | None = Field(default=None, examples=["%"])
    value: float | None = Field(default=None, examples=[6.4])
    value_date: str | None = Field(default=None, examples=["2026-11-22"])
    status: Status
    severity: float | None = None
    stale: bool | None = None


class GraphNode(BaseModel):
    """Узел видимого графа. Граничный узел: ``boundary`` задан, ``clickable: false``, поля урезаны."""

    id: int = Field(examples=[5])
    name: str = Field(examples=["Сборка"])
    type: NodeType = "department"
    description: str = ""
    owner: str = ""
    attrs: dict[str, AttrValue] = Field(default_factory=dict)
    tile: str | None = None
    stage: int | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    synthetic: bool = False
    flags: list[FlagOut] = Field(default_factory=list)
    status: Status | None = Field(
        description="Собственный статус (худший KPI). У граничного сверху — null"
    )
    deep_status: Status | None = Field(
        description="Худший статус в поддереве внутри зоны; у граничных — null"
    )
    scope_root: bool = Field(default=False, description="Узел — один из scope_roots пользователя")
    boundary: Boundary | None = Field(default=None, description="null — узел зоны")
    clickable: bool = True
    kpis: list[GraphKpi] = Field(default_factory=list)


class GraphLink(BaseModel):
    """Связь видимого графа. ``boundary`` — связь с граничным узлом: цифры вклада не отдаются."""

    id: str = Field(examples=["L-0013"])
    from_node: int
    from_kpi: str
    to_node: int
    to_kpi: str | None = None
    weight: float = Field(examples=[0.6])
    access: Access = "inherit"
    note: str = ""
    flags: list[FlagOut] = Field(default_factory=list)
    boundary: Boundary | None = None
    contribution: float | None = Field(default=None, description="weight × severity цели")
    share: float | None = Field(default=None, description="доля среди видимых связей KPI")


class GraphOut(BaseModel):
    units: Units = "natural"
    roots: list[int] = Field(description="scope_roots пользователя, которые есть в сети")
    zone_size: int = Field(description="Число узлов зоны (без граничных)")
    nodes: list[GraphNode]
    links: list[GraphLink]


# --- очередь, статистика, люди, журнал ---------------------------------------------


class StaleKpi(BaseModel):
    node_id: int
    node_name: str
    kpi: str
    title: str
    last_date: str | None = Field(default=None, description="последние сутки с данными")
    days_without_data: int | None = None


class QueueOut(BaseModel):
    my_actions: list[DeviationOut] = Field(description="Карточки, где я исполнитель (не завершённые)")
    deviations_on_my_nodes: list[DeviationOut] = Field(
        description="Открытые карточки на узлах моей зоны (кроме моих действий)"
    )
    stale_kpis: list[StaleKpi] = Field(description="KPI зоны без свежих данных (settings.stale_days)")


class StatsOut(BaseModel):
    login: str
    date: str = Field(examples=["2026-11-23"])
    week_from: str = Field(examples=["2026-11-17"], description="начало 7-суточного окна")
    actions_done_today: int
    actions_done_week: int
    points_today: int = Field(description="точек внесено мной за сегодня (по журналу)")
    points_week: int
    node: NodeRefOut | None = None
    personal_kpis: list[KpiCard] = Field(description="KPI моего узла")


class PersonAction(BaseModel):
    deviation_id: str = Field(examples=["DEV-0001"])
    title: str
    status: DeviationStatus
    text: str = ""
    due_at: str | None = None
    overdue: bool
    done_at: str | None = None


class PersonOut(BaseModel):
    id: int
    name: str = Field(examples=["Сборщик 1"])
    owner: str = ""
    status: Status
    logins: list[str] = Field(default_factory=list, description="пользователи, чей узел — этот человек")
    actions: list[PersonAction]
    kpis: list[KpiCard]


class PeopleOut(BaseModel):
    node_id: int
    node_name: str
    units: Units = "natural"
    people: list[PersonOut]


class AuditRecord(BaseModel):
    seq: int
    ts: str
    user: str = Field(examples=["director"])
    role: Role | None = None
    action: str = Field(examples=["deviation.update"])
    object_type: str = Field(examples=["deviation"])
    object_id: Any = Field(examples=["DEV-0001"])
    details: dict[str, Any] = Field(default_factory=dict)
    details_hidden: bool = Field(
        default=False, description="запись задевает узлы вне зоны: подробности скрыты"
    )
    nodes: list[int] = Field(default_factory=list, description="узлы, к которым относится запись")


class AuditOut(BaseModel):
    total: int = Field(description="записей после фильтров (до limit/offset)")
    items: list[AuditRecord] = Field(description="новые сверху")


# --- источники, события, заказы и поток (Ф6) ---------------------------------

StageStatus = Literal["pending", "in_progress", "done", "late", "defect"]
OrderStatus = Literal["in_progress", "completed"]


class SourceOut(BaseModel):
    key: Source
    title: str = Field(examples=["CRM"])
    system: str = Field(examples=["Битрикс24"])
    provides: list[str] = Field(examples=[["клиенты", "сделки", "коммуникации", "задачи"]])
    mode: Literal["mock"] = "mock"
    read_only: bool = True
    connector: str = Field(examples=["в проде — коннектор только на чтение"])
    note: str = ""
    events: int = Field(examples=[812], description="событий, видимых пользователю")
    last_event_at: str | None = Field(default=None, examples=["2026-11-23T08:41:00+03:00"])
    event_types: list[str] = Field(examples=[["crm.lead", "crm.next_offer"]])
    metrics: list[str] = Field(description="метрики словаря с этим источником")
    kpis_in_zone: int = Field(description="KPI зоны пользователя на метриках источника")


class EventOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str = Field(examples=["E-000123"])
    ts: str = Field(examples=["2026-11-11T00:00:00+03:00"])
    source: Source
    type: str = Field(examples=["annotation"], description="annotation — внешнее событие, объясняющее скачок")
    order_id: str | None = None
    customer_id: str | None = None
    node_id: int | None = None
    stage: int | None = None
    payload: dict[str, Any] = Field(
        examples=[{"label": "Запуск новой обложки",
                   "targets": [{"node_id": 7, "node": "Сборка", "kpi": "defect_rate"}],
                   "dims": {"product_line": "Выпускные альбомы", "brand": "ФФ РФ"}}]
    )
    synthetic: bool = True


class EventsOut(BaseModel):
    total: int
    items: list[EventOut] = Field(description="новые сверху")


class StageOwner(BaseModel):
    node_id: int | None = None
    node_name: str | None = Field(default=None, examples=["Сборка"])
    login: str | None = None


class ResultCheck(BaseModel):
    criterion: str = Field(examples=["изготовлено за 24 ч и принято ОТК"])
    passed: bool | None = Field(default=None, description="null — этап ещё не закончен")
    checked_at: str | None = None


class OrderStage(BaseModel):
    model_config = ConfigDict(extra="allow")

    stage: int = Field(ge=1, le=8, examples=[5])
    name: str = Field(examples=["Производство"])
    source: Source
    event_id: str | None = Field(default=None, description="событие этапа; null — этап не начат или вне зоны")
    status: StageStatus
    owner: StageOwner
    result_check: ResultCheck | None = Field(default=None, description="null — этап узла вне зоны")
    issue: str | None = Field(default=None, examples=["брак"])
    started_at: str | None = None
    due_at: str | None = None
    finished_at: str | None = None
    overdue: bool | None = None
    visible: bool = Field(description="false — этап узла вне зоны: без события, проверки и времени")


class OrderIssue(BaseModel):
    stage: int
    issue: str


class OrderOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    order_id: str = Field(examples=["ORD-000123"])
    customer_id: str = Field(examples=["C-0042"])
    product_line: str | None = Field(default=None, examples=["Выпускные альбомы"])
    brand: str | None = Field(default=None, examples=["ФФ РФ"])
    segment: str | None = Field(default=None, examples=["B2B"])
    created_at: str
    status: OrderStatus
    current_stage: int | None = None
    stages: list[OrderStage]
    issues: list[OrderIssue]
    prev_order_id: str | None = None
    next_order_id: str | None = Field(
        default=None, description="этап 8 «Возврат» ведёт на следующий заказ того же клиента"
    )
    synthetic: bool = True


class OrderStageBrief(BaseModel):
    stage: int
    status: StageStatus
    overdue: bool | None = None
    visible: bool


class OrderBrief(BaseModel):
    order_id: str
    customer_id: str
    product_line: str | None = None
    brand: str | None = None
    segment: str | None = None
    created_at: str
    status: OrderStatus
    current_stage: int | None = None
    issues: list[OrderIssue]
    stages: list[OrderStageBrief]
    prev_order_id: str | None = None
    next_order_id: str | None = None
    synthetic: bool = True


class OrdersOut(BaseModel):
    total: int
    items: list[OrderBrief] = Field(description="новые сверху")


class FlowStage(BaseModel):
    stage: int
    name: str = Field(examples=["Производство"])
    focus: str = Field(examples=["очередь / готовность"])
    source: Source
    owner: StageOwner
    norm_hours: float
    criterion: str
    visible: bool = Field(description="false — этап узла вне зоны: цифр нет")
    orders: int | None = None
    pending: int | None = None
    in_work: int | None = None
    overdue: int | None = None
    done: int | None = None
    late: int | None = None
    defect: int | None = None
    checked: int | None = None
    passed_share: float | None = Field(default=None, description="доля прошедших проверку среди проверенных")
    problems: int | None = None


class Bottleneck(BaseModel):
    stage: int
    name: str
    overdue: int
    in_work: int


class FlowSummaryOut(BaseModel):
    now: str
    orders_total: int
    in_progress: int
    completed: int
    stages: list[FlowStage]
    bottleneck: Bottleneck | None = Field(default=None, description="этап с наибольшим числом просроченных")
    synthetic: bool = True


class TileKpi(BaseModel):
    node_id: int
    node_name: str
    kpi: str
    title: str
    value: float | None = None
    value_date: str | None = None
    unit: str
    status: Status
    severity: float
    delta_week: float | None = Field(default=None, description="значение минус значение неделей раньше")
    trend: Literal["up", "down", "flat"] | None = None
    trend_quality: Literal["improving", "worsening", "stable"] | None = None


class TileRisk(BaseModel):
    at_risk: bool
    horizon: int = Field(examples=[14])
    in_days: int | None = Field(default=None, description="через сколько суток прогноз пересечёт порог")
    date: str | None = None
    level: Literal["warn", "crit"] | None = None
    node_id: int | None = None
    node_name: str | None = None
    kpi: str | None = None
    title: str | None = None


class TileOut(BaseModel):
    key: str = Field(examples=["quality"])
    title: str = Field(examples=["Качество"])
    stage: int | None = None
    priority: Priority
    order: int
    status: Status
    kpis: int
    kpi_statuses: dict[str, int]
    main_kpi: TileKpi | None = None
    forecast_risk: TileRisk
    open_deviations: int
    deviation_ids: list[str]


class OverviewOut(BaseModel):
    now: str
    user: str
    units: Units
    zone_nodes: int
    tiles: list[TileOut] = Field(description="8 плиток в порядке приоритета «срок → качество → себестоимость»")
    portfolio: PortfolioSummary


# --- конструктор: проверка и импорт (Ф7) ----------------------------------------


class ProblemOut(BaseModel):
    code: str = Field(examples=["weights_sum"])
    severity: Literal["error", "warning"]
    message: str
    node_id: int | None = None
    node_name: str | None = None
    kpi: str | None = None
    link_id: str | None = None


class ValidateOut(BaseModel):
    ok: bool = Field(description="ошибок нет (предупреждения допустимы)")
    errors: int
    warnings: int
    problems: list[ProblemOut]


class ChangeSet(BaseModel):
    add: list[str]
    remove: list[str]
    update: list[str]


class ImportChanges(BaseModel):
    nodes: ChangeSet
    kpis: ChangeSet
    links: ChangeSet
    changed: bool


class ImportOut(BaseModel):
    dry_run: bool
    applied: bool
    changes: ImportChanges

