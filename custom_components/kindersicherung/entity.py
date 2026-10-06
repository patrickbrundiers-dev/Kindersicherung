"""Gemeinsame Basis der Entitäten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import KindersicherungController


class KindersicherungEntity(Entity):
    """Basisklasse: hängt am Controller und gehört zu einem Gerät pro Eintrag."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: KindersicherungController, key: str) -> None:
        """Initialisiere die Entität."""
        self._controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name=controller.entry.title,
            manufacturer="Kindersicherung",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Registriere den Listener beim Controller."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._controller.async_add_listener(self.async_write_ha_state)
        )
