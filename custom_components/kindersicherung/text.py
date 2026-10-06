"""Eingabefeld für den Zahlencode."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
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
    """Lege das Eingabefeld nur an, wenn ein Code eingestellt ist."""
    controller = entry.runtime_data
    if controller.confirm_code:
        async_add_entities([CodeText(controller)])


class CodeText(KindersicherungEntity, TextEntity):
    """Hier wird der Zahlencode eingegeben (Zustand bleibt immer leer)."""

    _attr_mode = TextMode.PASSWORD
    _attr_native_min = 0
    _attr_native_max = 12
    _attr_pattern = r"^\d*$"

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere das Eingabefeld."""
        super().__init__(controller, "code")

    @property
    def native_value(self) -> str:
        """Der Code wird nie als Zustand angezeigt oder gespeichert."""
        return ""

    async def async_set_value(self, value: str) -> None:
        """Code prüfen."""
        await self._controller.async_submit_code(value)
