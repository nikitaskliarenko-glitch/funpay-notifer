"""Хранение фильтров и состояния предложений в SQLite."""

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from funpay_watch.models import Filters, OfferState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS offer_state (
    offer_id            TEXT PRIMARY KEY,
    price_usd           TEXT    NOT NULL,
    stock               INTEGER NOT NULL,
    matched             INTEGER NOT NULL,
    last_notified_price TEXT,
    last_seen           REAL    NOT NULL
);
"""

DEFAULT_FILTERS = Filters(
    min_stock=1,
    # Звёзды в списке округлены вниз, поэтому порог 5 отсёк бы продавца
    # с настоящим рейтингом 4.8. Четвёрка по умолчанию честнее.
    min_stars=4,
    min_reviews=100,
    max_price=Decimal("0.0080"),
    min_tenure_months=12,
    only_online=False,
)


def _encode_optional_int(value: int | None) -> str:
    return "" if value is None else str(value)


def _decode_optional_int(text: str) -> int | None:
    return None if text == "" else int(text)


# Как каждое поле фильтра кладётся в текстовую колонку и читается обратно.
_CODECS = {
    "min_stock": (str, int),
    "min_stars": (_encode_optional_int, _decode_optional_int),
    "min_reviews": (str, int),
    "max_price": (str, Decimal),
    "min_tenure_months": (str, int),
    "only_online": (lambda v: "1" if v else "0", lambda s: s == "1"),
}

FILTER_NAMES = tuple(_CODECS)


class Storage:
    def __init__(self, path: str | Path) -> None:
        self._db = sqlite3.connect(path, isolation_level=None)
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def _get_setting(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _set_setting(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_filters(self) -> Filters:
        values = {}
        for name, (_, decode) in _CODECS.items():
            stored = self._get_setting(name)
            values[name] = getattr(DEFAULT_FILTERS, name) if stored is None else decode(stored)
        return Filters(**values)

    def update_filter(self, name: str, value) -> None:
        if name not in _CODECS:
            raise ValueError(f"неизвестный фильтр {name!r}")
        encode, _ = _CODECS[name]
        self._set_setting(name, encode(value))

    def is_enabled(self) -> bool:
        return self._get_setting("enabled") == "1"

    def set_enabled(self, value: bool) -> None:
        self._set_setting("enabled", "1" if value else "0")

    def load_states(self) -> dict[str, OfferState]:
        rows = self._db.execute(
            "SELECT offer_id, price_usd, stock, matched, last_notified_price FROM offer_state"
        )
        return {
            offer_id: OfferState(
                offer_id=offer_id,
                price_usd=Decimal(price),
                stock=stock,
                matched=bool(matched),
                last_notified_price=Decimal(notified) if notified is not None else None,
            )
            for offer_id, price, stock, matched, notified in rows
        }

    def save_cycle(self, states: Iterable[OfferState], now: datetime) -> None:
        """Записывает итог цикла.

        Предложения, пропавшие из выдачи, перестают считаться подходящими,
        чтобы при возвращении сработал переход и уведомление пришло заново.
        """
        seen_at = now.timestamp()
        with self._db:
            self._db.execute("BEGIN")
            self._db.execute("UPDATE offer_state SET matched = 0")
            self._db.executemany(
                "INSERT INTO offer_state"
                " (offer_id, price_usd, stock, matched, last_notified_price, last_seen)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(offer_id) DO UPDATE SET"
                "   price_usd = excluded.price_usd,"
                "   stock = excluded.stock,"
                "   matched = excluded.matched,"
                "   last_notified_price = excluded.last_notified_price,"
                "   last_seen = excluded.last_seen",
                [
                    (
                        s.offer_id,
                        str(s.price_usd),
                        s.stock,
                        int(s.matched),
                        None if s.last_notified_price is None else str(s.last_notified_price),
                        seen_at,
                    )
                    for s in states
                ],
            )

    def clear_states(self) -> None:
        """Забывает всю выдачу, чтобы следующий цикл прошёл как первый."""
        self._db.execute("DELETE FROM offer_state")

    def prune(self, older_than: timedelta, now: datetime) -> int:
        cutoff = (now - older_than).timestamp()
        cursor = self._db.execute("DELETE FROM offer_state WHERE last_seen < ?", (cutoff,))
        return cursor.rowcount
