"""Tests für Einrichtung, Optionen und Ablauf der Kindersicherung."""

from __future__ import annotations

import asyncio

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.kindersicherung.const import DOMAIN, WEEKDAYS

TV = "media_player.tv"

BASE_OPTIONS = {
    "media_players": [TV],
    "notify_services": [],
    "notify_entities": [],
    "confirm_entities": [],
    "message": "Bitte bestätigen",
    "actionable": True,
    "announce_lock": True,
    "time_start": "00:00:00",
    "time_end": "23:59:59",
    "weekdays": WEEKDAYS,
    "confirm_timeout": 1,
    "max_attempts": 3,
    "lock_minutes": 30,
    "attempt_reset_minutes": 60,
}


async def _setup(hass: HomeAssistant, **overrides) -> MockConfigEntry:
    hass.states.async_set(TV, "off")
    entry = MockConfigEntry(
        domain=DOMAIN, title="Test TV", data={}, options={**BASE_OPTIONS, **overrides}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id, f"{platform} {key} fehlt"
    return entity_id


async def _tv_on(hass: HomeAssistant) -> None:
    hass.states.async_set(TV, "on")
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)


# ---------------------------------------------------------------- Config Flow
async def test_config_flow_creates_entry_with_defaults(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Wohnzimmer TV", "media_players": [TV]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wohnzimmer TV"
    options = result["options"]
    assert options["media_players"] == [TV]
    assert options["confirm_timeout"] == 30
    assert options["max_attempts"] == 3
    assert options["lock_minutes"] == 30
    assert options["time_end"] == "19:00:00"
    assert options["weekdays"] == WEEKDAYS
    assert options["notify_services"] == []
    assert "confirm_code" not in options


async def test_config_flow_requires_media_player(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "TV", "media_players": []}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"media_players": "no_media_player"}


async def test_config_flow_rejects_invalid_code(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "TV", "media_players": [TV], "confirm_code": "12ab"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"confirm_code": "invalid_code"}


async def test_options_flow_updates_options(hass: HomeAssistant) -> None:
    entry = await _setup(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"media_players": [TV], "max_attempts": 5, "confirm_code": "4711"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["max_attempts"] == 5
    assert entry.options["confirm_code"] == "4711"
    await hass.async_block_till_done()
    # Mit Code gibt es jetzt das Eingabefeld.
    assert _entity(hass, entry, "text", "code")


# ------------------------------------------------------------------ Entitäten
async def test_entities_are_created(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    for platform, key in (
        ("switch", "enabled"),
        ("switch", "confirm"),
        ("binary_sensor", "locked"),
        ("sensor", "attempts"),
        ("sensor", "lock_until"),
        ("sensor", "confirmations"),
        ("sensor", "timeouts"),
        ("sensor", "wrong_codes"),
        ("sensor", "locks"),
        ("button", "unlock"),
        ("button", "lock_now"),
    ):
        _entity(hass, entry, platform, key)
    # ohne Code kein Eingabefeld
    assert (
        er.async_get(hass).async_get_entity_id("text", DOMAIN, f"{entry.entry_id}_code")
        is None
    )
    assert await hass.config_entries.async_unload(entry.entry_id)


# --------------------------------------------------------------------- Ablauf
async def test_confirmation_with_switch_keeps_tv_on(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    notify = async_mock_service(hass, "notify", "send_message")
    entry = await _setup(hass, notify_entities=["notify.sprechen"])
    confirm = _entity(hass, entry, "switch", "confirm")

    await _tv_on(hass)
    assert len(notify) == 1
    assert notify[0].data["message"] == "Bitte bestätigen"

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": confirm}, blocking=True
    )
    await asyncio.sleep(0.2)
    assert not turn_off
    assert hass.states.get(TV).state == "on"
    stat = _entity(hass, entry, "sensor", "confirmations")
    assert hass.states.get(stat).state == "1"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_timeout_turns_tv_off_and_counts(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup(hass)

    await _tv_on(hass)
    await asyncio.sleep(1.5)  # confirm_timeout = 1 s
    assert len(turn_off) >= 1
    assert turn_off[0].data["entity_id"] == [TV]
    attempts = _entity(hass, entry, "sensor", "attempts")
    assert hass.states.get(attempts).state == "1"
    timeouts = _entity(hass, entry, "sensor", "timeouts")
    assert hass.states.get(timeouts).state == "1"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_manual_lock_blocks_power_on(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup(hass)
    lock_button = _entity(hass, entry, "button", "lock_now")
    locked = _entity(hass, entry, "binary_sensor", "locked")

    await hass.services.async_call(
        "button", "press", {"entity_id": lock_button}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(locked).state == "on"

    await _tv_on(hass)
    await asyncio.sleep(0.1)
    assert len(turn_off) >= 1

    unlock_button = _entity(hass, entry, "button", "unlock")
    await hass.services.async_call(
        "button", "press", {"entity_id": unlock_button}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(locked).state == "off"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_outside_time_window_nothing_happens(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    notify = async_mock_service(hass, "notify", "send_message")
    entry = await _setup(hass, notify_entities=["notify.sprechen"], weekdays=[])
    await _tv_on(hass)
    await asyncio.sleep(1.2)
    assert not notify
    assert not turn_off
    assert await hass.config_entries.async_unload(entry.entry_id)


# ----------------------------------------------------------------- Zahlencode
async def test_code_confirms_and_wrong_code_fails(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup(hass, confirm_code="1234", confirm_timeout=5)
    code = _entity(hass, entry, "text", "code")
    confirm = _entity(hass, entry, "switch", "confirm")

    # Schalter zählt mit Code nicht
    await _tv_on(hass)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": confirm}, blocking=True
    )
    await asyncio.sleep(0.1)
    assert hass.states.get(confirm).state == "off"
    assert not turn_off

    # Falscher Code: sofort aus, Fehlversuch
    await hass.services.async_call(
        "text", "set_value", {"entity_id": code, "value": "9999"}, blocking=True
    )
    await asyncio.sleep(0.2)
    assert len(turn_off) >= 1
    wrong = _entity(hass, entry, "sensor", "wrong_codes")
    assert hass.states.get(wrong).state == "1"

    # Richtiger Code bestätigt
    turn_off.clear()
    hass.states.async_set(TV, "off")
    await hass.async_block_till_done()
    await _tv_on(hass)
    await hass.services.async_call(
        "text", "set_value", {"entity_id": code, "value": "1234"}, blocking=True
    )
    await asyncio.sleep(0.2)
    assert not turn_off
    confirmations = _entity(hass, entry, "sensor", "confirmations")
    assert hass.states.get(confirmations).state == "1"
    # Der Code taucht nie im Zustand auf
    assert hass.states.get(code).state in ("", "unknown")
    assert await hass.config_entries.async_unload(entry.entry_id)
