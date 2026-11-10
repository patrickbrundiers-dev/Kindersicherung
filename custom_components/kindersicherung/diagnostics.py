"""Diagnose-Download: Einstellungen (ohne Code) und aktueller Zustand."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import KindersicherungConfigEntry
from .const import CONF_CONFIRM_CODE

TO_REDACT = {CONF_CONFIRM_CODE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: KindersicherungConfigEntry
) -> dict[str, Any]:
    """Diagnosedaten für einen Eintrag."""
    return {
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "state": entry.runtime_data.diagnostics(),
    }
