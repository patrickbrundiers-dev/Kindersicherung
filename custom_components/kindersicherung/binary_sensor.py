"""Binärsensor: ist die Sperre aktiv?"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KindersicherungConfigEntry
from .controller import KindersicherungController
from .entity import KindersicherungEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KindersicherungConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Lege den Sensor an."""
    async_add_entities([LockedBinarySensor(entry.runtime_data)])


class LockedBinarySensor(KindersicherungEntity, BinarySensorEntity):
    """An, solange die Sperre nach zu vielen Fehlversuchen aktiv ist."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Sensor."""
        super().__init__(controller, "locked")

    @property
    def is_on(self) -> bool:
        """Ist die Sperre aktiv?"""
        return self._controller.locked

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Ende der Sperre und Fehlversuche."""
        controller = self._controller
        return {
            "lock_until": controller.lock_until.isoformat()
            if controller.locked and controller.lock_until
            else None,
            "attempts": controller.attempts,
            "max_attempts": controller.max_attempts,
        }
