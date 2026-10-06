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
