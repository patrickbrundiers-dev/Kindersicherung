"""Kindersicherung für Fernseher: Bestätigung beim Einschalten, Sperre nach Fehlversuchen."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .controller import KindersicherungController

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
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
    """Lade den Eintrag nach Änderung der Optionen neu."""
    await hass.config_entries.async_reload(entry.entry_id)
