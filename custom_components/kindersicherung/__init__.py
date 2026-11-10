"""Kindersicherung für Fernseher: Bestätigung beim Einschalten, Sperre nach Fehlversuchen."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_APP_BLOCK_ALWAYS,
    CONF_APP_RELEASE_MINUTES,
    CONF_DAILY_LIMIT_MINUTES,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_WARN_MINUTES,
)
from .controller import KindersicherungController

# Optionen, die ohne Neuladen wirken (Dashboard-Entitäten).
LIVE_OPTIONS = frozenset(
    {
        CONF_TIME_START,
        CONF_TIME_END,
        CONF_DAILY_LIMIT_MINUTES,
        CONF_APP_RELEASE_MINUTES,
        CONF_WARN_MINUTES,
        CONF_APP_BLOCK_ALWAYS,
    }
)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.TEXT,
    Platform.TIME,
]

type KindersicherungConfigEntry = ConfigEntry[KindersicherungController]


async def async_setup_entry(
    hass: HomeAssistant, entry: KindersicherungConfigEntry
) -> bool:
    """Richte einen Kindersicherungs-Eintrag ein."""
    controller = KindersicherungController(hass, entry)
    await controller.async_setup()
    entry.runtime_data = controller
    entry.async_on_unload(controller.async_shutdown)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: KindersicherungConfigEntry
) -> bool:
    """Entlade einen Eintrag."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: KindersicherungConfigEntry
) -> None:
    """Nach Änderung der Optionen neu laden, außer bei Werten aus dem Dashboard.

    Uhrzeiten, Minuten und die App-Sperre liest der Controller bei jeder
    Prüfung neu, dafür ist kein Neuladen nötig.
    """
    controller = entry.runtime_data
    old = controller.loaded_options
    new = dict(entry.options)
    changed = {key for key in old.keys() | new.keys() if old.get(key) != new.get(key)}
    if changed and changed <= LIVE_OPTIONS:
        controller.loaded_options = new
        controller.async_options_changed()
        return
    await hass.config_entries.async_reload(entry.entry_id)
