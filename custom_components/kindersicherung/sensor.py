"""Sensoren: Fehlversuche und Ende der Sperre."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KindersicherungConfigEntry
from .const import STAT_KEYS
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
            AttemptsSensor(controller),
            LockUntilSensor(controller),
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
