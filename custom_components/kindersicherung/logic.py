"""Reine Logik ohne Home-Assistant-Abhängigkeit (leicht testbar)."""

from __future__ import annotations

from datetime import datetime, time, timedelta

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_time(value: str) -> time:
    """Parst 'HH:MM' oder 'HH:MM:SS'."""
    return time.fromisoformat(value)


def is_in_window(
    now: datetime,
    start: str,
    end: str,
    weekdays: list[str],
) -> bool:
    """Prüft, ob `now` im Zeitfenster und an einem gewählten Wochentag liegt.

    - start == end bedeutet: ganztägig.
    - start > end bedeutet: Fenster über Mitternacht (z. B. 20:00-06:00).
    - Der Wochentag bezieht sich immer auf den aktuellen Tag.
    """
    if WEEKDAY_KEYS[now.weekday()] not in weekdays:
        return False
    start_t = parse_time(start)
    end_t = parse_time(end)
    current = now.time().replace(tzinfo=None)
    if start_t == end_t:
        return True
    if start_t < end_t:
        return start_t <= current < end_t
    return current >= start_t or current < end_t


def attempts_after_failure(
    attempts: int,
    last_failure: datetime | None,
    now: datetime,
    reset_minutes: int,
) -> int:
    """Neuer Fehlversuchs-Zähler nach einem weiteren Fehlversuch.

    Liegt der letzte Fehlversuch länger als `reset_minutes` zurück
    (und ist `reset_minutes` > 0), beginnt die Zählung bei 1.
    """
    if reset_minutes > 0 and last_failure is not None:
        if now - last_failure > timedelta(minutes=reset_minutes):
            attempts = 0
    return attempts + 1
