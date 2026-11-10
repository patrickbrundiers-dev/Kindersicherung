"""Tests für Einrichtung, Optionen und Ablauf der Kindersicherung."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
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
    assert options["blocked_apps"] == ["youtube"]
    assert options["app_block_always"] is True
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
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {"devices", "schedule", "apps", "limit", "confirm"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "confirm"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"confirm_timeout": 30, "max_attempts": 5, "confirm_code": "4711"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["max_attempts"] == 5
    assert entry.options["confirm_code"] == "4711"
    # andere Bereiche bleiben unverändert
    assert entry.options["media_players"] == [TV]
    assert entry.options["time_end"] == "23:59:59"
    await hass.async_block_till_done()
    # Mit Code gibt es jetzt das Eingabefeld.
    assert _entity(hass, entry, "text", "code")

    # Code wieder entfernen: Feld leer lassen
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "confirm"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"confirm_timeout": 30, "max_attempts": 5}
    )
    assert "confirm_code" not in entry.options
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_options_schedule_and_apps_steps(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "schedule"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "time_start": "21:00:00",
            "time_end": "07:30:00",
            "weekdays": ["sun", "mon"],
            "at_window_start": "off",
            "warn_minutes": 10,
            "time_start_2": "22:30:00",
            "time_end_2": "08:00:00",
            "weekdays_2": ["fri", "sat"],
            "pause_entities": ["input_boolean.ferien"],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["weekdays_2"] == ["fri", "sat"]
    assert entry.options["warn_minutes"] == 10
    assert entry.runtime_data.at_start == "off"
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "schedule"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"time_start": "21:00:00", "time_end": "07:30:00", "weekdays": [],
         "at_window_start": "off", "warn_minutes": 10,
         "time_start_2": "22:30:00", "time_end_2": "08:00:00"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"weekdays": "no_weekday"}

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "apps"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"blocked_apps": ["youtube", "netflix"], "app_block_always": True,
         "app_release_minutes": 30},
    )
    assert entry.options["blocked_apps"] == ["youtube", "netflix"]
    assert entry.options["app_release_minutes"] == 30
    assert entry.options["weekdays_2"] == ["fri", "sat"]
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


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


async def _setup_with_tv_on(hass: HomeAssistant, **overrides) -> MockConfigEntry:
    hass.states.async_set(TV, "on")
    entry = MockConfigEntry(
        domain=DOMAIN, title="Test TV", data={}, options={**BASE_OPTIONS, **overrides}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _next_midnight():
    return (dt_util.now() + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


PAUSE = "input_boolean.ferien"


async def _setup_running_before_window(hass: HomeAssistant, **overrides) -> MockConfigEntry:
    """Fernseher läuft, solange keine Regeln gelten (Pause an)."""
    hass.states.async_set(PAUSE, "on")
    return await _setup_with_tv_on(hass, pause_entities=[PAUSE], **overrides)


async def _rules_begin(hass: HomeAssistant) -> None:
    hass.states.async_set(PAUSE, "off")
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)


async def test_turn_off_at_window_start(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup_running_before_window(hass, turn_off_at_start=True)
    assert entry.runtime_data.at_start == "off"
    assert not turn_off

    await _rules_begin(hass)
    assert len(turn_off) >= 1
    assert turn_off[0].data["entity_id"] == [TV]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_no_turn_off_at_window_start_by_default(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    notify = async_mock_service(hass, "notify", "send_message")
    entry = await _setup_running_before_window(hass, notify_entities=["notify.sprechen"])
    assert entry.runtime_data.at_start == "none"

    await _rules_begin(hass)
    async_fire_time_changed(hass, _next_midnight())
    await hass.async_block_till_done()
    await asyncio.sleep(1.2)
    assert not turn_off
    assert not notify
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_confirmation_at_window_start(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    notify = async_mock_service(hass, "notify", "send_message")
    entry = await _setup_running_before_window(
        hass, at_window_start="confirm", notify_entities=["notify.sprechen"]
    )
    await _rules_begin(hass)
    assert notify and notify[0].data["message"] == "Bitte bestätigen"
    await asyncio.sleep(1.2)
    assert turn_off
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_tv_running_at_startup_in_window_is_checked(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup_with_tv_on(hass)
    assert entry.runtime_data.waiting_for_confirmation
    await asyncio.sleep(1.2)
    assert turn_off
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_power_on_from_unavailable_needs_confirmation(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    hass.states.async_set(TV, "unavailable")
    entry = MockConfigEntry(domain=DOMAIN, title="Test TV", data={}, options=BASE_OPTIONS)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    controller = entry.runtime_data
    # Länger nicht verfügbar als die Lücke
    controller.sessions[TV].off_since -= timedelta(minutes=5)

    hass.states.async_set(TV, "on")
    await hass.async_block_till_done()
    assert controller.waiting_for_confirmation
    await asyncio.sleep(1.2)
    assert turn_off
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_flicker_keeps_confirmation(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup(hass)
    controller = entry.runtime_data
    await _tv_on(hass)
    await controller.async_confirm("switch")
    await asyncio.sleep(0.05)
    assert controller.sessions[TV].status == "confirmed"

    # kurz „aus“ und „nicht verfügbar“, dann wieder an: keine neue Abfrage
    for state in ("off", "unavailable", "on"):
        hass.states.async_set(TV, state)
        await hass.async_block_till_done()
    assert not controller.waiting_for_confirmation

    # länger aus: neue Sitzung, neue Abfrage
    hass.states.async_set(TV, "off")
    await hass.async_block_till_done()
    controller.sessions[TV].off_since -= timedelta(minutes=5)
    await _tv_on(hass)
    assert controller.waiting_for_confirmation
    await asyncio.sleep(1.2)
    assert turn_off
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_second_tv_during_confirmation_is_turned_off(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    tv2 = "media_player.tv2"
    hass.states.async_set(tv2, "off")
    entry = await _setup(hass, media_players=[TV, tv2])
    await _tv_on(hass)
    hass.states.async_set(tv2, "on")
    await hass.async_block_till_done()
    await asyncio.sleep(1.2)
    switched_off = {e for call in turn_off for e in call.data["entity_id"]}
    assert switched_off == {TV, tv2}
    assert entry.runtime_data.attempts == 1
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_turn_off_waits_for_state_before_retry(hass: HomeAssistant) -> None:
    from custom_components.kindersicherung import devices

    calls = []

    async def slow_off(call) -> None:
        calls.append(call)

        async def later() -> None:
            await asyncio.sleep(0.1)
            hass.states.async_set(TV, "off")

        hass.async_create_task(later())

    hass.services.async_register("media_player", "turn_off", slow_off)
    hass.states.async_set(TV, "on")
    assert await devices.async_turn_off(hass, [TV])
    assert len(calls) == 1

    # Fernseher reagiert gar nicht: drei Versuche
    calls.clear()
    hass.services.async_register("media_player", "turn_off", lambda call: calls.append(call))
    hass.states.async_set(TV, "on")
    assert not await devices.async_turn_off(hass, [TV])
    assert len(calls) == devices.TURN_OFF_TRIES


async def test_late_phone_confirmation_does_not_release_apps(hass: HomeAssistant) -> None:
    async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup(hass, blocked_apps=["youtube"])
    controller = entry.runtime_data
    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": controller.confirm_action_id}
    )
    await hass.async_block_till_done()
    assert not controller.app_released
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


# ------------------------------------------------- Apps, Pause, Ausnahme, Limit
YOUTUBE = {"app_id": "com.google.android.youtube.tv", "app_name": "YouTube"}


async def test_blocked_app_without_remote_turns_tv_off(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup(hass, blocked_apps=["youtube"])
    hass.states.async_set(TV, "on", {"app_id": "ar.tvplayer.tv"})
    await hass.async_block_till_done()
    # Bestätigen, damit nur die App-Sperre greift
    await entry.runtime_data.async_confirm("switch")
    await hass.async_block_till_done()
    assert not turn_off

    hass.states.async_set(TV, "playing", YOUTUBE)
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)
    assert len(turn_off) >= 1
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_blocked_app_uses_remote_home(hass: HomeAssistant) -> None:
    from homeassistant.helpers import device_registry as dr

    send_command = async_mock_service(hass, "remote", "send_command")
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    tv_entry = MockConfigEntry(domain="androidtv_remote")
    tv_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=tv_entry.entry_id, identifiers={("androidtv_remote", "tv1")}
    )
    ent_reg = er.async_get(hass)
    player = ent_reg.async_get_or_create(
        "media_player", "androidtv_remote", "tv1", device_id=device.id
    ).entity_id
    remote = ent_reg.async_get_or_create(
        "remote", "androidtv_remote", "tv1", device_id=device.id
    ).entity_id

    hass.states.async_set(player, "off")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Leonie",
        data={},
        options={**BASE_OPTIONS, "media_players": [player], "blocked_apps": ["youtube"]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set(player, "playing", YOUTUBE)
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)
    assert send_command and send_command[0].data["entity_id"] == remote
    assert send_command[0].data["command"] == "HOME"
    await asyncio.sleep(1.2)  # Bestätigung läuft ab
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert turn_off  # wegen fehlender Bestätigung


async def test_pause_entity_suspends_window(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    hass.states.async_set("input_boolean.ferien", "on")
    entry = await _setup(hass, pause_entities=["input_boolean.ferien"])
    restricted = _entity(hass, entry, "binary_sensor", "restricted")
    assert hass.states.get(restricted).state == "off"
    await _tv_on(hass)
    await asyncio.sleep(1.2)
    assert not turn_off
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_allow_today_and_end_exception(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup(hass)
    allow = _entity(hass, entry, "button", "allow_today")
    end = _entity(hass, entry, "button", "end_exception")
    until = _entity(hass, entry, "sensor", "exception_until")

    await hass.services.async_call("button", "press", {"entity_id": allow}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(until).state not in ("unknown", "unavailable")
    await _tv_on(hass)
    await asyncio.sleep(1.2)
    assert not turn_off

    await hass.services.async_call("button", "press", {"entity_id": end}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(until).state == "unknown"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_daily_limit_turns_off_and_requires_confirmation(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    notify = async_mock_service(hass, "notify", "send_message")
    entry = await _setup_with_tv_on(
        hass,
        weekdays=[],
        daily_limit_minutes=3,
        warn_minutes=1,
        notify_entities=["notify.sprechen"],
    )
    controller = entry.runtime_data
    screen_time = _entity(hass, entry, "sensor", "screen_time")
    now = dt_util.now()
    for minute in range(2):
        await controller.async_minute_tick(now + timedelta(minutes=minute))
    await hass.async_block_till_done()
    assert hass.states.get(screen_time).state == "2"
    assert any("Noch 1 Minute " in c.data["message"] for c in notify)
    assert not turn_off

    await controller.async_minute_tick(now + timedelta(minutes=2))
    await hass.async_block_till_done()
    assert controller.limit_reached
    assert controller.restricted
    assert turn_off
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_warning_before_window_start(hass: HomeAssistant) -> None:
    notify = async_mock_service(hass, "notify", "send_message")
    async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup_with_tv_on(
        hass, time_start="21:00:00", time_end="07:30:00", warn_minutes=10,
        notify_entities=["notify.sprechen"],
    )
    moment = dt_util.now().replace(hour=20, minute=50, second=0, microsecond=0)
    await entry.runtime_data.async_minute_tick(moment)
    await hass.async_block_till_done()
    assert any("In 10 Minuten" in c.data["message"] for c in notify)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_app_block_always_and_code_release(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    notify = async_mock_service(hass, "notify", "mobile_app_test")
    entry = await _setup_with_tv_on(
        hass,
        weekdays=[],  # kein Zeitfenster: nur die App-Sperre zählt
        blocked_apps=["youtube"],
        app_block_always=True,
        confirm_code="4711",
        notify_services=["mobile_app_test"],
    )
    controller = entry.runtime_data
    code = _entity(hass, entry, "text", "code")
    released = _entity(hass, entry, "sensor", "app_release_until")

    hass.states.async_set(TV, "playing", YOUTUBE)
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)
    assert len(turn_off) >= 1
    hass.states.async_set(TV, "off")  # Fernseher ist aus, keine Wiederholung
    await hass.async_block_till_done()
    actions = notify[-1].data["data"]["actions"]
    assert actions[0]["action"] == controller.app_action_id

    # falscher Code: Fehlversuch, keine Freigabe
    await hass.services.async_call(
        "text", "set_value", {"entity_id": code, "value": "0000"}, blocking=True
    )
    assert controller.attempts == 1
    assert not controller.app_released

    # richtiger Code: YouTube erlaubt
    await hass.services.async_call(
        "text", "set_value", {"entity_id": code, "value": "4711"}, blocking=True
    )
    await hass.async_block_till_done()
    assert controller.app_released
    assert hass.states.get(released).state not in ("unknown", "unavailable")
    calls = len(turn_off)
    hass.states.async_set(TV, "on", {"app_id": "ar.tvplayer.tv"})
    hass.states.async_set(TV, "playing", YOUTUBE)
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)
    assert len(turn_off) == calls
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_app_release_via_phone_button(hass: HomeAssistant) -> None:
    async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup_with_tv_on(
        hass, weekdays=[], blocked_apps=["youtube"], app_block_always=True
    )
    controller = entry.runtime_data
    assert controller.app_block_active
    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": controller.app_action_id}
    )
    await hass.async_block_till_done()
    assert controller.app_released
    assert not controller.app_block_active
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_old_entries_block_apps_only_in_window(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup_with_tv_on(hass, weekdays=[], blocked_apps=["youtube"])
    hass.states.async_set(TV, "playing", YOUTUBE)
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)
    assert not turn_off
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_dashboard_entities_change_options_without_reload(hass: HomeAssistant) -> None:

    entry = await _setup(hass, daily_limit_minutes=0)
    controller = entry.runtime_data
    start = _entity(hass, entry, "time", "window_start")
    limit = _entity(hass, entry, "number", "daily_limit")
    always = _entity(hass, entry, "switch", "app_block_always")

    await hass.services.async_call(
        "time", "set_value", {"entity_id": start, "time": "21:00:00"}, blocking=True
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": limit, "value": 90}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": always}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.options["time_start"] == "21:00:00"
    assert entry.options["daily_limit_minutes"] == 90
    assert entry.options["app_block_always"] is True
    # derselbe Controller: kein Neuladen
    assert entry.runtime_data is controller
    assert hass.states.get(start).state == "21:00:00"
    assert hass.states.get(limit).state == "90.0"
    assert hass.states.get(always).state == "on"
    assert controller.windows[0][0] == "21:00:00"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_penalty_locks_for_configured_hours(hass: HomeAssistant) -> None:
    async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup(hass)
    controller = entry.runtime_data
    penalty = _entity(hass, entry, "button", "penalty")
    hours = _entity(hass, entry, "number", "penalty_hours")
    locked = _entity(hass, entry, "binary_sensor", "locked")
    assert hass.states.get(hours).state == "24.0"

    controller.app_release_until = dt_util.utcnow() + timedelta(minutes=30)
    before = dt_util.utcnow()
    await hass.services.async_call(
        "button", "press", {"entity_id": penalty}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(locked).state == "on"
    assert controller.app_release_until is None
    delta = controller.lock_until - before
    assert timedelta(hours=23, minutes=59) < delta <= timedelta(hours=24, minutes=1)
    # Datum im Text, weil die Sperre nicht heute endet
    assert "." in controller._lock_until_text()

    # nach 23 Stunden noch gesperrt
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=23))
    await hass.async_block_till_done()
    assert hass.states.get(locked).state == "on"

    # kürzere Strafe verkürzt eine längere Sperre nicht
    await hass.services.async_call(
        "number", "set_value", {"entity_id": hours, "value": 2}, blocking=True
    )
    await hass.async_block_till_done()
    assert entry.runtime_data is controller
    until = controller.lock_until
    await hass.services.async_call(
        "button", "press", {"entity_id": penalty}, blocking=True
    )
    await hass.async_block_till_done()
    assert controller.lock_until == until

    # Entsperren hebt die Strafe auf
    await hass.services.async_call(
        "button", "press", {"entity_id": _entity(hass, entry, "button", "unlock")},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(locked).state == "off"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_screensaver_does_not_count_as_screen_time(hass: HomeAssistant) -> None:
    entry = await _setup_with_tv_on(hass, weekdays=[])
    controller = entry.runtime_data
    now = dt_util.now()
    await controller.async_minute_tick(now)
    assert controller.screen_time_minutes == 1
    hass.states.async_set(
        TV, "on", {"app_id": "com.google.android.apps.tv.dreamx"}
    )
    await hass.async_block_till_done()
    await controller.async_minute_tick(now + timedelta(minutes=1))
    await controller.async_minute_tick(now + timedelta(minutes=2))
    assert controller.screen_time_minutes == 1
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_status_sensor_and_apps_closed(hass: HomeAssistant) -> None:
    async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup(hass, weekdays=[], blocked_apps=["youtube"], app_block_always=True)
    controller = entry.runtime_data
    status = _entity(hass, entry, "sensor", "status")
    closed = _entity(hass, entry, "sensor", "apps_closed")
    assert hass.states.get(status).state == "free"
    assert hass.states.get(status).attributes["apps_blocked"] is True

    await controller.async_penalty()
    await hass.async_block_till_done()
    assert hass.states.get(status).state == "locked"
    assert hass.states.get(status).attributes["until"]

    await controller.async_unlock()
    await controller.async_allow_today()
    await hass.async_block_till_done()
    assert hass.states.get(status).state == "exception"
    await controller.async_end_exception()

    hass.states.async_set(TV, "on", YOUTUBE)
    await hass.async_block_till_done()
    await asyncio.sleep(0.1)
    assert hass.states.get(closed).state == "1"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def _android_tv(hass: HomeAssistant) -> tuple[str, str]:
    from homeassistant.helpers import device_registry as dr

    tv_entry = MockConfigEntry(domain="androidtv_remote")
    tv_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=tv_entry.entry_id, identifiers={("androidtv_remote", "tv9")}
    )
    ent_reg = er.async_get(hass)
    player = ent_reg.async_get_or_create(
        "media_player", "androidtv_remote", "tv9", device_id=device.id
    ).entity_id
    remote = ent_reg.async_get_or_create(
        "remote", "androidtv_remote", "tv9", device_id=device.id
    ).entity_id
    return player, remote


async def test_app_still_running_after_home_turns_tv_off(hass: HomeAssistant) -> None:
    player, _remote = await _android_tv(hass)
    home_calls = []

    async def home(call) -> None:
        home_calls.append(call)
        if len(home_calls) == 1:
            hass.states.async_set(player, "on", {"app_id": "com.google.android.tvlauncher"})

    hass.services.async_register("remote", "send_command", home)
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    hass.states.async_set(player, "on", {"app_id": "ar.tvplayer.tv"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Leonie",
        data={},
        options={**BASE_OPTIONS, "media_players": [player], "weekdays": [],
                 "blocked_apps": ["youtube"], "app_block_always": True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Home hilft: App ist weg, Fernseher bleibt an
    hass.states.async_set(player, "playing", YOUTUBE)
    await hass.async_block_till_done()
    await asyncio.sleep(0.3)
    assert len(home_calls) == 1
    assert not turn_off

    # Home hilft nicht: nach der Kontrolle wird ausgeschaltet
    hass.states.async_set(player, "playing", YOUTUBE)
    await hass.async_block_till_done()
    await asyncio.sleep(0.3)
    assert len(home_calls) == 2
    assert turn_off
    assert entry.runtime_data.stats["apps_closed"] == 2
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_diagnostics_hide_code_and_logbook_event(hass: HomeAssistant) -> None:
    from custom_components.kindersicherung.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    async_mock_service(hass, "media_player", "turn_off")
    events = []
    hass.bus.async_listen("kindersicherung_action", events.append)
    entry = await _setup(hass, confirm_code="4711")
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["options"]["confirm_code"] == "**REDACTED**"
    assert diag["state"]["status"] == "window"

    await entry.runtime_data.async_lock()
    hass.states.async_set(TV, "on")
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)
    assert any(e.data["action"] == "turn_off" and e.data["reason"] == "locked" for e in events)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_school_nights_with_workday_and_holiday_calendar(hass: HomeAssistant) -> None:
    from homeassistant.core import SupportsResponse

    today = dt_util.now().date()
    tomorrow = today + timedelta(days=1)

    async def check_date(call):
        day = call.data["check_date"]
        return {call.data["entity_id"]: {"workday": day.weekday() < 7}}

    async def get_events(call):
        # Morgen sind Ferien (ganztägig)
        return {
            call.data["entity_id"]: {
                "events": [
                    {
                        "start": tomorrow.isoformat(),
                        "end": (tomorrow + timedelta(days=1)).isoformat(),
                        "summary": "Herbstferien",
                    }
                ]
            }
        }

    hass.services.async_register(
        "workday", "check_date", check_date, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    entry = await _setup(
        hass,
        time_start="00:00:00",
        time_end="00:00:00",  # ganztägig, bezieht sich auf den Tag selbst
        school_nights_only=True,
        workday_entity="binary_sensor.arbeitstag",
        holiday_calendars=["calendar.schulferien"],
        daily_limit_minutes=60,
        daily_limit_holiday=0,
    )
    controller = entry.runtime_data
    await hass.async_block_till_done()
    assert not controller.is_school_day(tomorrow)
    assert controller.is_school_day(today)
    assert controller.in_window  # heute Schultag, ganztägig
    diag = controller.diagnostics()
    assert diag["school_days"][tomorrow.isoformat()] is False

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_holiday_and_weekend_limits(hass: HomeAssistant) -> None:
    hass.states.async_set("input_boolean.ferien", "on")
    entry = await _setup(
        hass,
        weekdays=[],
        daily_limit_minutes=60,
        daily_limit_weekend=120,
        daily_limit_holiday=0,
        pause_entities=["input_boolean.ferien"],
    )
    controller = entry.runtime_data
    assert controller.holiday_today
    assert controller.daily_limit == 0
    hass.states.async_set("input_boolean.ferien", "off")
    await hass.async_block_till_done()
    expected = 120 if dt_util.now().weekday() >= 5 else 60
    assert controller.daily_limit == expected
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_bonus_extends_limit_and_window(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup(hass, daily_limit_minutes=30, bonus_minutes=15)
    controller = entry.runtime_data
    controller.screen_time_minutes = 30
    controller.limit_reached = True
    bonus = _entity(hass, entry, "button", "bonus")
    status = _entity(hass, entry, "sensor", "status")

    await hass.services.async_call("button", "press", {"entity_id": bonus}, blocking=True)
    await hass.async_block_till_done()
    assert controller.daily_limit == 45
    assert not controller.limit_reached
    assert controller.bonus_active
    assert hass.states.get(status).state == "bonus"

    # In der Bonuszeit braucht Einschalten keine Bestätigung
    await _tv_on(hass)
    assert not controller.waiting_for_confirmation
    await asyncio.sleep(1.2)
    assert not turn_off

    # zweiter Druck verlängert
    until = controller.bonus_until
    await controller.async_bonus()
    assert controller.bonus_until == until + timedelta(minutes=15)
    assert controller.daily_limit == 60
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_confirmation_expires_after_valid_minutes(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    notify = async_mock_service(hass, "notify", "send_message")
    entry = await _setup(
        hass, confirm_valid_minutes=60, warn_minutes=10, notify_entities=["notify.sprechen"]
    )
    controller = entry.runtime_data
    await _tv_on(hass)
    await controller.async_confirm("switch")
    await asyncio.sleep(0.05)
    session = controller.sessions[TV]
    assert session.status == "confirmed"
    assert session.confirmed_until is not None

    # Vorwarnung 10 Minuten vorher
    warn_at = dt_util.as_local(session.confirmed_until) - timedelta(minutes=10)
    await controller.async_minute_tick(warn_at)
    assert any("endet die Fernseh-Freigabe" in c.data["message"] for c in notify)

    # abgelaufen: neue Abfrage, ohne Antwort aus
    session.confirmed_until = dt_util.utcnow() - timedelta(seconds=1)
    await controller.async_minute_tick(dt_util.now())
    assert controller.waiting_for_confirmation
    await asyncio.sleep(1.2)
    assert turn_off
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_allowed_app_is_not_closed(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    entry = await _setup_with_tv_on(
        hass, weekdays=[], blocked_apps=["youtube"], allowed_apps=["tvkids"],
        app_block_always=True,
    )
    hass.states.async_set(TV, "playing", {"app_id": "com.google.android.youtube.tvkids"})
    await hass.async_block_till_done()
    await asyncio.sleep(0.3)
    assert not turn_off
    assert entry.runtime_data.stats["apps_closed"] == 0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_options_new_fields(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "limit"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"daily_limit_minutes": 90, "daily_limit_weekend": 0, "bonus_minutes": 15},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["daily_limit_weekend"] == 0
    assert "daily_limit_holiday" not in entry.options
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "schedule"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"time_start": "21:00:00", "time_end": "07:30:00", "weekdays": WEEKDAYS,
         "school_nights_only": True, "workday_entity": "binary_sensor.arbeitstag",
         "holiday_calendars": ["calendar.schulferien"], "at_window_start": "off",
         "warn_minutes": 10, "time_start_2": "22:30:00", "time_end_2": "08:00:00"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["school_nights_only"] is True
    assert entry.options["workday_entity"] == "binary_sensor.arbeitstag"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_tv_only_when_someone_is_home(hass: HomeAssistant) -> None:
    turn_off = async_mock_service(hass, "media_player", "turn_off")
    events = []
    hass.bus.async_listen("kindersicherung_action", events.append)
    hass.states.async_set("person.kind", "not_home")
    entry = await _setup(hass, weekdays=[], presence_entities=["person.kind"])
    controller = entry.runtime_data
    status = _entity(hass, entry, "sensor", "status")
    assert hass.states.get(status).state == "away"

    await _tv_on(hass)
    assert turn_off
    assert any(e.data["reason"] == "away" for e in events)

    # zu Hause: Fernseher bleibt an
    turn_off.clear()
    hass.states.async_set(TV, "off")
    hass.states.async_set("person.kind", "home")
    await hass.async_block_till_done()
    await _tv_on(hass)
    await asyncio.sleep(0.3)
    assert not turn_off
    assert hass.states.get(status).state == "free"

    # geht weg, während der Fernseher läuft: aus
    hass.states.async_set("person.kind", "not_home")
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)
    assert turn_off

    # unbekannt zählt als zu Hause, Ausnahme hebt es auf
    hass.states.async_set("person.kind", "unknown")
    await hass.async_block_till_done()
    assert not controller.away
    hass.states.async_set("person.kind", "not_home")
    await controller.async_allow_today()
    await hass.async_block_till_done()
    assert hass.states.get(status).state == "exception"
    assert await hass.config_entries.async_unload(entry.entry_id)
