"""Prüft, dass Übersetzungen, Icons und Entitäten zueinander passen."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kindersicherung.const import DOMAIN, WEEKDAYS

COMPONENT = Path(__file__).parent.parent / "custom_components" / DOMAIN
LANGUAGES = ("de", "en")


def _load(name: str) -> dict:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def test_languages_have_same_keys() -> None:
    de, en = (set(_values(_load(f"translations/{lang}.json"))) for lang in LANGUAGES)
    assert de - en == set(), "Nur in de.json"
    assert en - de == set(), "Nur in en.json"


def _values(data: dict, prefix: str = "") -> dict[str, str]:
    """Alle Texte eines verschachtelten Dicts mit ihrem Schlüsselpfad."""
    result: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result |= _values(value, f"{prefix}{key}.")
        else:
            result[f"{prefix}{key}"] = str(value)
    return result


def test_no_empty_translations() -> None:
    for lang in LANGUAGES:
        for path, text in _values(_load(f"translations/{lang}.json")).items():
            assert text.strip(), f"{lang}: {path} ist leer"


def test_icons_match_translated_entities() -> None:
    icons = _load("icons.json")["entity"]
    entities = _load("translations/de.json")["entity"]
    for platform, keys in icons.items():
        for key in keys:
            assert key in entities.get(platform, {}), f"Icon ohne Übersetzung: {platform}.{key}"
    for platform, keys in entities.items():
        for key in keys:
            assert key in icons.get(platform, {}), f"Übersetzung ohne Icon: {platform}.{key}"


def test_manifest_and_hacs_metadata() -> None:
    manifest = _load("manifest.json")
    assert manifest["domain"] == DOMAIN
    assert manifest["config_flow"] is True
    parts = manifest["version"].split(".")
    assert len(parts) == 3 and all(part.isdigit() for part in parts)
    hacs = json.loads((COMPONENT.parent.parent / "hacs.json").read_text(encoding="utf-8"))
    assert hacs["name"] == manifest["name"]


async def test_every_entity_is_translated(hass: HomeAssistant) -> None:
    """Jede angelegte Entität hat einen Namen in beiden Sprachen (auch mit Code)."""
    hass.states.async_set("media_player.tv", "off")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test TV",
        data={},
        options={
            "media_players": ["media_player.tv"],
            "time_start": "00:00:00",
            "time_end": "19:00:00",
            "weekdays": WEEKDAYS,
            "confirm_code": "1234",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    created = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert created
    for lang in LANGUAGES:
        entities = _load(f"translations/{lang}.json")["entity"]
        for item in created:
            name = entities.get(item.domain, {}).get(item.translation_key, {}).get("name")
            assert name, f"{lang}: {item.domain}.{item.translation_key} ohne Namen"
    assert await hass.config_entries.async_unload(entry.entry_id)
