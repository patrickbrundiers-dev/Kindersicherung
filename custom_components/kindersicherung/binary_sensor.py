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
    controller = entry.runtime_data
    async_add_entities(
        [LockedBinarySensor(controller), RestrictedBinarySensor(controller)]
    )


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


class RestrictedBinarySensor(KindersicherungEntity, BinarySensorEntity):
    """An, solange die Regeln gelten (Zeitfenster oder Tageslimit)."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Sensor."""
        super().__init__(controller, "restricted")

    @property
    def is_on(self) -> bool:
        """Gelten die Regeln gerade?"""
        return self._controller.restricted

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Warum die Regeln gelten oder nicht."""
        controller = self._controller
        return {
            "in_window": controller.in_window,
            "paused": controller.paused,
            "exception_active": controller.exception_active,
            "limit_reached": controller.limit_reached,
            "app_block_active": controller.app_block_active,
        }
