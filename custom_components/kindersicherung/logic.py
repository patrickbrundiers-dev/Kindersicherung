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
    - start > end bedeutet: Fenster über Mitternacht (z. B. 21:00-07:30).
      Der Teil nach Mitternacht gehört zum Starttag: Ist nur Montag gewählt,
      gilt das Fenster von Montag 21:00 bis Dienstag 07:30.
    - Sonst bezieht sich der Wochentag auf den aktuellen Tag.
    """
    start_t = parse_time(start)
    end_t = parse_time(end)
    current = now.time().replace(tzinfo=None)
    today = WEEKDAY_KEYS[now.weekday()]
    if start_t == end_t:
        return today in weekdays
    if start_t < end_t:
        return today in weekdays and start_t <= current < end_t
    if current >= start_t:
        return today in weekdays
    if current < end_t:
        return WEEKDAY_KEYS[(now.weekday() - 1) % 7] in weekdays
    return False


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


Window = tuple[str, str, list[str]]


def is_in_any_window(now: datetime, windows: list[Window]) -> bool:
    """Liegt `now` in mindestens einem Zeitfenster?"""
    return any(is_in_window(now, start, end, days) for start, end, days in windows)


def window_intervals(
    now: datetime, windows: list[Window], days_back: int = 1, days_ahead: int = 2
) -> list[tuple[datetime, datetime]]:
    """Konkrete Zeiträume (Beginn, Ende) der Fenster rund um `now`.

    Gleiche Start- und Endzeit ergibt den ganzen Kalendertag, ein Fenster
    über Mitternacht endet am Folgetag (passend zu `is_in_window`).
    """
    tz = now.tzinfo
    result: list[tuple[datetime, datetime]] = []
    for offset in range(-days_back, days_ahead + 1):
        day = now.date() + timedelta(days=offset)
        key = WEEKDAY_KEYS[day.weekday()]
        for start, end, days in windows:
            if key not in days:
                continue
            start_t = parse_time(start)
            end_t = parse_time(end)
            if start_t == end_t:
                begin = datetime.combine(day, time(0, 0), tz)
                finish = begin + timedelta(days=1)
            else:
                begin = datetime.combine(day, start_t, tz)
                finish = datetime.combine(day, end_t, tz)
                if start_t > end_t:
                    finish += timedelta(days=1)
            result.append((begin, finish))
    result.sort()
    return result


def next_midnight(now: datetime) -> datetime:
    """Nächste Mitternacht nach `now` (gleiche Zeitzone)."""
    return datetime.combine(now.date() + timedelta(days=1), time(0, 0), now.tzinfo)


def exception_until(now: datetime, windows: list[Window]) -> datetime:
    """Ende einer Ausnahme „heute erlauben“.

    Mindestens bis Mitternacht, und bis zum Ende jedes Fensters, das jetzt
    läuft oder heute noch beginnt (z. B. 21:00 bis 07:30 am nächsten Morgen).
    """
    midnight = next_midnight(now)
    until = midnight
    for begin, finish in window_intervals(now, windows):
        if finish > now and begin < midnight:
            until = max(until, finish)
    return until


def starts_at(moment: datetime, windows: list[Window], minutes_before: int = 0) -> bool:
    """Beginnt um `moment` (+ `minutes_before`) ein Fenster? Minutengenau."""
    target = moment.replace(second=0, microsecond=0) + timedelta(minutes=minutes_before)
    return any(
        begin == target
        for begin, _ in window_intervals(moment, windows, days_back=0, days_ahead=1)
    )


def app_matches(app: str | None, blocked: list[str]) -> bool:
    """Passt der App-Name oder die App-ID zu einem gesperrten Eintrag?"""
    if not app:
        return False
    value = app.lower()
    return any(entry.strip().lower() in value for entry in blocked if entry.strip())
