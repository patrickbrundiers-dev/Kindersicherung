"""Sensoren: Fehlversuche und Ende der Sperre."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KindersicherungConfigEntry
from .const import STAT_KEYS, STATUS_OPTIONS
from .controller import KindersicherungController
from .entity import KindersicherungEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KindersicherungConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Lege die Sensoren an."""
    controller = entry.runtime_data
    async_add_entities(
        [
            StatusSensor(controller),
            AttemptsSensor(controller),
            LockUntilSensor(controller),
            ScreenTimeSensor(controller),
            ExceptionUntilSensor(controller),
            AppReleaseUntilSensor(controller),
            *(StatSensor(controller, key) for key in STAT_KEYS),
        ]
    )


class AttemptsSensor(KindersicherungEntity, SensorEntity):
    """Aktuelle Anzahl der Fehlversuche."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Sensor."""
        super().__init__(controller, "attempts")

    @property
    def native_value(self) -> int:
        """Anzahl der Fehlversuche."""
        return self._controller.attempts

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Maximale Fehlversuche und Zeitpunkt des letzten."""
        controller = self._controller
        return {
            "max_attempts": controller.max_attempts,
            "last_failure": controller.last_failure.isoformat()
            if controller.last_failure
            else None,
        }


class LockUntilSensor(KindersicherungEntity, SensorEntity):
    """Zeitpunkt, bis zu dem gesperrt ist."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Sensor."""
        super().__init__(controller, "lock_until")

    @property
    def native_value(self) -> datetime | None:
        """Ende der Sperre oder None."""
        controller = self._controller
        return controller.lock_until if controller.locked else None


class StatSensor(KindersicherungEntity, SensorEntity):
    """Gesamtzähler (steigt nur). Im Verlauf pro Tag oder Woche auswertbar."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, controller: KindersicherungController, key: str) -> None:
        """Initialisiere den Zähler."""
        super().__init__(controller, key)
        self._key = key

    @property
    def native_value(self) -> int:
        """Bisherige Anzahl."""
        return self._controller.stats[self._key]


class ScreenTimeSensor(KindersicherungEntity, SensorEntity):
    """Bildschirmzeit heute (alle Fernseher dieses Eintrags zusammen)."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Sensor."""
        super().__init__(controller, "screen_time")

    @property
    def native_value(self) -> int:
        """Minuten heute."""
        return self._controller.screen_time_minutes

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Tageslimit und ob es erreicht ist."""
        controller = self._controller
        return {
            "daily_limit": controller.daily_limit or None,
            "limit_reached": controller.limit_reached,
        }


class ExceptionUntilSensor(KindersicherungEntity, SensorEntity):
    """Ende der Ausnahme „Heute erlauben“."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Sensor."""
        super().__init__(controller, "exception_until")

    @property
    def native_value(self) -> datetime | None:
        """Ende der Ausnahme oder None."""
        controller = self._controller
        return controller.exception_until if controller.exception_active else None


class AppReleaseUntilSensor(KindersicherungEntity, SensorEntity):
    """Ende der App-Freigabe per Code oder Handy."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Sensor."""
        super().__init__(controller, "app_release_until")

    @property
    def native_value(self) -> datetime | None:
        """Ende der App-Freigabe oder None."""
        controller = self._controller
        return controller.app_release_until if controller.app_released else None


class StatusSensor(KindersicherungEntity, SensorEntity):
    """Zustand auf einen Blick: frei, Sperrzeit, gesperrt, Ausnahme, ..."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUS_OPTIONS

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Sensor."""
        super().__init__(controller, "status")

    @property
    def native_value(self) -> str:
        """Aktueller Zustand."""
        return self._controller.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Bis wann der Zustand gilt und ob Apps gesperrt sind."""
        controller = self._controller
        until = None
        if controller.locked:
            until = controller.lock_until
        elif controller.exception_active:
            until = controller.exception_until
        elif controller.bonus_active:
            until = controller.bonus_until
        return {
            "until": until.isoformat() if until else None,
            "apps_blocked": controller.app_block_active,
            "app_release_until": controller.app_release_until.isoformat()
            if controller.app_released and controller.app_release_until
            else None,
            "screen_time_minutes": controller.screen_time_minutes,
            "daily_limit": controller.daily_limit or None,
            "holiday_today": controller.holiday_today,
        }
