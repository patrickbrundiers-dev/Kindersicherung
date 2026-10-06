"""Schalter der Kindersicherung."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Lege die Schalter an."""
    controller = entry.runtime_data
    async_add_entities(
        [
            EnabledSwitch(controller),
            ConfirmSwitch(controller),
        ]
    )


class EnabledSwitch(KindersicherungEntity, SwitchEntity):
    """Schaltet die Kindersicherung insgesamt ein oder aus."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Schalter."""
        super().__init__(controller, "enabled")

    @property
    def is_on(self) -> bool:
        """Ist die Kindersicherung aktiv?"""
        return self._controller.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Aktiviere die Kindersicherung."""
        await self._controller.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deaktiviere die Kindersicherung."""
        await self._controller.async_set_enabled(False)


class ConfirmSwitch(KindersicherungEntity, SwitchEntity):
    """Bestätigungsschalter (ersetzt input_boolean.kindersicherung_tv)."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Schalter."""
        super().__init__(controller, "confirm")

    @property
    def is_on(self) -> bool:
        """Wurde zuletzt bestätigt?"""
        return self._controller.confirmed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Zeigt, ob gerade auf eine Bestätigung gewartet wird."""
        return {"waiting": self._controller.waiting_for_confirmation}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Bestätige."""
        await self._controller.async_confirm()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Setze die Bestätigung zurück."""
        await self._controller.async_reset_confirmation()
