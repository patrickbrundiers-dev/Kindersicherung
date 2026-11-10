"""Steuerung der Kindersicherung (ersetzt die frühere Automation).

Aufbau:
- `logic.py` entscheidet, was gerade gilt (reine Funktionen, ohne Home Assistant).
- `devices.py` schaltet Fernseher aus und drückt die Home-Taste.
- `notifier.py` verschickt Nachrichten.
- Dieser Controller hält den Zustand, speichert ihn und setzt die Entscheidung
  durch: bei jeder Zustandsänderung eines Fernsehers und jede Minute.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import time
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import devices
from .const import (
    APP_ACTION_PREFIX,
    CONF_ACTIONABLE,
    CONF_ALLOWED_APPS,
    CONF_ANNOUNCE_LOCK,
    CONF_APP_BLOCK_ALWAYS,
    CONF_APP_RELEASE_MINUTES,
    CONF_AT_START,
    CONF_ATTEMPT_RESET_MINUTES,
    CONF_BLOCKED_APPS,
    CONF_BONUS_MINUTES,
    CONF_CONFIRM_CODE,
    CONF_CONFIRM_ENTITIES,
    CONF_CONFIRM_TIMEOUT,
    CONF_CONFIRM_VALID_MINUTES,
    CONF_DAILY_LIMIT_HOLIDAY,
    CONF_DAILY_LIMIT_MINUTES,
    CONF_DAILY_LIMIT_WEEKEND,
    CONF_HOLIDAY_CALENDARS,
    CONF_LOCK_MINUTES,
    CONF_MAX_ATTEMPTS,
    CONF_MEDIA_PLAYERS,
    CONF_MESSAGE,
    CONF_PAUSE_ENTITIES,
    CONF_PENALTY_HOURS,
    CONF_SCHOOL_NIGHTS,
    CONF_TIME_END,
    CONF_TIME_END_2,
    CONF_TIME_START,
    CONF_TIME_START_2,
    CONF_TURN_OFF_AT_START,
    CONF_WARN_MINUTES,
    CONF_WEEKDAYS,
    CONF_WEEKDAYS_2,
    CONF_WORKDAY_ENTITY,
    CONFIRM_ACTION_PREFIX,
    DEFAULT_ACTIONABLE,
    DEFAULT_ANNOUNCE_LOCK,
    DEFAULT_APP_RELEASE_MINUTES,
    DEFAULT_ATTEMPT_RESET_MINUTES,
    DEFAULT_BONUS_MINUTES,
    DEFAULT_CONFIRM_TIMEOUT,
    DEFAULT_CONFIRM_VALID_MINUTES,
    DEFAULT_DAILY_LIMIT_MINUTES,
    DEFAULT_LOCK_MINUTES,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MESSAGE,
    DEFAULT_PENALTY_HOURS,
    DEFAULT_TIME_END,
    DEFAULT_TIME_END_2,
    DEFAULT_TIME_START,
    DEFAULT_TIME_START_2,
    DEFAULT_WARN_MINUTES,
    DOMAIN,
    EVENT_ACTION,
    EVENT_CONFIRMED,
    EVENT_FAILED,
    EVENT_LOCKED,
    EVENT_UNLOCKED,
    IDLE_APPS,
    MOBILE_APP_ACTION_EVENT,
    STAT_KEYS,
    STORAGE_VERSION,
    WEEKDAYS,
)
from .logic import (
    ACTION_CONFIRM,
    ACTION_TURN_OFF,
    AT_START_NONE,
    AT_START_OFF,
    AT_START_OPTIONS,
    SESSION_CONFIRMED,
    SESSION_FREE,
    SESSION_NEW,
    Decision,
    RuleState,
    Session,
    Window,
    app_blocked,
    app_matches,
    attempts_after_failure,
    daily_limit_for,
    evaluate,
    exception_until,
    holiday_dates,
    is_in_any_window,
    school_window_day,
    session_action,
    starts_at,
    update_session,
)
from .notifier import TAG_APP, TAG_CONFIRM, Notifier

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

BLOCK_NOTICE_INTERVAL = 60
SCREEN_TIME_SAVE_DELAY = 60
# So lange darf ein Fernseher aus oder nicht verfügbar sein, ohne dass seine
# Freigabe endet (Android TV flackert zwischen „aus“ und „nicht verfügbar“).
SESSION_GAP = timedelta(minutes=2)
# Nach einem Fehlschlag wird ein weiter laufender Fernseher frühestens
# nach dieser Zeit erneut abgefragt (das Ausschalten läuft ja noch).
RETRY_DELAY = timedelta(seconds=60)
# Nach der Home-Taste so lange warten, dann prüfen, ob die App noch läuft.
APP_CHECK_DELAY = 5.0
# Schultage und Ferien so oft neu laden (Kalender können sich ändern).
SCHOOL_REFRESH = timedelta(minutes=30)
SCHOOL_DAYS_AHEAD = 4



class KindersicherungController:
    """Verwaltet Bestätigung, Fehlversuche und Sperre für einen Eintrag."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialisiere den Controller."""
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.notifier = Notifier(hass, entry.entry_id, lambda: self.entry.options)
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._unlock_unsub: Callable[[], None] | None = None
        self._flow_task: asyncio.Task[None] | None = None
        self._flow_players: set[str] = set()
        self._confirm_event: asyncio.Event | None = None
        self._turning_off: set[str] = set()
        self._went_off: set[str] = set()
        self._closing: set[str] = set()
        self._tick_lock = asyncio.Lock()
        self._last_block_notice = float("-inf")
        self._last_app_notice = float("-inf")
        self._confirm_ok = False
        self._wrong_code = False

        self.loaded_options: dict[str, Any] = dict(entry.options)
        self.stats: dict[str, int] = dict.fromkeys(STAT_KEYS, 0)
        self.sessions: dict[str, Session] = {}
        self.enabled = True
        self.confirmed = False
        self.attempts = 0
        self.last_failure: datetime | None = None
        self.lock_until: datetime | None = None
        self.exception_until: datetime | None = None
        self.app_release_until: datetime | None = None
        self.screen_time_date: str | None = None
        self.screen_time_minutes = 0
        self.limit_reached = False
        self.bonus_minutes_today = 0
        self.bonus_until: datetime | None = None
        # Schultage (B): Datum -> Schultag?, Ferientage, letzter Abruf
        self._school_days: dict[date, bool] = {}
        self._holidays: set[date] = set()
        self._school_loaded: datetime | None = None
        self._school_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Konfiguration
    # ------------------------------------------------------------------
    @property
    def _opts(self) -> dict[str, Any]:
        return self.entry.options

    @property
    def media_players(self) -> list[str]:
        """Überwachte Media Player."""
        return list(self._opts.get(CONF_MEDIA_PLAYERS, []))

    @property
    def confirm_entities(self) -> list[str]:
        """Zusätzliche, externe Bestätigungs-Entitäten."""
        # Eigene Entitäten dieser Integration ignorieren (Endlosschleife vermeiden).
        return [
            entity_id
            for entity_id in self._opts.get(CONF_CONFIRM_ENTITIES, [])
            if self._entity_registry_platform(entity_id) != DOMAIN
        ]

    @property
    def confirm_code(self) -> str:
        """Eingestellter Zahlencode (leer = nur Schalter/Button)."""
        return str(self._opts.get(CONF_CONFIRM_CODE) or "").strip()

    @property
    def max_attempts(self) -> int:
        """Fehlversuche bis zur Sperre."""
        return int(self._opts.get(CONF_MAX_ATTEMPTS, DEFAULT_MAX_ATTEMPTS))

    @property
    def lock_minutes(self) -> int:
        """Dauer der Sperre in Minuten."""
        return int(self._opts.get(CONF_LOCK_MINUTES, DEFAULT_LOCK_MINUTES))

    @property
    def confirm_timeout(self) -> int:
        """Wartezeit auf die Bestätigung in Sekunden."""
        return int(self._opts.get(CONF_CONFIRM_TIMEOUT, DEFAULT_CONFIRM_TIMEOUT))

    @property
    def windows(self) -> list[Window]:
        """Zeitfenster (erstes immer, zweites nur mit gewählten Wochentagen)."""
        start = self._opts.get(CONF_TIME_START, DEFAULT_TIME_START)
        days: Any = list(self._opts.get(CONF_WEEKDAYS, WEEKDAYS))
        if self.school_nights:
            # Nur vor Schultagen (bzw. an Schultagen, wenn das Fenster vormittags beginnt).
            def days(day: date, start: str = start) -> bool:
                return self.is_school_day(school_window_day(start, day))

        result: list[Window] = [
            (start, self._opts.get(CONF_TIME_END, DEFAULT_TIME_END), days)
        ]
        if days_2 := list(self._opts.get(CONF_WEEKDAYS_2) or []):
            result.append(
                (
                    self._opts.get(CONF_TIME_START_2, DEFAULT_TIME_START_2),
                    self._opts.get(CONF_TIME_END_2, DEFAULT_TIME_END_2),
                    days_2,
                )
            )
        return result

    @property
    def at_start(self) -> str:
        """Was bei Beginn der Regeln mit einem laufenden Fernseher passiert."""
        value = self._opts.get(CONF_AT_START)
        if value in AT_START_OPTIONS:
            return value
        # Ältere Einträge: Schalter „Bei Beginn des Zeitfensters ausschalten“.
        return AT_START_OFF if self._opts.get(CONF_TURN_OFF_AT_START) else AT_START_NONE

    @property
    def blocked_apps(self) -> list[str]:
        """Apps, die beendet werden."""
        return list(self._opts.get(CONF_BLOCKED_APPS) or [])

    @property
    def pause_entities(self) -> list[str]:
        """Entitäten, die die Zeitfenster aussetzen (z. B. Ferien)."""
        return list(self._opts.get(CONF_PAUSE_ENTITIES) or [])

    @property
    def warn_minutes(self) -> int:
        """Vorwarnung in Minuten (0 = aus)."""
        return int(self._opts.get(CONF_WARN_MINUTES, DEFAULT_WARN_MINUTES) or 0)

    @property
    def school_nights(self) -> bool:
        """Erstes Zeitfenster nur vor Schultagen?"""
        return bool(self._opts.get(CONF_SCHOOL_NIGHTS, False))

    @property
    def workday_entity(self) -> str | None:
        """Werktag-Sensor (Workday-Integration)."""
        return self._opts.get(CONF_WORKDAY_ENTITY) or None

    @property
    def holiday_calendars(self) -> list[str]:
        """Kalender mit Schulferien."""
        return list(self._opts.get(CONF_HOLIDAY_CALENDARS) or [])

    def is_school_day(self, day: date) -> bool:
        """Schultag: Werktag laut Sensor (sonst Mo bis Fr) und nicht in den Ferien."""
        if day in self._holidays:
            return False
        if day in self._school_days:
            return self._school_days[day]
        return day.weekday() < 5

    @property
    def holiday_today(self) -> bool:
        """Ferien heute (Ferienkalender oder Pause-Entität an)?"""
        return dt_util.now().date() in self._holidays or self.paused

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return None if value is None or value == "" else int(value)

    @property
    def base_daily_limit(self) -> int:
        """Eingestelltes Tageslimit für heute ohne Bonus (0 = aus)."""
        today = dt_util.now().date()
        return int(
            daily_limit_for(
                int(self._opts.get(CONF_DAILY_LIMIT_MINUTES, DEFAULT_DAILY_LIMIT_MINUTES) or 0),
                self._optional_int(self._opts.get(CONF_DAILY_LIMIT_WEEKEND)),
                self._optional_int(self._opts.get(CONF_DAILY_LIMIT_HOLIDAY)),
                today.weekday() >= 5,
                self.holiday_today,
            )
        )

    @property
    def daily_limit(self) -> int:
        """Bildschirmzeit heute in Minuten inklusive Bonus (0 = aus)."""
        base = self.base_daily_limit
        return base + self.bonus_minutes_today if base > 0 else 0

    @property
    def bonus_minutes(self) -> int:
        """Minuten pro Druck auf „Bonuszeit“."""
        return int(self._opts.get(CONF_BONUS_MINUTES, DEFAULT_BONUS_MINUTES) or DEFAULT_BONUS_MINUTES)

    @property
    def confirm_valid_minutes(self) -> int:
        """Wie lange eine Bestätigung gilt (0 = bis der Fernseher aus ist)."""
        return int(
            self._opts.get(CONF_CONFIRM_VALID_MINUTES, DEFAULT_CONFIRM_VALID_MINUTES) or 0
        )

    @property
    def allowed_apps(self) -> list[str]:
        """Apps, die nie gesperrt werden (z. B. tvkids)."""
        return list(self._opts.get(CONF_ALLOWED_APPS) or [])

    @property
    def app_block_always(self) -> bool:
        """Gesperrte Apps immer beenden (nicht nur im Zeitfenster)?

        Ältere Einträge ohne diese Einstellung behalten das bisherige
        Verhalten (nur im Zeitfenster).
        """
        return bool(self._opts.get(CONF_APP_BLOCK_ALWAYS, False))

    @property
    def app_release_minutes(self) -> int:
        """Dauer einer App-Freigabe per Code oder Handy."""
        return int(
            self._opts.get(CONF_APP_RELEASE_MINUTES, DEFAULT_APP_RELEASE_MINUTES)
            or DEFAULT_APP_RELEASE_MINUTES
        )

    @property
    def penalty_hours(self) -> int:
        """Dauer der Strafe in Stunden."""
        return int(
            self._opts.get(CONF_PENALTY_HOURS, DEFAULT_PENALTY_HOURS)
            or DEFAULT_PENALTY_HOURS
        )

    @property
    def actionable(self) -> bool:
        """Buttons in den Handy-Benachrichtigungen?"""
        return bool(self._opts.get(CONF_ACTIONABLE, DEFAULT_ACTIONABLE))

    @property
    def app_action_id(self) -> str:
        """Action-ID für „App freigeben“ in der mobilen Benachrichtigung."""
        return f"{APP_ACTION_PREFIX}{self.entry.entry_id}"

    @property
    def confirm_action_id(self) -> str:
        """Action-ID für den Bestätigen-Button der mobilen Benachrichtigung."""
        return f"{CONFIRM_ACTION_PREFIX}{self.entry.entry_id}"

    async def async_set_option(self, key: str, value: Any) -> None:
        """Eine Einstellung ändern (z. B. aus dem Dashboard)."""
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, key: value}
        )

    @callback
    def async_options_changed(self) -> None:
        """Einstellungen ohne Neuladen übernommen: Entitäten aktualisieren."""
        if self.limit_reached and (
            self.daily_limit <= 0 or self.screen_time_minutes < self.daily_limit
        ):
            self.limit_reached = False
        self._async_enforce()
        self._notify_listeners()

    def _entity_registry_platform(self, entity_id: str) -> str | None:
        from homeassistant.helpers import entity_registry as er

        entry = er.async_get(self.hass).async_get(entity_id)
        return entry.platform if entry else None

    # ------------------------------------------------------------------
    # Zustand und Entscheidung
    # ------------------------------------------------------------------
    @property
    def locked(self) -> bool:
        """Ist die Sperre aktuell aktiv?"""
        return self.lock_until is not None and self.lock_until > dt_util.utcnow()

    @property
    def exception_active(self) -> bool:
        """Läuft gerade eine Ausnahme („heute erlauben“)?"""
        return (
            self.exception_until is not None
            and self.exception_until > dt_util.utcnow()
        )

    @property
    def paused(self) -> bool:
        """Setzt eine Pause-Entität (z. B. Ferien) die Zeitfenster aus?"""
        for entity_id in self.pause_entities:
            state = self.hass.states.get(entity_id)
            if state is not None and state.state == "on":
                return True
        return False

    @property
    def in_window(self) -> bool:
        """Liegt jetzt ein Zeitfenster an (ohne Pause und Ausnahme)?"""
        return is_in_any_window(dt_util.now(), self.windows)

    @property
    def bonus_active(self) -> bool:
        """Läuft gerade Bonuszeit in der Sperrzeit?"""
        return self.bonus_until is not None and self.bonus_until > dt_util.utcnow()

    @property
    def app_released(self) -> bool:
        """Sind gesperrte Apps gerade per Code oder Handy freigegeben?"""
        return (
            self.app_release_until is not None
            and self.app_release_until > dt_util.utcnow()
        )

    @property
    def decision(self) -> Decision:
        """Was gilt gerade? Eine Stelle für Status, Sensoren und Durchsetzung."""
        return evaluate(
            RuleState(
                enabled=self.enabled,
                locked=self.locked,
                exception_active=self.exception_active,
                bonus_active=self.bonus_active,
                in_window=self.in_window,
                paused=self.paused,
                limit_reached=self.limit_reached and self.daily_limit > 0,
                has_blocked_apps=bool(self.blocked_apps),
                app_block_always=self.app_block_always,
                app_released=self.app_released,
            )
        )

    @property
    def restricted(self) -> bool:
        """Gelten jetzt die Regeln (Zeitfenster oder Tageslimit)?"""
        return self.decision.restricted

    @property
    def app_block_active(self) -> bool:
        """Werden gesperrte Apps gerade beendet?"""
        return self.decision.apps_blocked

    @property
    def status(self) -> str:
        """Zusammengefasster Zustand für das Dashboard."""
        return self.decision.status

    @property
    def waiting_for_confirmation(self) -> bool:
        """Wartet die Kindersicherung gerade auf eine Bestätigung?"""
        return self._confirm_event is not None

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        """Registriere einen Listener für Zustandsänderungen."""
        self._listeners.append(update)

        @callback
        def remove() -> None:
            if update in self._listeners:
                self._listeners.remove(update)

        return remove

    @callback
    def _notify_listeners(self) -> None:
        for update in list(self._listeners):
            update()

    async def _async_save(self) -> None:
        await self._store.async_save(self._data())

    @callback
    def _async_delay_save(self) -> None:
        self._store.async_delay_save(self._data, SCREEN_TIME_SAVE_DELAY)

    def _data(self) -> dict[str, Any]:
        def iso(value: datetime | None) -> str | None:
            return value.isoformat() if value else None

        return {
            "enabled": self.enabled,
            "attempts": self.attempts,
            "stats": dict(self.stats),
            "last_failure": iso(self.last_failure),
            "lock_until": iso(self.lock_until),
            "exception_until": iso(self.exception_until),
            "app_release_until": iso(self.app_release_until),
            "screen_time_date": self.screen_time_date,
            "screen_time_minutes": self.screen_time_minutes,
            "limit_reached": self.limit_reached,
            "bonus_minutes_today": self.bonus_minutes_today,
            "bonus_until": iso(self.bonus_until),
            "sessions": {
                entity_id: session.as_dict()
                for entity_id, session in self.sessions.items()
            },
        }

    def diagnostics(self) -> dict[str, Any]:
        """Zustand für den Diagnose-Download."""
        decision = self.decision
        return {
            **self._data(),
            "status": decision.status,
            "restricted": decision.restricted,
            "apps_blocked": decision.apps_blocked,
            "in_window": self.in_window,
            "paused": self.paused,
            "at_start": self.at_start,
            "daily_limit": self.daily_limit,
            "holiday_today": self.holiday_today,
            "school_days": {
                day.isoformat(): self.is_school_day(day)
                for day in (
                    dt_util.now().date() + timedelta(days=offset)
                    for offset in range(-1, SCHOOL_DAYS_AHEAD)
                )
            },
            "waiting_for_confirmation": self.waiting_for_confirmation,
            "flow_players": sorted(self._flow_players),
            "players": {
                entity_id: {
                    "state": state.state,
                    "app": self._app_of(state),
                }
                if (state := self.hass.states.get(entity_id)) is not None
                else None
                for entity_id in self.media_players
            },
        }

    # ------------------------------------------------------------------
    # Lebenszyklus
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        """Lade gespeicherten Zustand und registriere Listener."""
        data = await self._store.async_load() or {}
        self.enabled = bool(data.get("enabled", True))
        self.attempts = int(data.get("attempts", 0))
        saved_stats = data.get("stats") or {}
        for key in STAT_KEYS:
            self.stats[key] = int(saved_stats.get(key, 0))
        if raw := data.get("last_failure"):
            self.last_failure = dt_util.parse_datetime(raw)
        if raw := data.get("lock_until"):
            self.lock_until = dt_util.parse_datetime(raw)
        if raw := data.get("exception_until"):
            self.exception_until = dt_util.parse_datetime(raw)
        if raw := data.get("app_release_until"):
            self.app_release_until = dt_util.parse_datetime(raw)
        self.screen_time_date = data.get("screen_time_date")
        self.screen_time_minutes = int(data.get("screen_time_minutes") or 0)
        self.limit_reached = bool(data.get("limit_reached", False))
        self.bonus_minutes_today = int(data.get("bonus_minutes_today") or 0)
        if raw := data.get("bonus_until"):
            self.bonus_until = dt_util.parse_datetime(raw)
        for entity_id, raw in (data.get("sessions") or {}).items():
            if entity_id in self.media_players and isinstance(raw, dict):
                try:
                    self.sessions[entity_id] = Session.from_dict(raw)
                except (TypeError, ValueError):
                    continue
        self._roll_screen_time_day(dt_util.now())

        if self.lock_until is not None:
            if self.lock_until > dt_util.utcnow():
                self._schedule_unlock()
            else:
                self.lock_until = None
                self.attempts = 0
                self.last_failure = None
                await self._async_save()

        if self.media_players:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, self.media_players, self._async_media_player_changed
                )
            )
        if self.confirm_entities:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, self.confirm_entities, self._async_confirm_entity_changed
                )
            )
        if self.pause_entities:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, self.pause_entities, self._async_rules_input_changed
                )
            )
        self._unsubs.append(
            self.hass.bus.async_listen(
                MOBILE_APP_ACTION_EVENT, self._async_notification_action
            )
        )
        self._unsubs.append(
            async_track_time_change(self.hass, self._async_minute_tick, second=0)
        )
        if self.school_nights or self.holiday_calendars:
            self._async_refresh_school_days()
        # Läuft beim Start schon ein Fernseher, wird er gleich geprüft.
        self._async_enforce()

    @callback
    def async_shutdown(self) -> None:
        """Räume Listener, Timer und laufende Abläufe auf."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._unlock_unsub is not None:
            self._unlock_unsub()
            self._unlock_unsub = None
        for task in (self._flow_task, self._school_task):
            if task is not None and not task.done():
                task.cancel()
        self._listeners.clear()
        # Bildschirmzeit und Sitzungen nicht verlieren.
        self._store.async_delay_save(self._data, 0)

    # ------------------------------------------------------------------
    # Ereignisse
    # ------------------------------------------------------------------
    @callback
    def _async_media_player_changed(self, event: Event[EventStateChangedData]) -> None:
        """Ein überwachter Fernseher hat seinen Zustand geändert."""
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        # App gewechselt oder neu eingeschaltet: gesperrte App sofort prüfen.
        app_changed = (
            old_state is None
            or new_state is None
            or self._app_of(old_state) != self._app_of(new_state)
            or old_state.state != new_state.state
        )
        self._async_enforce([entity_id], check_apps=app_changed)

    @callback
    def _async_rules_input_changed(self, _event: Event[EventStateChangedData]) -> None:
        """Eine Pause-Entität (z. B. Ferien) hat sich geändert."""
        self._async_enforce()
        self._notify_listeners()

    @callback
    def _async_confirm_entity_changed(self, event: Event[EventStateChangedData]) -> None:
        """Eine externe Bestätigungs-Entität wurde eingeschaltet."""
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if new_state is None or new_state.state != "on":
            return
        if old_state is not None and old_state.state == "on":
            return
        if self._confirm_event is not None:
            self.entry.async_create_task(
                self.hass,
                self.async_confirm("external"),
                "kindersicherung external confirm",
            )

    @callback
    def _async_notification_action(self, event: Event) -> None:
        """Button einer mobilen Benachrichtigung wurde gedrückt."""
        action = event.data.get("action")
        if action == self.confirm_action_id:
            self.entry.async_create_task(
                self.hass, self.async_confirm("app"), "kindersicherung app confirm"
            )
        elif action == self.app_action_id:
            self.entry.async_create_task(
                self.hass, self.async_release_apps(), "kindersicherung app release"
            )

    # ------------------------------------------------------------------
    # Durchsetzung
    # ------------------------------------------------------------------
    def _session(self, entity_id: str, restricted: bool) -> Session:
        session = self.sessions.get(entity_id)
        if session is None:
            session = Session(SESSION_NEW if restricted else SESSION_FREE)
            self.sessions[entity_id] = session
        return session

    @callback
    def _async_enforce(
        self, entity_ids: Iterable[str] | None = None, *, check_apps: bool = True
    ) -> None:
        """Entscheidung für die Fernseher durchsetzen.

        Geprüft wird der Zustand, nicht nur der Moment des Einschaltens: Auch
        ein Fernseher, der aus „nicht verfügbar“ angeht, schon beim Start von
        Home Assistant läuft oder bei Beginn der Sperrzeit noch an ist, wird
        abgefragt bzw. ausgeschaltet.
        """
        now = dt_util.utcnow()
        decision = self.decision
        locked = self.locked
        changed = False
        for entity_id in entity_ids if entity_ids is not None else self.media_players:
            session = self._session(entity_id, decision.restricted)
            before = session.as_dict()
            active = devices.is_active(self.hass, entity_id)
            update_session(session, active, now, decision.restricted, SESSION_GAP)
            changed |= session.as_dict() != before
            if not active and entity_id in self._turning_off:
                self._went_off.add(entity_id)
            if not active or not self.enabled or entity_id in self._turning_off:
                continue
            if locked:
                self._async_start_turn_off([entity_id], "locked")
                self.entry.async_create_task(
                    self.hass, self._async_announce_blocked(), "kindersicherung blocked"
                )
                continue
            state = self.hass.states.get(entity_id)
            if (
                check_apps
                and decision.apps_blocked
                and state is not None
                and self._runs_blocked_app(state)
            ):
                self._async_start_close_app(entity_id)
            action = session_action(session, decision.restricted, self.at_start)
            if action == ACTION_TURN_OFF:
                self._async_start_turn_off([entity_id], "window_start")
            elif action == ACTION_CONFIRM and (
                session.retry_after is None or now >= session.retry_after
            ):
                self._async_request_confirmation(entity_id)
        if changed:
            self._async_delay_save()

    def _fire_action(self, action: str, reason: str, entity_id: str | None = None) -> None:
        """Ereignis für Logbuch und eigene Automationen."""
        self.hass.bus.async_fire(
            EVENT_ACTION,
            {
                "entry_id": self.entry.entry_id,
                "name": self.entry.title,
                "action": action,
                "reason": reason,
                "entity_id": entity_id,
            },
        )

    @callback
    def _async_start_turn_off(self, entity_ids: Iterable[str], reason: str) -> None:
        """Fernseher im Hintergrund ausschalten (jeder nur einmal gleichzeitig)."""
        ids = [
            entity_id
            for entity_id in entity_ids
            if entity_id not in self._turning_off
            and devices.is_active(self.hass, entity_id)
        ]
        if not ids:
            return
        self._turning_off.update(ids)
        for entity_id in ids:
            # Wer ausgeschaltet wurde, muss beim nächsten Einschalten bestätigen.
            session = self.sessions.setdefault(entity_id, Session())
            session.status = SESSION_NEW
            session.confirmed_until = None
            self._fire_action("turn_off", reason, entity_id)
        self._async_delay_save()
        self.entry.async_create_background_task(
            self.hass, self._async_turn_off(ids), "kindersicherung turn off"
        )

    async def _async_turn_off(self, entity_ids: list[str]) -> None:
        def keep_going(entity_id: str) -> bool:
            # War der Fernseher zwischendurch aus oder ist er inzwischen
            # freigegeben, nicht noch einmal drücken (Power-Taste schaltet um).
            if entity_id in self._went_off:
                return False
            session = self.sessions.get(entity_id)
            return session is None or session.status != SESSION_CONFIRMED

        try:
            if not await devices.async_turn_off(self.hass, entity_ids, keep_going):
                _LOGGER.warning("%s ließ sich nicht ausschalten", entity_ids)
        finally:
            self._turning_off.difference_update(entity_ids)
            self._went_off.difference_update(entity_ids)
        # Wieder eingeschaltet, während noch ausgeschaltet wurde: gleich prüfen.
        self._async_enforce(entity_ids)

    @staticmethod
    def _app_of(state: Any) -> str:
        attrs = state.attributes
        return f"{attrs.get('app_id') or ''} {attrs.get('app_name') or ''}".strip()

    def _runs_blocked_app(self, state: Any) -> bool:
        return app_blocked(self._app_of(state), self.blocked_apps, self.allowed_apps)

    @callback
    def _async_start_close_app(self, entity_id: str) -> None:
        if entity_id in self._closing:
            return
        self._closing.add(entity_id)
        self.entry.async_create_background_task(
            self.hass, self._async_close_app(entity_id), "kindersicherung close app"
        )

    def _still_blocked(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return (
            state is not None
            and devices.is_active(self.hass, entity_id)
            and self._runs_blocked_app(state)
            and self.app_block_active
        )

    async def _async_close_app(self, entity_id: str) -> None:
        """Gesperrte App beenden: Home-Taste und Kontrolle, sonst Fernseher aus."""
        try:
            self.stats["apps_closed"] += 1
            self._fire_action("close_app", "blocked_app", entity_id)
            self._async_delay_save()
            self._notify_listeners()
            remote = devices.remote_for(self.hass, entity_id)
            closed = False
            if remote is not None and await devices.async_press_home(self.hass, remote):
                closed = await devices.async_wait_until(
                    lambda: not self._still_blocked(entity_id), APP_CHECK_DELAY
                )
            if not closed and self._still_blocked(entity_id):
                self._async_start_turn_off([entity_id], "blocked_app")
            await self._async_app_notice()
        finally:
            self._closing.discard(entity_id)

    async def _async_app_notice(self) -> None:
        now = time.monotonic()
        if now - self._last_app_notice < BLOCK_NOTICE_INTERVAL:
            return
        self._last_app_notice = now
        await self.notifier.async_send("Diese App ist gerade gesperrt.", entities_only=True)
        await self.notifier.async_send(
            f"Kindersicherung {self.entry.title}: gesperrte App beendet. "
            f"Freigabe für {self.app_release_minutes} Minuten per Code oder Button.",
            kind=TAG_APP,
            services_only=True,
            action=(self.app_action_id, "App freigeben") if self.actionable else None,
        )

    async def async_release_apps(self) -> None:
        """Gesperrte Apps für die eingestellte Dauer freigeben (Code oder Handy)."""
        self.app_release_until = dt_util.utcnow() + timedelta(
            minutes=self.app_release_minutes
        )
        await self._async_save()
        self._notify_listeners()

    # ------------------------------------------------------------------
    # Minütliche Prüfung: Bildschirmzeit, Vorwarnung, Durchsetzung
    # ------------------------------------------------------------------
    def _roll_screen_time_day(self, now: datetime) -> bool:
        today = now.date().isoformat()
        if self.screen_time_date == today:
            return False
        self.screen_time_date = today
        self.screen_time_minutes = 0
        self.limit_reached = False
        self.bonus_minutes_today = 0
        return True

    @callback
    def _async_minute_tick(self, now: datetime) -> None:
        self.entry.async_create_task(
            self.hass, self.async_minute_tick(dt_util.as_local(now)), "kindersicherung tick"
        )

    async def async_minute_tick(self, now: datetime) -> None:
        """Einmal pro Minute: zählen, warnen, durchsetzen."""
        changed = self._roll_screen_time_day(now)
        if (self.school_nights or self.holiday_calendars) and (
            changed
            or self._school_loaded is None
            or dt_util.utcnow() - self._school_loaded >= SCHOOL_REFRESH
        ):
            self._async_refresh_school_days()
        active = self._active_players()
        if self._watching_players(active):
            self.screen_time_minutes += 1
            changed = True
        if changed:
            self._async_delay_save()
        if self._tick_lock.locked():
            # Die vorige Prüfung läuft noch (z. B. langsame Benachrichtigung).
            self._notify_listeners()
            return
        async with self._tick_lock:
            if self.enabled:
                await self._async_check_limit(active)
                if not self.exception_active and not self.paused:
                    await self._async_warn_window_start(now, active)
                await self._async_warn_confirmation_end(now, active)
            self._async_enforce()
        self._notify_listeners()

    async def _async_check_limit(self, active: list[str]) -> None:
        limit = self.daily_limit
        if limit <= 0 or self.exception_active:
            return
        used = self.screen_time_minutes
        if self.warn_minutes and active and used == limit - self.warn_minutes:
            await self.notifier.async_send(
                f"Noch {self.warn_minutes} Minute{'' if self.warn_minutes == 1 else 'n'} Fernsehzeit für heute."
            )
        if used >= limit and not self.limit_reached:
            self.limit_reached = True
            await self._async_save()
            if active:
                await self.notifier.async_send(
                    f"Kindersicherung {self.entry.title}: Tageslimit von {limit} Minuten erreicht."
                )
                self._async_start_turn_off(active, "limit")

    async def _async_warn_window_start(self, now: datetime, active: list[str]) -> None:
        if not active or not self.warn_minutes:
            return
        if starts_at(now, self.windows, self.warn_minutes):
            await self.notifier.async_send(
                f"In {self.warn_minutes} Minuten wird der Fernseher gesperrt."
            )

    def _watching_players(self, active: list[str]) -> list[str]:
        """Laufende Fernseher ohne Bildschirmschoner (zählen als Bildschirmzeit)."""
        return [
            entity_id
            for entity_id in active
            if (state := self.hass.states.get(entity_id)) is not None
            and not app_matches(self._app_of(state), IDLE_APPS)
        ]

    def _active_players(self) -> list[str]:
        return [e for e in self.media_players if devices.is_active(self.hass, e)]

    # ------------------------------------------------------------------
    # Schultage und Ferien
    # ------------------------------------------------------------------
    @callback
    def _async_refresh_school_days(self) -> None:
        if self._school_task is not None and not self._school_task.done():
            return
        self._school_loaded = dt_util.utcnow()
        self._school_task = self.entry.async_create_background_task(
            self.hass, self._async_load_school_days(), "kindersicherung school days"
        )

    async def _async_load_school_days(self) -> None:
        """Werktage (Workday-Sensor) und Ferien (Kalender) für die nächsten Tage laden."""
        today = dt_util.now().date()
        first = today - timedelta(days=1)
        days = [first + timedelta(days=offset) for offset in range(SCHOOL_DAYS_AHEAD + 2)]
        school_days: dict[date, bool] = {}
        if workday := self.workday_entity:
            for day in days:
                try:
                    response = await self.hass.services.async_call(
                        "workday",
                        "check_date",
                        {"entity_id": workday, "check_date": day},
                        blocking=True,
                        return_response=True,
                    )
                    school_days[day] = bool((response or {})[workday]["workday"])
                except Exception:
                    _LOGGER.warning(
                        "Werktag für %s über %s nicht abrufbar", day, workday, exc_info=True
                    )
                    break
        holidays: set[date] = set()
        for calendar in self.holiday_calendars:
            start = dt_util.start_of_local_day(first)
            end = start + timedelta(days=len(days))
            try:
                response = await self.hass.services.async_call(
                    "calendar",
                    "get_events",
                    {
                        "entity_id": calendar,
                        "start_date_time": start,
                        "end_date_time": end,
                    },
                    blocking=True,
                    return_response=True,
                )
            except Exception:
                _LOGGER.warning("Ferien aus %s nicht abrufbar", calendar, exc_info=True)
                continue
            events = []
            for event in (response or {}).get(calendar, {}).get("events", []):
                begin = _parse_event_time(event.get("start"))
                finish = _parse_event_time(event.get("end"))
                if begin is not None and finish is not None:
                    events.append((begin, finish))
            holidays |= holiday_dates(events, first, len(days))
        self._school_days = school_days
        self._holidays = holidays
        self._async_enforce()
        self._notify_listeners()

    # ------------------------------------------------------------------
    # Bonuszeit und Ablauf von Freigaben
    # ------------------------------------------------------------------
    async def async_bonus(self) -> None:
        """Bonuszeit: Tageslimit und laufende Sperrzeit um ein paar Minuten verlängern."""
        minutes = self.bonus_minutes
        now = dt_util.utcnow()
        parts = []
        if self.base_daily_limit > 0:
            self.bonus_minutes_today += minutes
            if self.limit_reached and self.screen_time_minutes < self.daily_limit:
                self.limit_reached = False
            parts.append("Tageslimit")
        if self.in_window and not self.paused and not self.exception_active:
            start = self.bonus_until if self.bonus_active else now
            self.bonus_until = start + timedelta(minutes=minutes)
            parts.append(
                f"Fernsehen bis {dt_util.as_local(self.bonus_until).strftime('%H:%M')} Uhr"
            )
        await self._async_save()
        self._async_enforce()
        self._notify_listeners()
        await self.notifier.async_send(
            f"Kindersicherung {self.entry.title}: {minutes} Minuten Bonus"
            + (f" ({', '.join(parts)})." if parts else ".")
        )

    async def _async_warn_confirmation_end(self, now: datetime, active: list[str]) -> None:
        """Vorwarnung, bevor eine Bestätigung mit Ablaufzeit endet."""
        if not self.warn_minutes or not active:
            return
        target = now.replace(second=0, microsecond=0) + timedelta(minutes=self.warn_minutes)
        if (
            self.bonus_active
            and self.bonus_until is not None
            and dt_util.as_local(self.bonus_until).replace(second=0, microsecond=0) == target
        ):
            await self.notifier.async_send(
                f"In {self.warn_minutes} Minuten endet die Bonuszeit."
            )
        for entity_id in active:
            session = self.sessions.get(entity_id)
            if (
                session is not None
                and session.status == SESSION_CONFIRMED
                and session.confirmed_until is not None
                and dt_util.as_local(session.confirmed_until).replace(second=0, microsecond=0)
                == target
            ):
                await self.notifier.async_send(
                    f"In {self.warn_minutes} Minuten endet die Fernseh-Freigabe."
                )
                return

    # ------------------------------------------------------------------
    # Ausnahme „heute erlauben“
    # ------------------------------------------------------------------
    async def async_allow_today(self) -> None:
        """Regeln bis Mitternacht bzw. bis zum Ende des heutigen Fensters aussetzen."""
        until = exception_until(dt_util.now(), self.windows)
        self.exception_until = dt_util.as_utc(until)
        await self._async_save()
        self._async_enforce()
        self._notify_listeners()
        await self.notifier.async_send(
            f"Kindersicherung {self.entry.title}: heute erlaubt bis "
            f"{dt_util.as_local(until).strftime('%d.%m. %H:%M')} Uhr."
        )

    async def async_end_exception(self) -> None:
        """Ausnahme und App-Freigabe beenden."""
        self.exception_until = None
        self.app_release_until = None
        self.bonus_until = None
        await self._async_save()
        self._async_enforce()
        self._notify_listeners()

    # ------------------------------------------------------------------
    # Bestätigungsablauf
    # ------------------------------------------------------------------
    @callback
    def _async_request_confirmation(self, entity_id: str) -> None:
        """Bestätigung verlangen; läuft schon eine Abfrage, gilt sie mit."""
        self._flow_players.add(entity_id)
        if self._flow_task is not None and not self._flow_task.done():
            return
        self._flow_task = self.entry.async_create_background_task(
            self.hass,
            self._async_confirmation_flow(),
            f"kindersicherung confirmation {self.entry.entry_id}",
        )

    async def _async_confirmation_flow(self) -> None:
        self.confirmed = False
        self._confirm_ok = False
        self._wrong_code = False
        await self._async_reset_external_confirms()
        self._confirm_event = asyncio.Event()
        self._notify_listeners()

        confirmed = False
        try:
            await self.notifier.async_send(
                self._opts.get(CONF_MESSAGE) or DEFAULT_MESSAGE,
                kind=TAG_CONFIRM,
                action=(self.confirm_action_id, "Bestätigen") if self.actionable else None,
            )
            try:
                async with asyncio.timeout(self.confirm_timeout):
                    await self._confirm_event.wait()
                confirmed = self._confirm_ok
            except TimeoutError:
                confirmed = False
        finally:
            self._confirm_event = None
            players = set(self._flow_players)
            self._flow_players.clear()
            self._notify_listeners()

        if confirmed:
            valid = self.confirm_valid_minutes
            until = dt_util.utcnow() + timedelta(minutes=valid) if valid else None
            for entity_id in players:
                session = self.sessions.setdefault(entity_id, Session())
                session.status = SESSION_CONFIRMED
                session.confirmed_until = until
                session.retry_after = None
            self.stats["confirmations"] += 1
            self.attempts = 0
            self.last_failure = None
            await self._async_save()
            self._notify_listeners()
            self.hass.bus.async_fire(
                EVENT_CONFIRMED,
                {"entry_id": self.entry.entry_id, "name": self.entry.title},
            )
            return

        # Anfrage auf dem Handy ist abgelaufen.
        await self.notifier.async_clear(TAG_CONFIRM)
        # Erst ausschalten anstoßen, dann zählen (und ggf. sperren): ein
        # Fernseher, der nicht gleich reagiert, darf die Sperre nicht verzögern.
        reason = "wrong_code" if self._wrong_code else "timeout"
        self.stats["wrong_codes" if self._wrong_code else "timeouts"] += 1
        retry = dt_util.utcnow() + RETRY_DELAY
        for entity_id in players:
            # Läuft der Fernseher trotz Ausschalten weiter, erst später neu fragen.
            self.sessions.setdefault(entity_id, Session()).retry_after = retry
        self._async_start_turn_off(
            players, "wrong_code" if self._wrong_code else "no_confirmation"
        )
        await self._async_register_failure(reason)

    async def async_confirm(self, via: str = "switch") -> None:
        """Bestätige die Kindersicherung.

        `via` ist "switch", "external", "app" oder "code". Ist ein Zahlencode
        eingestellt, bestätigen nur "code" und "app" (Button in der
        Benachrichtigung auf dem Handy der Eltern).
        """
        if self.confirm_code and via in ("switch", "external"):
            self.confirmed = False
            self._notify_listeners()
            return
        if via == "app" and self._confirm_event is None:
            # Zu spät gedrückt: Die Abfrage ist schon vorbei. Nichts freigeben.
            return
        self.confirmed = True
        self._confirm_ok = True
        if self._confirm_event is not None and not self._confirm_event.is_set():
            self._confirm_event.set()
        if via in ("code", "app"):
            # Freigabe durch Eltern (Code oder Handy) gibt auch gesperrte Apps frei.
            await self.async_release_apps()
        self._notify_listeners()

    async def async_submit_code(self, code: str) -> None:
        """Zahlencode eingegeben: richtig bestätigt, falsch zählt als Fehlversuch."""
        if not self.confirm_code:
            return
        correct = hmac.compare_digest(code.strip().encode(), self.confirm_code.encode())
        if self._confirm_event is None or self._confirm_event.is_set():
            # Keine Abfrage läuft: der Code gibt gesperrte Apps frei.
            if correct:
                await self.async_release_apps()
            else:
                self.stats["wrong_codes"] += 1
                await self._async_register_failure("wrong_code")
            return
        if correct:
            await self.async_confirm("code")
            return
        self._confirm_ok = False
        self._wrong_code = True
        self._confirm_event.set()

    async def async_reset_confirmation(self) -> None:
        """Setze die Bestätigung zurück (Schalter ausgeschaltet)."""
        self.confirmed = False
        self._notify_listeners()

    async def _async_reset_external_confirms(self) -> None:
        for entity_id in self.confirm_entities:
            state = self.hass.states.get(entity_id)
            if state is None or state.state != "on":
                continue
            try:
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_off",
                    {"entity_id": entity_id},
                    blocking=True,
                )
            except Exception:
                _LOGGER.warning("Konnte %s nicht zurücksetzen", entity_id, exc_info=True)

    def _lock_until_text(self) -> str:
        if self.lock_until is None:
            return ""
        local = dt_util.as_local(self.lock_until)
        if local.date() != dt_util.now().date():
            return local.strftime("%d.%m. %H:%M")
        return local.strftime("%H:%M")

    async def _async_announce_lock(self) -> None:
        """Eltern informieren, dass gesperrt wurde."""
        if not self._opts.get(CONF_ANNOUNCE_LOCK, DEFAULT_ANNOUNCE_LOCK):
            return
        await self.notifier.async_send(
            f"Kindersicherung {self.entry.title}: gesperrt bis {self._lock_until_text()} Uhr."
        )

    async def _async_announce_blocked(self) -> None:
        """Bei Einschaltversuch während der Sperre kurz ansagen (höchstens einmal pro Minute)."""
        if not self._opts.get(CONF_ANNOUNCE_LOCK, DEFAULT_ANNOUNCE_LOCK):
            return
        now = time.monotonic()
        if now - self._last_block_notice < BLOCK_NOTICE_INTERVAL:
            return
        self._last_block_notice = now
        await self.notifier.async_send(
            f"Der Fernseher ist gesperrt bis {self._lock_until_text()} Uhr.",
            entities_only=True,
        )

    # ------------------------------------------------------------------
    # Fehlversuche und Sperre
    # ------------------------------------------------------------------
    async def _async_register_failure(self, reason: str = "timeout") -> None:
        now = dt_util.utcnow()
        self.attempts = attempts_after_failure(
            self.attempts,
            self.last_failure,
            now,
            int(self._opts.get(CONF_ATTEMPT_RESET_MINUTES, DEFAULT_ATTEMPT_RESET_MINUTES)),
        )
        self.last_failure = now
        self.hass.bus.async_fire(
            EVENT_FAILED,
            {
                "entry_id": self.entry.entry_id,
                "name": self.entry.title,
                "attempts": self.attempts,
                "max_attempts": self.max_attempts,
                "reason": reason,
            },
        )
        if self.attempts >= self.max_attempts:
            await self.async_lock()
            return
        await self._async_save()
        self._notify_listeners()

    async def async_penalty(self) -> None:
        """Strafe: Fernseher für die eingestellte Zeit komplett sperren.

        Eine laufende längere Sperre wird nicht verkürzt. Ausnahme und
        App-Freigabe enden.
        """
        minutes = self.penalty_hours * 60
        until = dt_util.utcnow() + timedelta(minutes=minutes)
        if self.lock_until is not None and self.lock_until > until:
            return
        self.exception_until = None
        self.app_release_until = None
        self.bonus_until = None
        await self.async_lock(minutes)

    async def async_lock(self, minutes: int | None = None) -> None:
        """Sperre die Fernseher für `minutes` (Standard: konfigurierte Dauer)."""
        duration = minutes if minutes else self.lock_minutes
        self.lock_until = dt_util.utcnow() + timedelta(minutes=duration)
        self.stats["locks"] += 1
        self.attempts = 0
        self.last_failure = None
        self._schedule_unlock()
        await self._async_save()
        self._notify_listeners()
        self.hass.bus.async_fire(
            EVENT_LOCKED,
            {
                "entry_id": self.entry.entry_id,
                "name": self.entry.title,
                "lock_until": self.lock_until.isoformat(),
            },
        )
        await self._async_announce_lock()
        self._async_start_turn_off(self._active_players(), "locked")

    async def async_unlock(self) -> None:
        """Hebe die Sperre auf und setze die Fehlversuche zurück."""
        was_locked = self.lock_until is not None
        if self._unlock_unsub is not None:
            self._unlock_unsub()
            self._unlock_unsub = None
        self.lock_until = None
        self.attempts = 0
        self.last_failure = None
        await self._async_save()
        self._notify_listeners()
        if was_locked:
            self.hass.bus.async_fire(
                EVENT_UNLOCKED,
                {"entry_id": self.entry.entry_id, "name": self.entry.title},
            )

    async def async_set_enabled(self, enabled: bool) -> None:
        """Schalte die Kindersicherung insgesamt ein oder aus."""
        self.enabled = enabled
        await self._async_save()
        self._async_enforce()
        self._notify_listeners()

    def _schedule_unlock(self) -> None:
        if self._unlock_unsub is not None:
            self._unlock_unsub()
            self._unlock_unsub = None
        if self.lock_until is None:
            return
        self._unlock_unsub = async_track_point_in_utc_time(
            self.hass, self._async_unlock_due, self.lock_until
        )

    @callback
    def _async_unlock_due(self, _now: datetime) -> None:
        self._unlock_unsub = None
        self.entry.async_create_task(
            self.hass, self.async_unlock(), "kindersicherung unlock"
        )


def _parse_event_time(value: Any) -> datetime | date | None:
    """Beginn/Ende eines Kalendertermins (Datum bei ganztägigen Terminen)."""
    if isinstance(value, datetime | date):
        return dt_util.as_local(value) if isinstance(value, datetime) else value
    if not isinstance(value, str):
        return None
    if len(value) == 10:
        return dt_util.parse_date(value)
    parsed = dt_util.parse_datetime(value)
    return dt_util.as_local(parsed) if parsed else None
