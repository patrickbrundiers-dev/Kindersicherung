"""Uhrzeiten des Zeitfensters, direkt im Dashboard änderbar."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KindersicherungConfigEntry
from .const import CONF_TIME_END, CONF_TIME_START, DEFAULT_TIME_END, DEFAULT_TIME_START
from .controller import KindersicherungController
from .entity import KindersicherungEntity
from .logic import parse_time


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KindersicherungConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Lege die Uhrzeit-Entitäten an."""
    controller = entry.runtime_data
    async_add_entities(
        [
            WindowTime(controller, "window_start", CONF_TIME_START, DEFAULT_TIME_START),
            WindowTime(controller, "window_end", CONF_TIME_END, DEFAULT_TIME_END),
        ]
    )


class WindowTime(KindersicherungEntity, TimeEntity):
    """Beginn oder Ende des (ersten) Zeitfensters."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        controller: KindersicherungController,
        key: str,
        option: str,
        default: str,
    ) -> None:
        """Initialisiere die Entität."""
        super().__init__(controller, key)
        self._option = option
        self._default = default

    @property
    def native_value(self) -> time:
        """Eingestellte Uhrzeit."""
        return parse_time(self._controller.entry.options.get(self._option, self._default))

    async def async_set_value(self, value: time) -> None:
        """Neue Uhrzeit speichern."""
        await self._controller.async_set_option(
            self._option, value.replace(microsecond=0).isoformat()
        )
