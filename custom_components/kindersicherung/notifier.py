"""Benachrichtigungen an Handys (notify-Dienste) und Lautsprecher (notify-Entitäten)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_NOTIFY_ENTITIES, CONF_NOTIFY_SERVICES, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Getrennte Tags: eine neue Nachricht ersetzt auf dem Handy nur eine
# Nachricht derselben Art, nicht z. B. eine offene Bestätigungsanfrage.
TAG_CONFIRM = "confirm"
TAG_APP = "app"
TAG_INFO = "info"


class Notifier:
    """Sendet Nachrichten an die Ziele eines Eintrags."""

    def __init__(self, hass: HomeAssistant, entry_id: str, options: Any) -> None:
        """`options` liefert die aktuellen Einstellungen (Callable)."""
        self.hass = hass
        self._entry_id = entry_id
        self._options = options

    def _tag(self, kind: str) -> str:
        return f"{DOMAIN}_{self._entry_id}_{kind}"

    async def async_send(
        self,
        message: str,
        *,
        kind: str = TAG_INFO,
        entities_only: bool = False,
        services_only: bool = False,
        action: tuple[str, str] | None = None,
    ) -> None:
        """Nachricht senden; `action` ergibt einen Button auf dem Handy."""
        opts = self._options()
        entities = [] if services_only else list(opts.get(CONF_NOTIFY_ENTITIES, []))
        if entities:
            try:
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {"entity_id": entities, "message": message},
                    blocking=False,
                )
            except Exception:
                _LOGGER.warning("Benachrichtigung an %s fehlgeschlagen", entities, exc_info=True)
        if entities_only:
            return
        payload: dict[str, Any] = {"tag": self._tag(kind)}
        if action is not None:
            payload["actions"] = [{"action": action[0], "title": action[1]}]
        await self._async_services({"message": message, "data": payload})

    async def async_clear(self, kind: str) -> None:
        """Nachricht dieser Art vom Handy entfernen (z. B. abgelaufene Anfrage)."""
        await self._async_services(
            {"message": "clear_notification", "data": {"tag": self._tag(kind)}}
        )

    async def _async_services(self, data: dict[str, Any]) -> None:
        for service in self._options().get(CONF_NOTIFY_SERVICES, []):
            service = service.removeprefix("notify.")
            try:
                await self.hass.services.async_call(
                    "notify", service, data, blocking=False
                )
            except Exception:
                _LOGGER.warning(
                    "Benachrichtigung über notify.%s fehlgeschlagen", service, exc_info=True
                )
