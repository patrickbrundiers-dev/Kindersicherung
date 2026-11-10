"""Zahlenwerte (Tageslimit, Freigabedauer, Vorwarnung), direkt im Dashboard änderbar."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KindersicherungConfigEntry
from .const import (
    CONF_APP_RELEASE_MINUTES,
    CONF_DAILY_LIMIT_MINUTES,
    CONF_PENALTY_HOURS,
    CONF_WARN_MINUTES,
    DEFAULT_APP_RELEASE_MINUTES,
    DEFAULT_DAILY_LIMIT_MINUTES,
    DEFAULT_PENALTY_HOURS,
    DEFAULT_WARN_MINUTES,
)
from .controller import KindersicherungController
from .entity import KindersicherungEntity

NUMBERS = (
    # key, Option, Standard, min, max, Schritt
    ("daily_limit", CONF_DAILY_LIMIT_MINUTES, DEFAULT_DAILY_LIMIT_MINUTES, 0, 600, 15),
    ("app_release", CONF_APP_RELEASE_MINUTES, DEFAULT_APP_RELEASE_MINUTES, 15, 240, 15),
    ("warn", CONF_WARN_MINUTES, DEFAULT_WARN_MINUTES, 0, 60, 5),
    ("penalty_hours", CONF_PENALTY_HOURS, DEFAULT_PENALTY_HOURS, 1, 168, 1, UnitOfTime.HOURS),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KindersicherungConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Lege die Zahlen-Entitäten an."""
    controller = entry.runtime_data
    async_add_entities(OptionNumber(controller, *spec) for spec in NUMBERS)


class OptionNumber(KindersicherungEntity, NumberEntity):
    """Eine Zeit-Einstellung (Minuten oder Stunden) als Schieberegler."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        controller: KindersicherungController,
        key: str,
        option: str,
        default: int,
        minimum: int,
        maximum: int,
        step: int,
        unit: str = UnitOfTime.MINUTES,
    ) -> None:
        """Initialisiere die Entität."""
        super().__init__(controller, key)
        self._option = option
        self._default = default
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float:
        """Eingestellter Wert."""
        return float(self._controller.entry.options.get(self._option, self._default))

    async def async_set_native_value(self, value: float) -> None:
        """Neuen Wert speichern."""
        await self._controller.async_set_option(self._option, int(value))
