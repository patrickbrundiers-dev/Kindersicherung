"""Einrichtung und Optionen der Kindersicherung (alles im Editor einstellbar)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
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
    CONF_BLOCKED_APPS,
    CONF_DAILY_LIMIT_MINUTES,
    CONF_PAUSE_ENTITIES,
    CONF_TIME_END_2,
    CONF_TIME_START_2,
    CONF_WARN_MINUTES,
    CONF_WEEKDAYS_2,
    DEFAULT_BLOCKED_APPS,
    DEFAULT_DAILY_LIMIT_MINUTES,
    DEFAULT_TIME_END_2,
    DEFAULT_TIME_START_2,
    DEFAULT_WARN_MINUTES,
    SECTION_RULES,
    SECTION_SECOND_WINDOW,
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
)
SECTIONS = (SECTION_SECOND_WINDOW, SECTION_RULES)


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


def _weekday_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=WEEKDAYS,
            multiple=True,
            translation_key="weekdays",
            mode=SelectSelectorMode.LIST,
        )
    )


def _settings_schema(hass: HomeAssistant, current: dict[str, Any]) -> dict[Any, Any]:
    """Alle einstellbaren Felder; `current` liefert die Vorbelegung."""

    def suggested(key: str) -> dict[str, Any]:
        value = current.get(key)
        return {"suggested_value": value} if value else {}

    return {
        vol.Required(
            CONF_MEDIA_PLAYERS, description=suggested(CONF_MEDIA_PLAYERS)
        ): EntitySelector(EntitySelectorConfig(domain="media_player", multiple=True)),
        vol.Optional(
            CONF_NOTIFY_SERVICES, description=suggested(CONF_NOTIFY_SERVICES)
        ): SelectSelector(
            SelectSelectorConfig(
                options=_notify_service_names(hass),
                multiple=True,
                custom_value=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(
            CONF_NOTIFY_ENTITIES, description=suggested(CONF_NOTIFY_ENTITIES)
        ): EntitySelector(EntitySelectorConfig(domain="notify", multiple=True)),
        vol.Optional(
            CONF_CONFIRM_ENTITIES, description=suggested(CONF_CONFIRM_ENTITIES)
        ): EntitySelector(
            EntitySelectorConfig(domain=["input_boolean", "switch"], multiple=True)
        ),
        vol.Optional(
            CONF_CONFIRM_CODE, description=suggested(CONF_CONFIRM_CODE)
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Required(
            CONF_MESSAGE, default=current.get(CONF_MESSAGE, DEFAULT_MESSAGE)
        ): TextSelector(),
        vol.Required(
            CONF_ACTIONABLE, default=current.get(CONF_ACTIONABLE, DEFAULT_ACTIONABLE)
        ): BooleanSelector(),
        vol.Required(
            CONF_ANNOUNCE_LOCK,
            default=current.get(CONF_ANNOUNCE_LOCK, DEFAULT_ANNOUNCE_LOCK),
        ): BooleanSelector(),
        vol.Required(
            CONF_TIME_START, default=current.get(CONF_TIME_START, DEFAULT_TIME_START)
        ): TimeSelector(),
        vol.Required(
            CONF_TIME_END, default=current.get(CONF_TIME_END, DEFAULT_TIME_END)
        ): TimeSelector(),
        vol.Required(
            CONF_WEEKDAYS, default=current.get(CONF_WEEKDAYS, WEEKDAYS)
        ): _weekday_selector(),
        vol.Required(
            CONF_TURN_OFF_AT_START,
            default=current.get(CONF_TURN_OFF_AT_START, DEFAULT_TURN_OFF_AT_START),
        ): BooleanSelector(),
        vol.Required(
            CONF_CONFIRM_TIMEOUT,
            default=current.get(CONF_CONFIRM_TIMEOUT, DEFAULT_CONFIRM_TIMEOUT),
        ): _number(5, 600, "s"),
        vol.Required(
            CONF_MAX_ATTEMPTS,
            default=current.get(CONF_MAX_ATTEMPTS, DEFAULT_MAX_ATTEMPTS),
        ): _number(1, 20, ""),
        vol.Required(
            CONF_LOCK_MINUTES,
            default=current.get(CONF_LOCK_MINUTES, DEFAULT_LOCK_MINUTES),
        ): _number(1, 1440, "min"),
        vol.Required(
            CONF_ATTEMPT_RESET_MINUTES,
            default=current.get(
                CONF_ATTEMPT_RESET_MINUTES, DEFAULT_ATTEMPT_RESET_MINUTES
            ),
        ): _number(0, 1440, "min"),
        vol.Optional(SECTION_SECOND_WINDOW, default={}): section(
            vol.Schema(
                {
                    vol.Required(
                        CONF_TIME_START_2,
                        default=current.get(CONF_TIME_START_2, DEFAULT_TIME_START_2),
                    ): TimeSelector(),
                    vol.Required(
                        CONF_TIME_END_2,
                        default=current.get(CONF_TIME_END_2, DEFAULT_TIME_END_2),
                    ): TimeSelector(),
                    vol.Optional(
                        CONF_WEEKDAYS_2, default=current.get(CONF_WEEKDAYS_2, [])
                    ): _weekday_selector(),
                }
            ),
            {"collapsed": not current.get(CONF_WEEKDAYS_2)},
        ),
        vol.Optional(SECTION_RULES, default={}): section(
            vol.Schema(
                {
                    vol.Optional(
                        CONF_BLOCKED_APPS,
                        default=current.get(CONF_BLOCKED_APPS, DEFAULT_BLOCKED_APPS),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=APP_SUGGESTIONS,
                            multiple=True,
                            custom_value=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_PAUSE_ENTITIES,
                        default=current.get(CONF_PAUSE_ENTITIES, []),
                    ): EntitySelector(
                        EntitySelectorConfig(
                            domain=["binary_sensor", "input_boolean", "calendar", "switch"],
                            multiple=True,
                        )
                    ),
                    vol.Required(
                        CONF_WARN_MINUTES,
                        default=current.get(CONF_WARN_MINUTES, DEFAULT_WARN_MINUTES),
                    ): _number(0, 120, "min"),
                    vol.Required(
                        CONF_DAILY_LIMIT_MINUTES,
                        default=current.get(
                            CONF_DAILY_LIMIT_MINUTES, DEFAULT_DAILY_LIMIT_MINUTES
                        ),
                    ): _number(0, 1440, "min"),
                }
            ),
            {"collapsed": True},
        ),
    }


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Felder aus den Abschnitten auf die oberste Ebene holen."""
    data = dict(user_input)
    for key in SECTIONS:
        data.update(data.pop(key, None) or {})
    return data


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not user_input.get(CONF_MEDIA_PLAYERS):
        errors[CONF_MEDIA_PLAYERS] = "no_media_player"
    if not user_input.get(CONF_WEEKDAYS):
        errors[CONF_WEEKDAYS] = "no_weekday"
    code = str(user_input.get(CONF_CONFIRM_CODE) or "").strip()
    if code and not (code.isascii() and code.isdigit() and 4 <= len(code) <= 12):
        errors[CONF_CONFIRM_CODE] = "invalid_code"
    return errors


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    """Zahlen als int speichern, fehlende Listen leer lassen."""
    data = dict(user_input)
    data.pop(CONF_NAME, None)
    code = str(data.pop(CONF_CONFIRM_CODE, "") or "").strip()
    if code:
        data[CONF_CONFIRM_CODE] = code
    for key in INT_KEYS:
        if key in data:
            data[key] = int(data[key])
    for key in LIST_KEYS:
        data[key] = [value for value in (data.get(key) or []) if str(value).strip()]
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
        """Erster und einziger Schritt."""
        errors: dict[str, str] = {}
        current: dict[str, Any] = _flatten(user_input or {})
        if user_input is not None:
            user_input = current
            errors = _validate(user_input)
            if not errors:
                title = user_input.get(CONF_NAME) or DEFAULT_NAME
                return self.async_create_entry(
                    title=title, data={}, options=_normalize(user_input)
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=current.get(CONF_NAME, DEFAULT_NAME)
                ): TextSelector(),
                **_settings_schema(self.hass, current),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class KindersicherungOptionsFlow(OptionsFlow):
    """Alle Einstellungen nachträglich im Editor ändern."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Einziger Schritt."""
        errors: dict[str, str] = {}
        current: dict[str, Any] = dict(self.config_entry.options)
        if user_input is not None:
            user_input = _flatten(user_input)
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(data=_normalize(user_input))
            current = dict(user_input)

        schema = vol.Schema(_settings_schema(self.hass, current))
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
