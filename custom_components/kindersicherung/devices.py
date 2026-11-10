"""Fernseher steuern: ausschalten mit Kontrolle, Home-Taste über die Fernbedienung."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import INACTIVE_STATES

_LOGGER = logging.getLogger(__name__)

TURN_OFF_TRIES = 3
# So lange wird nach dem Ausschalten auf den neuen Zustand gewartet, bevor es
# noch einmal versucht wird. Bei Android TV ist „Ausschalten“ die Power-Taste:
# Ein zweiter Druck, bevor der Fernseher „aus“ meldet, würde ihn wieder einschalten.
TURN_OFF_WAIT = 10.0
POLL_INTERVAL = 0.5


def is_active(hass: HomeAssistant, entity_id: str) -> bool:
    """Läuft der Media Player (nicht aus, Standby oder nicht verfügbar)?"""
    state = hass.states.get(entity_id)
    return state is not None and state.state not in INACTIVE_STATES


async def async_wait_until(
    condition: Callable[[], bool], timeout: float, interval: float = POLL_INTERVAL
) -> bool:
    """Warte bis `condition()` wahr ist, höchstens `timeout` Sekunden."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if condition():
            return True
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(interval, remaining))


async def async_turn_off(
    hass: HomeAssistant,
    entity_ids: Iterable[str],
    keep_going: Callable[[str], bool] = lambda _entity_id: True,
) -> bool:
    """Ausschalten; erst wiederholen, wenn der Zustand nach der Wartezeit noch „an“ ist.

    `keep_going(entity_id)` False beendet die Versuche für dieses Gerät, z. B.
    weil es zwischendurch aus war oder inzwischen freigegeben wurde.
    """
    ids = list(entity_ids)
    for _ in range(TURN_OFF_TRIES):
        pending = [
            entity_id
            for entity_id in ids
            if keep_going(entity_id) and is_active(hass, entity_id)
        ]
        if not pending:
            return True
        try:
            await hass.services.async_call(
                "media_player", "turn_off", {"entity_id": pending}, blocking=True
            )
        except Exception:
            _LOGGER.warning("Ausschalten von %s fehlgeschlagen", pending, exc_info=True)
        if await async_wait_until(
            lambda ids=pending: not any(keep_going(e) and is_active(hass, e) for e in ids),
            TURN_OFF_WAIT,
        ):
            return True
    return not any(keep_going(e) and is_active(hass, e) for e in ids)


def remote_for(hass: HomeAssistant, media_player: str) -> str | None:
    """Fernbedienungs-Entität (remote.*) desselben Geräts, falls vorhanden."""
    registry = er.async_get(hass)
    entry = registry.async_get(media_player)
    if entry is None or entry.device_id is None:
        return None
    for candidate in er.async_entries_for_device(registry, entry.device_id):
        if candidate.domain == "remote":
            return candidate.entity_id
    return None


async def async_press_home(hass: HomeAssistant, remote: str) -> bool:
    """Home-Taste drücken. False, wenn der Befehl fehlschlägt."""
    try:
        await hass.services.async_call(
            "remote", "send_command", {"entity_id": remote, "command": "HOME"}, blocking=True
        )
    except Exception:
        _LOGGER.warning("Home-Taste über %s fehlgeschlagen", remote, exc_info=True)
        return False
    return True
