"""Konstanten für die Kindersicherung."""

from __future__ import annotations

DOMAIN = "kindersicherung"

STORAGE_VERSION = 1

CONF_NAME = "name"
CONF_MEDIA_PLAYERS = "media_players"
CONF_CONFIRM_ENTITIES = "confirm_entities"
CONF_CONFIRM_CODE = "confirm_code"
CONF_NOTIFY_ENTITIES = "notify_entities"
CONF_NOTIFY_SERVICES = "notify_services"
CONF_MESSAGE = "message"
CONF_ACTIONABLE = "actionable"
CONF_ANNOUNCE_LOCK = "announce_lock"
CONF_TIME_START = "time_start"
CONF_TIME_END = "time_end"
CONF_WEEKDAYS = "weekdays"
CONF_TURN_OFF_AT_START = "turn_off_at_start"
CONF_TIME_START_2 = "time_start_2"
CONF_TIME_END_2 = "time_end_2"
CONF_WEEKDAYS_2 = "weekdays_2"
CONF_BLOCKED_APPS = "blocked_apps"
CONF_APP_BLOCK_ALWAYS = "app_block_always"
CONF_APP_RELEASE_MINUTES = "app_release_minutes"
CONF_PENALTY_HOURS = "penalty_hours"
CONF_PAUSE_ENTITIES = "pause_entities"
CONF_WARN_MINUTES = "warn_minutes"
CONF_DAILY_LIMIT_MINUTES = "daily_limit_minutes"

CONF_CONFIRM_TIMEOUT = "confirm_timeout"
CONF_MAX_ATTEMPTS = "max_attempts"
CONF_LOCK_MINUTES = "lock_minutes"
CONF_ATTEMPT_RESET_MINUTES = "attempt_reset_minutes"

STAT_KEYS = ("confirmations", "timeouts", "wrong_codes", "locks", "apps_closed")

# Bildschirmschoner und ähnliche Leerlauf-Apps: zählen nicht als Bildschirmzeit.
IDLE_APPS = ["dreamx", "screensaver", "daydream", "backdrop"]

STATUS_OPTIONS = ["off", "locked", "exception", "limit", "window", "paused", "free"]

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

DEFAULT_MESSAGE = "Kindersicherung in der App bestätigen."
DEFAULT_TIME_START = "00:00:00"
DEFAULT_TIME_END = "19:00:00"
DEFAULT_CONFIRM_TIMEOUT = 30
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_LOCK_MINUTES = 30
DEFAULT_ATTEMPT_RESET_MINUTES = 60
DEFAULT_ACTIONABLE = True
DEFAULT_ANNOUNCE_LOCK = True
DEFAULT_TURN_OFF_AT_START = False
DEFAULT_TIME_START_2 = "22:00:00"
DEFAULT_TIME_END_2 = "08:00:00"
DEFAULT_WARN_MINUTES = 0
DEFAULT_DAILY_LIMIT_MINUTES = 0
DEFAULT_BLOCKED_APPS = ["youtube"]
DEFAULT_APP_BLOCK_ALWAYS = True
DEFAULT_APP_RELEASE_MINUTES = 60
DEFAULT_PENALTY_HOURS = 24

# Vorschläge für gesperrte Apps; Teil des App-Namens oder der App-ID genügt.
APP_SUGGESTIONS = ["youtube", "netflix", "disney", "amazon", "twitch", "tiktok"]

# Zustände, in denen ein Media Player als "aus" gilt.
INACTIVE_STATES = frozenset({"off", "standby", "unavailable", "unknown"})
# Nur aus diesen Zuständen heraus zählt ein Einschalten als "TV angemacht".
POWER_OFF_STATES = frozenset({"off", "standby"})

EVENT_CONFIRMED = f"{DOMAIN}_confirmed"
EVENT_FAILED = f"{DOMAIN}_failed"
EVENT_LOCKED = f"{DOMAIN}_locked"
EVENT_UNLOCKED = f"{DOMAIN}_unlocked"

MOBILE_APP_ACTION_EVENT = "mobile_app_notification_action"
CONFIRM_ACTION_PREFIX = "KINDERSICHERUNG_CONFIRM_"
APP_ACTION_PREFIX = "KINDERSICHERUNG_APP_"
