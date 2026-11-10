"""Steuerung der Kindersicherung (ersetzt die frühere Automation)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import hmac
import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    APP_ACTION_PREFIX,
    CONF_APP_BLOCK_ALWAYS,
    CONF_APP_RELEASE_MINUTES,
    CONF_BLOCKED_APPS,
    CONF_DAILY_LIMIT_MINUTES,
    CONF_PAUSE_ENTITIES,
    CONF_TIME_END_2,
    CONF_TIME_START_2,
    CONF_WARN_MINUTES,
    CONF_WEEKDAYS_2,
    DEFAULT_APP_RELEASE_MINUTES,
    DEFAULT_DAILY_LIMIT_MINUTES,
    DEFAULT_TIME_END_2,
    DEFAULT_TIME_START_2,
    DEFAULT_WARN_MINUTES,
    CONF_ACTIONABLE,
    CONF_ANNOUNCE_LOCK,
    CONF_ATTEMPT_RESET_MINUTES,
    CONF_CONFIRM_CODE,
    CONF_CONFIRM_ENTITIES,
    CONF_CONFIRM_TIMEOUT,
    CONF_LOCK_MINUTES,
    CONF_MAX_ATTEMPTS,
    CONF_MEDIA_PLAYERS,
    CONF_MESSAGE,
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_SERVICES,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TURN_OFF_AT_START,
    CONF_WEEKDAYS,
    CONFIRM_ACTION_PREFIX,
    DEFAULT_ACTIONABLE,
    DEFAULT_ANNOUNCE_LOCK,
    DEFAULT_ATTEMPT_RESET_MINUTES,
    DEFAULT_CONFIRM_TIMEOUT,
    DEFAULT_LOCK_MINUTES,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MESSAGE,
    DEFAULT_TIME_END,
    DEFAULT_TIME_START,
    DEFAULT_TURN_OFF_AT_START,
    DOMAIN,
    EVENT_CONFIRMED,
    EVENT_FAILED,
    EVENT_LOCKED,
    EVENT_UNLOCKED,
    INACTIVE_STATES,
    MOBILE_APP_ACTION_EVENT,
    POWER_OFF_STATES,
    STAT_KEYS,
    STORAGE_VERSION,
    WEEKDAYS,
)
from .logic import (
    Window,
    app_matches,
    attempts_after_failure,
    exception_until,
    is_in_any_window,
    starts_at,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

TURN_OFF_TRIES = 3
TURN_OFF_RETRY_DELAY = 3
BLOCK_NOTICE_INTERVAL = 60
SCREEN_TIME_SAVE_DELAY = 60


class KindersicherungController:
    """Verwaltet Bestätigung, Fehlversuche und Sperre für einen Eintrag."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialisiere den Controller."""
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._unlock_unsub: Callable[[], None] | None = None
        self._flow_task: asyncio.Task[None] | None = None
        self._confirm_event: asyncio.Event | None = None
        self._last_block_notice = float("-inf")
        self._last_app_notice = float("-inf")
        self._confirm_ok = False
        self._wrong_code = False

        self.stats: dict[str, int] = dict.fromkeys(STAT_KEYS, 0)
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
        result: list[Window] = [
            (
                self._opts.get(CONF_TIME_START, DEFAULT_TIME_START),
                self._opts.get(CONF_TIME_END, DEFAULT_TIME_END),
                list(self._opts.get(CONF_WEEKDAYS, WEEKDAYS)),
            )
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
    def blocked_apps(self) -> list[str]:
        """Apps, die im Zeitfenster sofort beendet werden."""
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
    def daily_limit(self) -> int:
        """Bildschirmzeit pro Tag in Minuten (0 = aus)."""
        return int(
            self._opts.get(CONF_DAILY_LIMIT_MINUTES, DEFAULT_DAILY_LIMIT_MINUTES) or 0
        )

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
    def app_action_id(self) -> str:
        """Action-ID für „App freigeben“ in der mobilen Benachrichtigung."""
        return f"{APP_ACTION_PREFIX}{self.entry.entry_id}"

    @property
    def confirm_action_id(self) -> str:
        """Action-ID für den Bestätigen-Button der mobilen Benachrichtigung."""
        return f"{CONFIRM_ACTION_PREFIX}{self.entry.entry_id}"

    def _entity_registry_platform(self, entity_id: str) -> str | None:
        from homeassistant.helpers import entity_registry as er

        entry = er.async_get(self.hass).async_get(entity_id)
        return entry.platform if entry else None

    # ------------------------------------------------------------------
    # Zustand
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
    def restricted(self) -> bool:
        """Gelten jetzt die Regeln (Zeitfenster oder Tageslimit)?"""
        if not self.enabled or self.exception_active:
            return False
        if self.limit_reached and self.daily_limit > 0:
            return True
        return self.in_window and not self.paused

    @property
    def app_released(self) -> bool:
        """Sind gesperrte Apps gerade per Code oder Handy freigegeben?"""
        return (
            self.app_release_until is not None
            and self.app_release_until > dt_util.utcnow()
        )

    @property
    def app_block_active(self) -> bool:
        """Werden gesperrte Apps gerade beendet?"""
        if not self.enabled or not self.blocked_apps:
            return False
        if self.exception_active or self.app_released:
            return False
        return self.app_block_always or self.restricted

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

    def _data(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "attempts": self.attempts,
            "stats": dict(self.stats),
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "lock_until": self.lock_until.isoformat() if self.lock_until else None,
            "exception_until": self.exception_until.isoformat()
            if self.exception_until
            else None,
            "app_release_until": self.app_release_until.isoformat()
            if self.app_release_until
            else None,
            "screen_time_date": self.screen_time_date,
            "screen_time_minutes": self.screen_time_minutes,
            "limit_reached": self.limit_reached,
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
        self._unsubs.append(
            self.hass.bus.async_listen(
                MOBILE_APP_ACTION_EVENT, self._async_notification_action
            )
        )
        self._unsubs.append(
            async_track_time_change(self.hass, self._async_minute_tick, second=0)
        )

    @callback
    def async_shutdown(self) -> None:
        """Räume Listener, Timer und laufende Abläufe auf."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._unlock_unsub is not None:
            self._unlock_unsub()
            self._unlock_unsub = None
        if self._flow_task is not None and not self._flow_task.done():
            self._flow_task.cancel()
        self._listeners.clear()
        # Bildschirmzeit nicht verlieren, falls noch eine verzögerte Speicherung aussteht.
        self._store.async_delay_save(self._data, 0)

    # ------------------------------------------------------------------
    # Ereignisse
    # ------------------------------------------------------------------
    @callback
    def _async_media_player_changed(self, event: Event[EventStateChangedData]) -> None:
        """Reagiere auf Zustandswechsel der überwachten Media Player."""
        if not self.enabled:
            return
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if new_state is None or new_state.state in INACTIVE_STATES:
            return
        entity_id = event.data["entity_id"]
        old = old_state.state if old_state is not None else None

        if self.app_block_active and self._runs_blocked_app(new_state):
            old_app = self._app_of(old_state) if old_state is not None else None
            if old_app != self._app_of(new_state) or old in INACTIVE_STATES:
                self.entry.async_create_task(
                    self.hass,
                    self._async_close_app(entity_id),
                    "kindersicherung close blocked app",
                )

        # Während der Sperre wird jedes Einschalten sofort rückgängig gemacht,
        # unabhängig von Uhrzeit und Wochentag.
        if self.locked:
            if old is None or old in INACTIVE_STATES:
                self.entry.async_create_task(
                    self.hass,
                    self._async_turn_off([entity_id]),
                    "kindersicherung turn off while locked",
                )
                self.entry.async_create_task(
                    self.hass,
                    self._async_announce_blocked(),
                    "kindersicherung announce blocked",
                )
            return

        if old not in POWER_OFF_STATES:
            return
        if not self.restricted:
            return
        if self._flow_task is not None and not self._flow_task.done():
            return
        self._flow_task = self.entry.async_create_background_task(
            self.hass,
            self._async_confirmation_flow(entity_id),
            f"kindersicherung confirmation {self.entry.entry_id}",
        )

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
        """Bestätigen-Button einer mobilen Benachrichtigung wurde gedrückt."""
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
    # Minütliche Prüfung: Bildschirmzeit, Vorwarnung, Fensterbeginn, Apps
    # ------------------------------------------------------------------
    def _roll_screen_time_day(self, now: datetime) -> bool:
        today = now.date().isoformat()
        if self.screen_time_date == today:
            return False
        self.screen_time_date = today
        self.screen_time_minutes = 0
        self.limit_reached = False
        return True

    @callback
    def _async_minute_tick(self, now: datetime) -> None:
        self.entry.async_create_task(
            self.hass, self.async_minute_tick(dt_util.as_local(now)), "kindersicherung tick"
        )

    async def async_minute_tick(self, now: datetime) -> None:
        """Einmal pro Minute: zählen, warnen, ausschalten, Apps prüfen."""
        changed = self._roll_screen_time_day(now)
        active = self._active_players()
        if active:
            self.screen_time_minutes += 1
            changed = True

        if self.enabled:
            await self._async_check_limit(active)
            if not self.exception_active and not self.paused:
                await self._async_check_window_start(now, active)

        if self.app_block_active:
            for entity_id in active:
                state = self.hass.states.get(entity_id)
                if state is not None and self._runs_blocked_app(state):
                    await self._async_close_app(entity_id)

        if changed:
            self._store.async_delay_save(self._data, SCREEN_TIME_SAVE_DELAY)
        self._notify_listeners()

    async def _async_check_limit(self, active: list[str]) -> None:
        limit = self.daily_limit
        if limit <= 0 or self.exception_active:
            return
        used = self.screen_time_minutes
        if self.warn_minutes and active and used == limit - self.warn_minutes:
            await self._async_notify(
                f"Noch {self.warn_minutes} Minute{'' if self.warn_minutes == 1 else 'n'} Fernsehzeit für heute."
            )
        if used >= limit and not self.limit_reached:
            self.limit_reached = True
            await self._async_save()
            if active:
                await self._async_notify(
                    f"Kindersicherung {self.entry.title}: Tageslimit von {limit} Minuten erreicht."
                )
                await self._async_turn_off(active)

    async def _async_check_window_start(self, now: datetime, active: list[str]) -> None:
        if not active:
            return
        windows = self.windows
        if self.warn_minutes and starts_at(now, windows, self.warn_minutes):
            await self._async_notify(
                f"In {self.warn_minutes} Minuten wird der Fernseher gesperrt."
            )
        if starts_at(now, windows) and self._opts.get(
            CONF_TURN_OFF_AT_START, DEFAULT_TURN_OFF_AT_START
        ):
            await self._async_turn_off(active)

    @staticmethod
    def _app_of(state: Any) -> str:
        attrs = state.attributes
        return f"{attrs.get('app_id') or ''} {attrs.get('app_name') or ''}".strip()

    def _runs_blocked_app(self, state: Any) -> bool:
        return app_matches(self._app_of(state), self.blocked_apps)

    def _remote_for(self, media_player: str) -> str | None:
        """Fernbedienungs-Entität (remote.*) desselben Geräts, falls vorhanden."""
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self.hass)
        entry = registry.async_get(media_player)
        if entry is None or entry.device_id is None:
            return None
        for candidate in er.async_entries_for_device(registry, entry.device_id):
            if candidate.domain == "remote":
                return candidate.entity_id
        return None

    async def _async_close_app(self, media_player: str) -> None:
        """Gesperrte App beenden: Home-Taste, sonst Fernseher aus."""
        remote = self._remote_for(media_player)
        closed = False
        if remote is not None:
            try:
                await self.hass.services.async_call(
                    "remote",
                    "send_command",
                    {"entity_id": remote, "command": "HOME"},
                    blocking=True,
                )
                closed = True
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Home-Taste über %s fehlgeschlagen", remote, exc_info=True)
        if not closed:
            await self._async_turn_off([media_player])
        now = time.monotonic()
        if now - self._last_app_notice >= BLOCK_NOTICE_INTERVAL:
            self._last_app_notice = now
            await self._async_notify(
                "Diese App ist gerade gesperrt.", entities_only=True
            )
            await self._async_notify(
                f"Kindersicherung {self.entry.title}: gesperrte App beendet. "
                f"Freigabe für {self.app_release_minutes} Minuten per Code oder Button.",
                services_only=True,
                action=(self.app_action_id, "App freigeben")
                if self._opts.get(CONF_ACTIONABLE, DEFAULT_ACTIONABLE)
                else None,
            )

    async def async_release_apps(self) -> None:
        """Gesperrte Apps für die eingestellte Dauer freigeben (Code oder Handy)."""
        self.app_release_until = dt_util.utcnow() + timedelta(
            minutes=self.app_release_minutes
        )
        await self._async_save()
        self._notify_listeners()

    # ------------------------------------------------------------------
    # Ausnahme „heute erlauben“
    # ------------------------------------------------------------------
    async def async_allow_today(self) -> None:
        """Regeln bis Mitternacht bzw. bis zum Ende des heutigen Fensters aussetzen."""
        until = exception_until(dt_util.now(), self.windows)
        self.exception_until = dt_util.as_utc(until)
        await self._async_save()
        self._notify_listeners()
        await self._async_notify(
            f"Kindersicherung {self.entry.title}: heute erlaubt bis "
            f"{dt_util.as_local(until).strftime('%d.%m. %H:%M')} Uhr."
        )

    async def async_end_exception(self) -> None:
        """Ausnahme und App-Freigabe beenden."""
        self.exception_until = None
        self.app_release_until = None
        await self._async_save()
        self._notify_listeners()

    # ------------------------------------------------------------------
    # Bestätigungsablauf
    # ------------------------------------------------------------------
    async def _async_confirmation_flow(self, trigger_entity: str) -> None:
        self.confirmed = False
        self._confirm_ok = False
        self._wrong_code = False
        await self._async_reset_external_confirms()
        self._confirm_event = asyncio.Event()
        self._notify_listeners()

        confirmed = False
        try:
            await self._async_send_notifications()
            try:
                async with asyncio.timeout(self.confirm_timeout):
                    await self._confirm_event.wait()
                confirmed = self._confirm_ok
            except TimeoutError:
                confirmed = False
        finally:
            self._confirm_event = None
            self._notify_listeners()

        if confirmed:
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

        # Erst zählen (und ggf. sperren), dann ausschalten: ein Fernseher, der
        # nicht gleich reagiert, darf die Sperre nicht verzögern.
        reason = "wrong_code" if self._wrong_code else "timeout"
        self.stats["wrong_codes" if self._wrong_code else "timeouts"] += 1
        self.entry.async_create_task(
            self.hass,
            self._async_turn_off([trigger_entity]),
            "kindersicherung turn off after failure",
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
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Konnte %s nicht zurücksetzen", entity_id, exc_info=True)

    async def _async_send_notifications(self) -> None:
        """Bestätigungsanfrage an alle Ziele (mobile mit Bestätigen-Button)."""
        message = self._opts.get(CONF_MESSAGE) or DEFAULT_MESSAGE
        await self._async_notify(
            message, actionable=self._opts.get(CONF_ACTIONABLE, DEFAULT_ACTIONABLE)
        )

    async def _async_notify(
        self,
        message: str,
        *,
        actionable: bool = False,
        entities_only: bool = False,
        services_only: bool = False,
        action: tuple[str, str] | None = None,
    ) -> None:
        """Sende eine Nachricht an die konfigurierten Ziele."""
        if actionable:
            action = (self.confirm_action_id, "Bestätigen")
        entities = [] if services_only else self._opts.get(CONF_NOTIFY_ENTITIES, [])
        if entities:
            try:
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {"entity_id": list(entities), "message": message},
                    blocking=False,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Benachrichtigung an %s fehlgeschlagen", entities, exc_info=True)

        if entities_only:
            return

        for service in self._opts.get(CONF_NOTIFY_SERVICES, []):
            service = service.removeprefix("notify.")
            data: dict[str, Any] = {"message": message}
            if action is not None:
                data["data"] = {
                    "tag": f"{DOMAIN}_{self.entry.entry_id}",
                    "actions": [{"action": action[0], "title": action[1]}],
                }
            try:
                await self.hass.services.async_call(
                    "notify", service, data, blocking=False
                )
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Benachrichtigung über notify.%s fehlgeschlagen", service, exc_info=True)

    def _lock_until_text(self) -> str:
        if self.lock_until is None:
            return ""
        return dt_util.as_local(self.lock_until).strftime("%H:%M")

    async def _async_announce_lock(self) -> None:
        """Eltern informieren, dass gesperrt wurde."""
        if not self._opts.get(CONF_ANNOUNCE_LOCK, DEFAULT_ANNOUNCE_LOCK):
            return
        await self._async_notify(
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
        await self._async_notify(
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
        await self._async_turn_off(self._active_players())

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

    # ------------------------------------------------------------------
    # Geräte ausschalten
    # ------------------------------------------------------------------
    def _active_players(self) -> list[str]:
        return [
            entity_id
            for entity_id in self.media_players
            if (state := self.hass.states.get(entity_id)) is not None
            and state.state not in INACTIVE_STATES
        ]

    async def _async_turn_off(self, entity_ids: list[str]) -> None:
        """Schalte Geräte aus und versuche es bei Bedarf noch zweimal."""
        for attempt in range(TURN_OFF_TRIES):
            pending = [
                entity_id
                for entity_id in entity_ids
                if (state := self.hass.states.get(entity_id)) is not None
                and state.state not in INACTIVE_STATES
            ]
            if not pending:
                return
            try:
                await self.hass.services.async_call(
                    "media_player",
                    "turn_off",
                    {"entity_id": pending},
                    blocking=True,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Ausschalten von %s fehlgeschlagen", pending, exc_info=True)
            if attempt < TURN_OFF_TRIES - 1:
                await asyncio.sleep(TURN_OFF_RETRY_DELAY)
