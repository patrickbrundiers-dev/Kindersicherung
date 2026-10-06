"""Tests der reinen Logik (ohne Home Assistant)."""

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

_path = Path(__file__).parent.parent / "custom_components" / "kindersicherung" / "logic.py"
_spec = importlib.util.spec_from_file_location("ks_logic", _path)
logic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(logic)

ALL = logic.WEEKDAY_KEYS


def test_window_default():
    # 2026-10-06 ist ein Dienstag
    assert logic.is_in_window(datetime(2026, 10, 6, 12, 0), "00:00:00", "19:00:00", ALL)
    assert logic.is_in_window(datetime(2026, 10, 6, 0, 0), "00:00:00", "19:00:00", ALL)
    assert not logic.is_in_window(datetime(2026, 10, 6, 19, 0), "00:00:00", "19:00:00", ALL)
    assert not logic.is_in_window(datetime(2026, 10, 6, 23, 30), "00:00:00", "19:00:00", ALL)


def test_window_overnight_and_all_day():
    assert logic.is_in_window(datetime(2026, 10, 6, 23, 0), "20:00", "06:00", ALL)
    assert logic.is_in_window(datetime(2026, 10, 6, 5, 0), "20:00", "06:00", ALL)
    assert not logic.is_in_window(datetime(2026, 10, 6, 12, 0), "20:00", "06:00", ALL)
    assert logic.is_in_window(datetime(2026, 10, 6, 12, 0), "08:00", "08:00", ALL)


def test_window_weekdays():
    assert not logic.is_in_window(datetime(2026, 10, 6, 12, 0), "00:00", "19:00", ["sat", "sun"])
    assert logic.is_in_window(datetime(2026, 10, 10, 12, 0), "00:00", "19:00", ["sat", "sun"])


def test_attempts():
    now = datetime(2026, 10, 6, 12, 0)
    assert logic.attempts_after_failure(0, None, now, 60) == 1
    assert logic.attempts_after_failure(2, now - timedelta(minutes=10), now, 60) == 3
    assert logic.attempts_after_failure(2, now - timedelta(minutes=90), now, 60) == 1
    assert logic.attempts_after_failure(2, now - timedelta(days=3), now, 0) == 3
