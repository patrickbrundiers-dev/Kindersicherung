"""Gemeinsame Test-Fixtures."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Eigene Integrationen aus custom_components laden."""
    yield


@pytest.fixture(autouse=True)
def mock_storage(hass_storage):
    """Speicher im Test nicht auf die Platte schreiben."""
    yield hass_storage


@pytest.fixture(autouse=True)
def short_waits(monkeypatch):
    """Wartezeiten nach Ausschalten und Home-Taste im Test kurz halten."""
    from custom_components.kindersicherung import controller, devices

    monkeypatch.setattr(devices, "TURN_OFF_WAIT", 0.2)
    monkeypatch.setattr(devices, "POLL_INTERVAL", 0.05)
    monkeypatch.setattr(controller, "APP_CHECK_DELAY", 0.1)
