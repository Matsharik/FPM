"""Workspace — точка сборки: конфигурация, данные и сервисы одного стенда.

Один процесс держит один ``Workspace`` (Р10: ``workers=1``). Все сервисы делят
общий замок ``lock``, поэтому составные операции над несколькими файлами
выполняются последовательно.
"""

from __future__ import annotations

import os
from pathlib import Path

from network.meta import Meta
from network.network import QualityNetwork

from .access import AccessService
from .analysis import Analysis
from .audit import AuditLog
from .clock import Clock
from .demo import Demo
from .deviations import DeviationService
from .events import EventService
from .forecast import Forecaster
from .glossary import Glossary
from .kpi import KpiService
from .orders import OrderService
from .orgio import OrgIO
from .orgconfig import load_playbook
from .overview import Overview
from .people import People
from .settings import Settings, load_settings
from .sources import Sources
from .visibility import CardVisibility

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ENV = "QNET_ROOT"
CONFIG_ENV = "QNET_CONFIG"


def default_config_dir() -> Path:
    return Path(os.environ.get(CONFIG_ENV) or PROJECT_ROOT / "config")


def default_data_dir() -> Path:
    return Path(os.environ.get(DATA_ENV) or PROJECT_ROOT / "data")


class Workspace:
    def __init__(
        self,
        config_dir: str | os.PathLike[str] | None = None,
        data_dir: str | os.PathLike[str] | None = None,
    ) -> None:
        self.config_dir = Path(config_dir) if config_dir is not None else default_config_dir()
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.settings: Settings = load_settings(self.config_dir / "settings.yaml")
        self.meta = Meta(self.data_dir)
        self.clock = Clock(self.meta, self.settings.clock.default_now, self.settings.clock.tz)
        self.net = QualityNetwork(self.data_dir, meta=self.meta)
        self.lock = self.net._lock  # общий замок: сеть и сервисы над ней
        self.audit = AuditLog(self.data_dir, self.clock)
        self.glossary = Glossary(self.config_dir / "glossary.yaml", self.data_dir, self.settings)
        self.kpi = KpiService(self.net, self.glossary, self.clock, self.settings)
        # Р6: цвет KPI и узла считается по порогам словаря, флажки — запасной вариант.
        self.net.set_status_resolver(self.kpi.status)
        self.analysis = Analysis(self.net, self.kpi, self.settings)
        self.forecast = Forecaster(self.kpi)
        self.playbook = load_playbook(self.config_dir / "playbook.yaml")
        self.deviations = DeviationService(self)
        self.demo = Demo(self)
        self.access = AccessService(self)
        self.visibility = CardVisibility(self)
        self.people = People(self)
        self.sources = Sources(self)
        self.events = EventService(self)
        self.orders = OrderService(self)
        self.overview = Overview(self)
        self.orgio = OrgIO(self)
        self.audit.role_of = self._role_of

    def _role_of(self, login: str) -> str | None:
        user = self.access.find(login)
        return user.role if user is not None else None

    def has_data(self) -> bool:
        """Есть ли уже собранные данные (иначе ``run.py`` запускает сид)."""
        return (self.data_dir / "meta.json").is_file()
