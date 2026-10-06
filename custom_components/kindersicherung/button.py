"""Buttons: Entsperren und Jetzt sperren."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Lege die Buttons an."""
    controller = entry.runtime_data
    async_add_entities([UnlockButton(controller), LockNowButton(controller)])


class UnlockButton(KindersicherungEntity, ButtonEntity):
    """Hebt die Sperre auf und setzt die Fehlversuche zurück."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Button."""
        super().__init__(controller, "unlock")

    async def async_press(self) -> None:
        """Entsperre."""
        await self._controller.async_unlock()


class LockNowButton(KindersicherungEntity, ButtonEntity):
    """Sperrt sofort für die konfigurierte Dauer."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Button."""
        super().__init__(controller, "lock_now")

    async def async_press(self) -> None:
        """Sperre sofort."""
        await self._controller.async_lock()
