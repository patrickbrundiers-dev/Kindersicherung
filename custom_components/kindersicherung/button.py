"""Buttons: Entsperren, Jetzt sperren, Heute erlauben, Ausnahme beenden."""

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
    async_add_entities(
        [
            UnlockButton(controller),
            LockNowButton(controller),
            AllowTodayButton(controller),
            EndExceptionButton(controller),
            PenaltyButton(controller),
            BonusButton(controller),
        ]
    )


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


class AllowTodayButton(KindersicherungEntity, ButtonEntity):
    """Setzt Zeitfenster, App-Sperre und Tageslimit für heute aus."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Button."""
        super().__init__(controller, "allow_today")

    async def async_press(self) -> None:
        """Ausnahme für heute."""
        await self._controller.async_allow_today()


class EndExceptionButton(KindersicherungEntity, ButtonEntity):
    """Beendet eine laufende Ausnahme."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Button."""
        super().__init__(controller, "end_exception")

    async def async_press(self) -> None:
        """Ausnahme beenden."""
        await self._controller.async_end_exception()


class PenaltyButton(KindersicherungEntity, ButtonEntity):
    """Strafe: sperrt die Fernseher für die eingestellte Dauer (Standard 24 Std.)."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Button."""
        super().__init__(controller, "penalty")

    async def async_press(self) -> None:
        """Strafe auslösen."""
        await self._controller.async_penalty()


class BonusButton(KindersicherungEntity, ButtonEntity):
    """Bonuszeit: Tageslimit und Sperrzeit um die eingestellten Minuten verlängern."""

    def __init__(self, controller: KindersicherungController) -> None:
        """Initialisiere den Button."""
        super().__init__(controller, "bonus")

    async def async_press(self) -> None:
        """Bonuszeit geben."""
        await self._controller.async_bonus()
