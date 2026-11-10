"""Reine Logik ohne Home-Assistant-Abhängigkeit (leicht testbar)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# Wochentage als Liste ("mon", ...) oder eine Funktion Datum -> gilt an diesem Tag.
DaySpec = list[str] | Callable[[date], bool]


def day_applies(days: DaySpec, day: date) -> bool:
    """Gilt ein Fenster, das an `day` beginnt?"""
    if callable(days):
        return bool(days(day))
    return WEEKDAY_KEYS[day.weekday()] in days


def school_window_day(start: str, day: date) -> date:
    """Auf welchen Schultag sich ein Fenster bezieht, das an `day` beginnt.

    Beginnt es ab 12:00 (z. B. 21:00 bis 07:30), ist es der Abend vor dem
    Schultag, also zählt der Folgetag. Sonst der Tag selbst (z. B. 00:00 bis 19:00).
    """
    return day + timedelta(days=1) if parse_time(start) >= time(12, 0) else day


def parse_time(value: str) -> time:
    """Parst 'HH:MM' oder 'HH:MM:SS'."""
    return time.fromisoformat(value)


def is_in_window(
    now: datetime,
    start: str,
    end: str,
    weekdays: DaySpec,
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
    today = now.date()
    if start_t == end_t:
        return day_applies(weekdays, today)
    if start_t < end_t:
        return start_t <= current < end_t and day_applies(weekdays, today)
    if current >= start_t:
        return day_applies(weekdays, today)
    if current < end_t:
        return day_applies(weekdays, today - timedelta(days=1))
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
    if (
        reset_minutes > 0
        and last_failure is not None
        and now - last_failure > timedelta(minutes=reset_minutes)
    ):
        attempts = 0
    return attempts + 1


Window = tuple[str, str, DaySpec]


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
        for start, end, days in windows:
            if not day_applies(days, day):
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


def app_blocked(app: str | None, blocked: list[str], allowed: list[str]) -> bool:
    """Gesperrt, außer ein erlaubter Eintrag passt (z. B. youtube, aber nicht tvkids)."""
    return app_matches(app, blocked) and not app_matches(app, allowed)


def daily_limit_for(
    base: int, weekend: int | None, holiday: int | None, is_weekend: bool, is_holiday: bool
) -> int:
    """Tageslimit für heute: Ferien vor Wochenende vor normal. None = wie normal."""
    if is_holiday and holiday is not None:
        return holiday
    if is_weekend and weekend is not None:
        return weekend
    return base


def holiday_dates(
    events: list[tuple[datetime | date, datetime | date]], first: date, days: int
) -> set[date]:
    """Tage zwischen `first` und `first + days`, die ein Termin berührt.

    Ganztägige Termine haben ein exklusives Ende (Ende = Tag nach dem letzten Tag).
    """
    result: set[date] = set()
    for start, end in events:
        if isinstance(start, datetime):
            begin_day = start.date()
            # Ende genau um Mitternacht zählt nicht mehr zum Folgetag.
            last_day = (end - timedelta(microseconds=1)).date()
        else:
            begin_day = start
            last_day = end - timedelta(days=1)
        for offset in range(days):
            day = first + timedelta(days=offset)
            if begin_day <= day <= last_day:
                result.add(day)
    return result


# ----------------------------------------------------------------------
# Entscheidung: Was gilt gerade? (eine Stelle für Status und Durchsetzung)
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class RuleState:
    """Alles, was die Entscheidung braucht (ohne Home Assistant)."""

    enabled: bool = True
    locked: bool = False
    away: bool = False
    exception_active: bool = False
    bonus_active: bool = False
    in_window: bool = False
    paused: bool = False
    limit_reached: bool = False
    has_blocked_apps: bool = False
    app_block_always: bool = False
    app_released: bool = False


@dataclass(frozen=True)
class Decision:
    """Ergebnis von `evaluate`."""

    status: str
    restricted: bool
    apps_blocked: bool


def evaluate(state: RuleState) -> Decision:
    """Status, ob Regeln gelten (Bestätigung nötig) und ob Apps gesperrt sind."""
    if not state.enabled:
        return Decision("off", False, False)
    restricted = not state.exception_active and (
        state.limit_reached
        or (state.in_window and not state.paused and not state.bonus_active)
    )
    apps_blocked = (
        state.has_blocked_apps
        and not state.exception_active
        and not state.app_released
        and (state.app_block_always or restricted)
    )
    if state.locked:
        status = "locked"
    elif state.away and not state.exception_active:
        status = "away"
    elif state.exception_active:
        status = "exception"
    elif state.limit_reached:
        status = "limit"
    elif state.in_window and state.bonus_active and not state.paused:
        status = "bonus"
    elif state.in_window:
        status = "paused" if state.paused else "window"
    else:
        status = "free"
    return Decision(status, restricted, apps_blocked)


# ----------------------------------------------------------------------
# Sitzungen: Gilt ein laufender Fernseher als freigegeben?
# ----------------------------------------------------------------------
SESSION_FREE = "free"  # eingeschaltet, als keine Regeln galten
SESSION_NEW = "new"  # braucht eine Bestätigung, sobald Regeln gelten
SESSION_CONFIRMED = "confirmed"

AT_START_OFF = "off"
AT_START_CONFIRM = "confirm"
AT_START_NONE = "none"
AT_START_OPTIONS = [AT_START_OFF, AT_START_CONFIRM, AT_START_NONE]

ACTION_OK = "ok"
ACTION_CONFIRM = "confirm"
ACTION_TURN_OFF = "turn_off"


@dataclass
class Session:
    """Freigabe eines Fernsehers, bis er länger aus war."""

    status: str = SESSION_NEW
    off_since: datetime | None = None
    confirmed_until: datetime | None = None
    retry_after: datetime | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Zum Speichern."""
        return {
            "status": self.status,
            "off_since": self.off_since.isoformat() if self.off_since else None,
            "confirmed_until": self.confirmed_until.isoformat()
            if self.confirmed_until
            else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """Aus dem Speicher."""

        def parse(key: str) -> datetime | None:
            raw = data.get(key)
            return datetime.fromisoformat(raw) if raw else None

        status = data.get("status")
        if status not in (SESSION_FREE, SESSION_NEW, SESSION_CONFIRMED):
            status = SESSION_NEW
        return cls(status, parse("off_since"), parse("confirmed_until"))


def update_session(
    session: Session,
    active: bool,
    now: datetime,
    restricted: bool,
    gap: timedelta,
) -> None:
    """Sitzung an den aktuellen Zustand anpassen.

    Aus oder nicht verfügbar zählt gleich. Erst wenn ein Fernseher länger als
    `gap` aus war, beginnt beim Einschalten eine neue Sitzung. So stört ein
    kurzes Flackern zwischen „aus“ und „nicht verfügbar“ nicht, und ein
    Einschalten aus „nicht verfügbar“ wird genauso geprüft wie aus „aus“.
    """
    if not active:
        if session.off_since is None:
            session.off_since = now
        session.retry_after = None
        return
    if session.off_since is not None:
        if now - session.off_since >= gap:
            session.status = SESSION_NEW
            session.confirmed_until = None
        session.off_since = None
    if not restricted:
        # Regeln vorbei: Freigaben enden, der nächste Beginn prüft neu.
        session.status = SESSION_FREE
        session.confirmed_until = None
    elif (
        session.status == SESSION_CONFIRMED
        and session.confirmed_until is not None
        and now >= session.confirmed_until
    ):
        session.status = SESSION_NEW
        session.confirmed_until = None


def session_action(session: Session, restricted: bool, at_start: str) -> str:
    """Was mit einem laufenden Fernseher passieren soll."""
    if not restricted or session.status == SESSION_CONFIRMED:
        return ACTION_OK
    if session.status == SESSION_FREE:
        # Lief schon, bevor die Regeln begannen (z. B. Beginn des Zeitfensters).
        if at_start == AT_START_OFF:
            return ACTION_TURN_OFF
        if at_start == AT_START_CONFIRM:
            return ACTION_CONFIRM
        return ACTION_OK
    return ACTION_CONFIRM
