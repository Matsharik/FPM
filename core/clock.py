"""Сервис часов (Р8): единственный источник «сейчас» для всего бэкенда.

Время хранится в ``data/meta.json`` и само не идёт: оно меняется только через
``set``/``advance`` (демо-перемотка). Так повторный прогон сценария даёт
одинаковые метки времени и цифры на любой машине. В продакшне на месте этого
класса — системное время.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from network.meta import Meta

from .errors import BadRequest


class Clock:
    def __init__(self, meta: Meta, default_now: datetime, tz: timezone) -> None:
        self._meta = meta
        self._default = default_now
        self.tz = tz

    def now(self) -> datetime:
        """Текущее демо-время в часовом поясе стенда."""
        stored = self._meta.clock_now
        value = datetime.fromisoformat(stored) if stored else self._default
        return value.astimezone(self.tz)

    def iso(self) -> str:
        return self.now().isoformat()

    def today(self) -> date:
        """Текущие местные сутки (они ещё не закрыты)."""
        return self.now().date()

    def local_date(self, moment: datetime) -> date:
        """Местная дата произвольного момента времени."""
        return moment.astimezone(self.tz).date()

    def day_start(self, day: date) -> datetime:
        """Начало местных суток ``day``."""
        return datetime(day.year, day.month, day.day, tzinfo=self.tz)

    def set(self, value: datetime | str) -> datetime:
        """Установить время; строка — ISO 8601 с часовым поясом."""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                raise BadRequest(f"некорректное время: {value!r}", code="invalid_time") from None
        if value.utcoffset() is None:
            raise BadRequest(
                "время должно быть с часовым поясом, например 2026-11-23T09:00:00+03:00",
                code="invalid_time",
            )
        value = value.astimezone(self.tz)
        self._meta.set_clock(value.isoformat())
        return value

    def advance(self, days: int = 0, hours: int = 0) -> datetime:
        """Перевести часы вперёд. Назад время не идёт."""
        delta = timedelta(days=days, hours=hours)
        if delta <= timedelta(0):
            raise BadRequest("перемотка возможна только вперёд", code="invalid_advance")
        return self.set(self.now() + delta)

    def reset(self) -> datetime:
        """Вернуть время по умолчанию из настроек."""
        return self.set(self._default)
