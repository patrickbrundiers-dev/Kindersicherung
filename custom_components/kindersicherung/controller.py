"""Steuerung der Kindersicherung (ersetzt die frühere Automation)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACTIONABLE,
    CONF_ATTEMPT_RESET_MINUTES,
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
    CONF_WEEKDAYS,
    CONFIRM_ACTION_PREFIX,
    DEFAULT_ACTIONABLE,
    DEFAULT_ATTEMPT_RESET_MINUTES,
    DEFAULT_CONFIRM_TIMEOUT,
    DEFAULT_LOCK_MINUTES,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MESSAGE,
    DEFAULT_TIME_END,
    DEFAULT_TIME_START,
    DOMAIN,
    EVENT_CONFIRMED,
    EVENT_FAILED,
    EVENT_LOCKED,
    EVENT_UNLOCKED,
    INACTIVE_STATES,
    MOBILE_APP_ACTION_EVENT,
    POWER_OFF_STATES,
    STORAGE_VERSION,
    WEEKDAYS,
)
from .logic import attempts_after_failure, is_in_window

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

TURN_OFF_TRIES = 3
TURN_OFF_RETRY_DELAY = 3


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

        self.enabled = True
        self.confirmed = False
        self.attempts = 0
        self.last_failure: datetime | None = None
        self.lock_until: datetime | None = None

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
        await self._store.async_save(
            {
                "enabled": self.enabled,
                "attempts": self.attempts,
                "last_failure": self.last_failure.isoformat()
                if self.last_failure
                else None,
                "lock_until": self.lock_until.isoformat() if self.lock_until else None,
            }
        )

    # ------------------------------------------------------------------
    # Lebenszyklus
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        """Lade gespeicherten Zustand und registriere Listener."""
        data = await self._store.async_load() or {}
        self.enabled = bool(data.get("enabled", True))
        self.attempts = int(data.get("attempts", 0))
        if raw := data.get("last_failure"):
            self.last_failure = dt_util.parse_datetime(raw)
        if raw := data.get("lock_until"):
            self.lock_until = dt_util.parse_datetime(raw)

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

        # Während der Sperre wird jedes Einschalten sofort rückgängig gemacht,
        # unabhängig von Uhrzeit und Wochentag.
        if self.locked:
            if old is None or old in INACTIVE_STATES:
                self.entry.async_create_task(
                    self.hass,
                    self._async_turn_off([entity_id]),
                    "kindersicherung turn off while locked",
                )
            return

        if old not in POWER_OFF_STATES:
            return
        if not self._is_active_now():
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
                self.hass, self.async_confirm(), "kindersicherung external confirm"
            )

    @callback
    def _async_notification_action(self, event: Event) -> None:
        """Bestätigen-Button einer mobilen Benachrichtigung wurde gedrückt."""
        if event.data.get("action") == self.confirm_action_id:
            self.entry.async_create_task(
                self.hass, self.async_confirm(), "kindersicherung app confirm"
            )

    def _is_active_now(self) -> bool:
        return is_in_window(
            dt_util.now(),
            self._opts.get(CONF_TIME_START, DEFAULT_TIME_START),
            self._opts.get(CONF_TIME_END, DEFAULT_TIME_END),
            list(self._opts.get(CONF_WEEKDAYS, WEEKDAYS)),
        )

    # ------------------------------------------------------------------
    # Bestätigungsablauf
    # ------------------------------------------------------------------
    async def _async_confirmation_flow(self, trigger_entity: str) -> None:
        self.confirmed = False
        await self._async_reset_external_confirms()
        self._confirm_event = asyncio.Event()
        self._notify_listeners()

        confirmed = False
        try:
            await self._async_send_notifications()
            try:
                async with asyncio.timeout(self.confirm_timeout):
                    await self._confirm_event.wait()
                confirmed = True
            except TimeoutError:
                confirmed = False
        finally:
            self._confirm_event = None
            self._notify_listeners()

        if confirmed:
            self.attempts = 0
            self.last_failure = None
            await self._async_save()
            self._notify_listeners()
            self.hass.bus.async_fire(
                EVENT_CONFIRMED,
                {"entry_id": self.entry.entry_id, "name": self.entry.title},
            )
            return

        await self._async_turn_off([trigger_entity])
        await self._async_register_failure()

    async def async_confirm(self) -> None:
        """Bestätige die Kindersicherung (Schalter, App-Button, externe Entität)."""
        self.confirmed = True
        if self._confirm_event is not None and not self._confirm_event.is_set():
            self._confirm_event.set()
        self._notify_listeners()

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
        message = self._opts.get(CONF_MESSAGE) or DEFAULT_MESSAGE

        if entities := self._opts.get(CONF_NOTIFY_ENTITIES, []):
            try:
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {"entity_id": list(entities), "message": message},
                    blocking=False,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Benachrichtigung an %s fehlgeschlagen", entities, exc_info=True)

        actionable = self._opts.get(CONF_ACTIONABLE, DEFAULT_ACTIONABLE)
        for service in self._opts.get(CONF_NOTIFY_SERVICES, []):
            service = service.removeprefix("notify.")
            data: dict[str, Any] = {"message": message}
            if actionable:
                data["data"] = {
                    "tag": f"{DOMAIN}_{self.entry.entry_id}",
                    "actions": [
                        {"action": self.confirm_action_id, "title": "Bestätigen"}
                    ],
                }
            try:
                await self.hass.services.async_call(
                    "notify", service, data, blocking=False
                )
            except Exception:  # noqa: BLE001
                _LOGGER.warning("Benachrichtigung über notify.%s fehlgeschlagen", service, exc_info=True)

    # ------------------------------------------------------------------
    # Fehlversuche und Sperre
    # ------------------------------------------------------------------
    async def _async_register_failure(self) -> None:
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
