"""Einrichtung (kurz) und Optionen nach Bereichen (Menü)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)

from .const import (
    APP_SUGGESTIONS,
    CONF_APP_BLOCK_ALWAYS,
    CONF_APP_RELEASE_MINUTES,
    CONF_BLOCKED_APPS,
    CONF_DAILY_LIMIT_MINUTES,
    CONF_PAUSE_ENTITIES,
    CONF_TIME_END_2,
    CONF_TIME_START_2,
    CONF_WARN_MINUTES,
    CONF_WEEKDAYS_2,
    DEFAULT_APP_BLOCK_ALWAYS,
    DEFAULT_APP_RELEASE_MINUTES,
    DEFAULT_BLOCKED_APPS,
    DEFAULT_DAILY_LIMIT_MINUTES,
    DEFAULT_TIME_END_2,
    DEFAULT_TIME_START_2,
    DEFAULT_WARN_MINUTES,
    CONF_ACTIONABLE,
    CONF_ANNOUNCE_LOCK,
    CONF_ATTEMPT_RESET_MINUTES,
    CONF_CONFIRM_CODE,
    CONF_CONFIRM_ENTITIES,
    CONF_CONFIRM_TIMEOUT,
    CONF_LOCK_MINUTES,
    CONF_MAX_ATTEMPTS,
    CONF_MEDIA_PLAYERS,
    CONF_MESSAGE,
    CONF_NAME,
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_SERVICES,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TURN_OFF_AT_START,
    CONF_WEEKDAYS,
    DEFAULT_ACTIONABLE,
    DEFAULT_ANNOUNCE_LOCK,
    DEFAULT_ATTEMPT_RESET_MINUTES,
    DEFAULT_CONFIRM_TIMEOUT,
    DEFAULT_LOCK_MINUTES,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MESSAGE,
    DEFAULT_TIME_END,
    DEFAULT_TIME_START,
    DEFAULT_TURN_OFF_AT_START,
    DOMAIN,
    WEEKDAYS,
)

DEFAULT_NAME = "Wohnzimmer TV"

LIST_KEYS = (
    CONF_MEDIA_PLAYERS,
    CONF_CONFIRM_ENTITIES,
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_SERVICES,
    CONF_WEEKDAYS_2,
    CONF_BLOCKED_APPS,
    CONF_PAUSE_ENTITIES,
)
INT_KEYS = (
    CONF_CONFIRM_TIMEOUT,
    CONF_MAX_ATTEMPTS,
    CONF_LOCK_MINUTES,
    CONF_ATTEMPT_RESET_MINUTES,
    CONF_WARN_MINUTES,
    CONF_DAILY_LIMIT_MINUTES,
    CONF_APP_RELEASE_MINUTES,
)

DEFAULTS: dict[str, Any] = {
    CONF_MEDIA_PLAYERS: [],
    CONF_NOTIFY_SERVICES: [],
    CONF_NOTIFY_ENTITIES: [],
    CONF_CONFIRM_ENTITIES: [],
    CONF_MESSAGE: DEFAULT_MESSAGE,
    CONF_ACTIONABLE: DEFAULT_ACTIONABLE,
    CONF_ANNOUNCE_LOCK: DEFAULT_ANNOUNCE_LOCK,
    CONF_TIME_START: DEFAULT_TIME_START,
    CONF_TIME_END: DEFAULT_TIME_END,
    CONF_WEEKDAYS: WEEKDAYS,
    CONF_TURN_OFF_AT_START: DEFAULT_TURN_OFF_AT_START,
    CONF_TIME_START_2: DEFAULT_TIME_START_2,
    CONF_TIME_END_2: DEFAULT_TIME_END_2,
    CONF_WEEKDAYS_2: [],
    CONF_PAUSE_ENTITIES: [],
    CONF_WARN_MINUTES: DEFAULT_WARN_MINUTES,
    CONF_DAILY_LIMIT_MINUTES: DEFAULT_DAILY_LIMIT_MINUTES,
    CONF_BLOCKED_APPS: DEFAULT_BLOCKED_APPS,
    CONF_APP_BLOCK_ALWAYS: DEFAULT_APP_BLOCK_ALWAYS,
    CONF_APP_RELEASE_MINUTES: DEFAULT_APP_RELEASE_MINUTES,
    CONF_CONFIRM_TIMEOUT: DEFAULT_CONFIRM_TIMEOUT,
    CONF_MAX_ATTEMPTS: DEFAULT_MAX_ATTEMPTS,
    CONF_LOCK_MINUTES: DEFAULT_LOCK_MINUTES,
    CONF_ATTEMPT_RESET_MINUTES: DEFAULT_ATTEMPT_RESET_MINUTES,
}

# Bereiche im Optionen-Menü.
STEPS: dict[str, tuple[str, ...]] = {
    "devices": (
        CONF_MEDIA_PLAYERS,
        CONF_NOTIFY_SERVICES,
        CONF_NOTIFY_ENTITIES,
        CONF_MESSAGE,
        CONF_ACTIONABLE,
        CONF_ANNOUNCE_LOCK,
    ),
    "schedule": (
        CONF_TIME_START,
        CONF_TIME_END,
        CONF_WEEKDAYS,
        CONF_TURN_OFF_AT_START,
        CONF_WARN_MINUTES,
        CONF_TIME_START_2,
        CONF_TIME_END_2,
        CONF_WEEKDAYS_2,
        CONF_PAUSE_ENTITIES,
    ),
    "apps": (CONF_BLOCKED_APPS, CONF_APP_BLOCK_ALWAYS, CONF_APP_RELEASE_MINUTES),
    "limit": (CONF_DAILY_LIMIT_MINUTES,),
    "confirm": (
        CONF_CONFIRM_CODE,
        CONF_CONFIRM_TIMEOUT,
        CONF_MAX_ATTEMPTS,
        CONF_LOCK_MINUTES,
        CONF_ATTEMPT_RESET_MINUTES,
        CONF_CONFIRM_ENTITIES,
    ),
}

# Einrichtung: nur das Nötigste.
SETUP_KEYS: tuple[str, ...] = (
    CONF_MEDIA_PLAYERS,
    CONF_NOTIFY_SERVICES,
    CONF_CONFIRM_CODE,
    CONF_TIME_START,
    CONF_TIME_END,
    CONF_WEEKDAYS,
    CONF_BLOCKED_APPS,
)


def _notify_service_names(hass: HomeAssistant) -> list[str]:
    """Alle vorhandenen notify-Dienste (z. B. mobile_app_xyz), ohne send_message."""
    try:
        services = hass.services.async_services_for_domain("notify")
    except AttributeError:
        services = hass.services.async_services().get("notify", {})
    return sorted(name for name in services if name != "send_message")


def _number(minimum: int, maximum: int, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.BOX,
        )
    )


def _slider(minimum: int, maximum: int, step: int, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.SLIDER,
        )
    )


def _weekday_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=WEEKDAYS,
            multiple=True,
            translation_key="weekdays",
            mode=SelectSelectorMode.LIST,
        )
    )


def _fields(
    hass: HomeAssistant, current: dict[str, Any], keys: tuple[str, ...]
) -> dict[Any, Any]:
    """Formularfelder für `keys`, vorbelegt mit `current` bzw. den Standards."""

    def value(key: str) -> Any:
        return current.get(key, DEFAULTS.get(key))

    def suggested(key: str) -> dict[str, Any]:
        val = current.get(key)
        return {"suggested_value": val} if val else {}

    def required(key: str) -> vol.Required:
        return vol.Required(key, default=value(key))

    builders: dict[str, Any] = {
        CONF_MEDIA_PLAYERS: lambda: (
            vol.Required(CONF_MEDIA_PLAYERS, description=suggested(CONF_MEDIA_PLAYERS)),
            EntitySelector(EntitySelectorConfig(domain="media_player", multiple=True)),
        ),
        CONF_NOTIFY_SERVICES: lambda: (
            vol.Optional(
                CONF_NOTIFY_SERVICES, description=suggested(CONF_NOTIFY_SERVICES)
            ),
            SelectSelector(
                SelectSelectorConfig(
                    options=_notify_service_names(hass),
                    multiple=True,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        ),
        CONF_NOTIFY_ENTITIES: lambda: (
            vol.Optional(
                CONF_NOTIFY_ENTITIES, description=suggested(CONF_NOTIFY_ENTITIES)
            ),
            EntitySelector(EntitySelectorConfig(domain="notify", multiple=True)),
        ),
        CONF_MESSAGE: lambda: (required(CONF_MESSAGE), TextSelector()),
        CONF_ACTIONABLE: lambda: (required(CONF_ACTIONABLE), BooleanSelector()),
        CONF_ANNOUNCE_LOCK: lambda: (required(CONF_ANNOUNCE_LOCK), BooleanSelector()),
        CONF_TIME_START: lambda: (required(CONF_TIME_START), TimeSelector()),
        CONF_TIME_END: lambda: (required(CONF_TIME_END), TimeSelector()),
        CONF_WEEKDAYS: lambda: (required(CONF_WEEKDAYS), _weekday_selector()),
        CONF_TURN_OFF_AT_START: lambda: (
            required(CONF_TURN_OFF_AT_START),
            BooleanSelector(),
        ),
        CONF_TIME_START_2: lambda: (required(CONF_TIME_START_2), TimeSelector()),
        CONF_TIME_END_2: lambda: (required(CONF_TIME_END_2), TimeSelector()),
        CONF_WEEKDAYS_2: lambda: (
            vol.Optional(CONF_WEEKDAYS_2, default=value(CONF_WEEKDAYS_2)),
            _weekday_selector(),
        ),
        CONF_PAUSE_ENTITIES: lambda: (
            vol.Optional(CONF_PAUSE_ENTITIES, default=value(CONF_PAUSE_ENTITIES)),
            EntitySelector(
                EntitySelectorConfig(
                    domain=["binary_sensor", "input_boolean", "calendar", "switch"],
                    multiple=True,
                )
            ),
        ),
        CONF_WARN_MINUTES: lambda: (required(CONF_WARN_MINUTES), _slider(0, 60, 5, "min")),
        CONF_DAILY_LIMIT_MINUTES: lambda: (
            required(CONF_DAILY_LIMIT_MINUTES),
            _slider(0, 600, 15, "min"),
        ),
        CONF_BLOCKED_APPS: lambda: (
            vol.Optional(CONF_BLOCKED_APPS, default=value(CONF_BLOCKED_APPS)),
            SelectSelector(
                SelectSelectorConfig(
                    options=APP_SUGGESTIONS,
                    multiple=True,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        ),
        CONF_APP_BLOCK_ALWAYS: lambda: (
            # Bestehende Einträge ohne Wert behalten „nur im Zeitfenster“.
            vol.Required(
                CONF_APP_BLOCK_ALWAYS,
                default=current.get(
                    CONF_APP_BLOCK_ALWAYS,
                    DEFAULT_APP_BLOCK_ALWAYS
                    if CONF_MEDIA_PLAYERS not in current
                    else False,
                ),
            ),
            BooleanSelector(),
        ),
        CONF_APP_RELEASE_MINUTES: lambda: (
            required(CONF_APP_RELEASE_MINUTES),
            _slider(15, 240, 15, "min"),
        ),
        CONF_CONFIRM_CODE: lambda: (
            vol.Optional(CONF_CONFIRM_CODE, description=suggested(CONF_CONFIRM_CODE)),
            TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        ),
        CONF_CONFIRM_ENTITIES: lambda: (
            vol.Optional(
                CONF_CONFIRM_ENTITIES, description=suggested(CONF_CONFIRM_ENTITIES)
            ),
            EntitySelector(
                EntitySelectorConfig(domain=["input_boolean", "switch"], multiple=True)
            ),
        ),
        CONF_CONFIRM_TIMEOUT: lambda: (required(CONF_CONFIRM_TIMEOUT), _number(5, 600, "s")),
        CONF_MAX_ATTEMPTS: lambda: (required(CONF_MAX_ATTEMPTS), _slider(1, 10, 1, "")),
        CONF_LOCK_MINUTES: lambda: (required(CONF_LOCK_MINUTES), _number(1, 1440, "min")),
        CONF_ATTEMPT_RESET_MINUTES: lambda: (
            required(CONF_ATTEMPT_RESET_MINUTES),
            _number(0, 1440, "min"),
        ),
    }
    result: dict[Any, Any] = {}
    for key in keys:
        marker, selector = builders[key]()
        result[marker] = selector
    return result


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if CONF_MEDIA_PLAYERS in user_input and not user_input[CONF_MEDIA_PLAYERS]:
        errors[CONF_MEDIA_PLAYERS] = "no_media_player"
    if CONF_WEEKDAYS in user_input and not user_input[CONF_WEEKDAYS]:
        errors[CONF_WEEKDAYS] = "no_weekday"
    code = str(user_input.get(CONF_CONFIRM_CODE) or "").strip()
    if code and not (code.isascii() and code.isdigit() and 4 <= len(code) <= 12):
        errors[CONF_CONFIRM_CODE] = "invalid_code"
    return errors


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    """Zahlen als int speichern, fehlende Listen leer lassen."""
    data = dict(user_input)
    data.pop(CONF_NAME, None)
    if CONF_CONFIRM_CODE in data:
        code = str(data.pop(CONF_CONFIRM_CODE) or "").strip()
        if code:
            data[CONF_CONFIRM_CODE] = code
    for key in INT_KEYS:
        if key in data:
            data[key] = int(data[key])
    for key in LIST_KEYS:
        if key in data:
            data[key] = [value for value in (data[key] or []) if str(value).strip()]
    return data


class KindersicherungConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung: Name, Geräte, Benachrichtigungen und Regeln."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KindersicherungOptionsFlow:
        """Optionen-Dialog."""
        return KindersicherungOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Einrichtung mit dem Nötigsten; alles Weitere später unter „Konfigurieren“."""
        errors: dict[str, str] = {}
        current: dict[str, Any] = dict(user_input or {})
        if user_input is not None:
            submitted = {CONF_MEDIA_PLAYERS: [], **user_input}
            errors = _validate(submitted)
            if not errors:
                title = user_input.get(CONF_NAME) or DEFAULT_NAME
                options = {**DEFAULTS, **_normalize(submitted)}
                return self.async_create_entry(title=title, data={}, options=options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=current.get(CONF_NAME, DEFAULT_NAME)
                ): TextSelector(),
                **_fields(self.hass, current, SETUP_KEYS),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class KindersicherungOptionsFlow(OptionsFlow):
    """Einstellungen nach Bereichen; jeder Bereich speichert für sich."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Auswahl des Bereichs."""
        return self.async_show_menu(step_id="init", menu_options=list(STEPS))

    async def _async_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        keys = STEPS[step_id]
        errors: dict[str, str] = {}
        current: dict[str, Any] = dict(self.config_entry.options)
        if user_input is not None:
            # Nicht ausgefüllte optionale Felder (z. B. geleerter Code) gelten als leer.
            submitted = {key: user_input.get(key) for key in keys}
            errors = _validate(submitted)
            if not errors:
                options = {
                    k: v for k, v in self.config_entry.options.items() if k not in keys
                }
                options.update(
                    {k: v for k, v in _normalize(submitted).items() if v is not None}
                )
                return self.async_create_entry(data=options)
            current.update(user_input)

        schema = vol.Schema(_fields(self.hass, current, keys))
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fernseher und Benachrichtigungen."""
        return await self._async_step("devices", user_input)

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Zeitfenster, Ferien und Vorwarnung."""
        return await self._async_step("schedule", user_input)

    async def async_step_apps(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Gesperrte Apps und Freigabe."""
        return await self._async_step("apps", user_input)

    async def async_step_limit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Tageslimit."""
        return await self._async_step("limit", user_input)

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Bestätigung, Code und Sperre."""
        return await self._async_step("confirm", user_input)
