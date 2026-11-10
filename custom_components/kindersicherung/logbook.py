"""Logbuch: Aktionen der Kindersicherung mit Grund anzeigen."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_ENTITY_ID,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_ACTION

ACTIONS = {
    "turn_off": "hat den Fernseher ausgeschaltet",
    "close_app": "hat eine gesperrte App beendet",
}
REASONS = {
    "no_confirmation": "keine Bestätigung",
    "wrong_code": "falscher Code",
    "locked": "gesperrt",
    "limit": "Tageslimit erreicht",
    "window_start": "Beginn der Sperrzeit",
    "blocked_app": "gesperrte App",
    "confirmation_expired": "Freigabe abgelaufen",
    "away": "niemand zu Hause",
}


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, Any]]], None],
) -> None:
    """Beschreibe die Ereignisse der Kindersicherung."""

    @callback
    def describe(event: Event) -> dict[str, Any]:
        data = event.data
        action = ACTIONS.get(data.get("action"), data.get("action", ""))
        reason = REASONS.get(data.get("reason"), data.get("reason", ""))
        entry: dict[str, Any] = {
            LOGBOOK_ENTRY_NAME: f"Kindersicherung {data.get('name', '')}".strip(),
            LOGBOOK_ENTRY_MESSAGE: f"{action} ({reason})" if reason else action,
        }
        if data.get("entity_id"):
            entry[LOGBOOK_ENTRY_ENTITY_ID] = data["entity_id"]
        return entry

    async_describe_event(DOMAIN, EVENT_ACTION, describe)
