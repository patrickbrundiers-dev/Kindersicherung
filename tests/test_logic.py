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


def test_window_overnight_belongs_to_start_day():
    # 21:00-07:30 nur Montag: Montagabend und Dienstagmorgen gesperrt,
    # Montagmorgen (gehört zu Sonntag) nicht.
    mon = ["mon"]
    assert logic.is_in_window(datetime(2026, 10, 5, 21, 0), "21:00", "07:30", mon)
    assert logic.is_in_window(datetime(2026, 10, 6, 7, 29), "21:00", "07:30", mon)
    assert not logic.is_in_window(datetime(2026, 10, 6, 7, 30), "21:00", "07:30", mon)
    assert not logic.is_in_window(datetime(2026, 10, 5, 6, 0), "21:00", "07:30", mon)
    assert not logic.is_in_window(datetime(2026, 10, 6, 21, 0), "21:00", "07:30", mon)
    # Sonntag bis Donnerstag: Freitagmorgen gesperrt, Freitagabend frei,
    # Sonntagabend gesperrt.
    school = ["sun", "mon", "tue", "wed", "thu"]
    assert logic.is_in_window(datetime(2026, 10, 9, 6, 0), "21:00", "07:30", school)
    assert not logic.is_in_window(datetime(2026, 10, 9, 22, 0), "21:00", "07:30", school)
    assert not logic.is_in_window(datetime(2026, 10, 10, 6, 0), "21:00", "07:30", school)
    assert logic.is_in_window(datetime(2026, 10, 11, 21, 30), "21:00", "07:30", school)


def test_intervals_and_exception():
    from datetime import timezone

    tz = timezone.utc
    school = ["sun", "mon", "tue", "wed", "thu"]
    windows = [("21:00", "07:30", school)]
    # Dienstag 15:00: Ausnahme gilt bis Mittwoch 07:30
    now = datetime(2026, 10, 6, 15, 0, tzinfo=tz)
    assert logic.exception_until(now, windows) == datetime(2026, 10, 7, 7, 30, tzinfo=tz)
    # Mittwoch 06:00 (noch im Fenster von Dienstag): bis Donnerstag 07:30,
    # weil das heutige Abendfenster noch beginnt
    now = datetime(2026, 10, 7, 6, 0, tzinfo=tz)
    assert logic.exception_until(now, windows) == datetime(2026, 10, 8, 7, 30, tzinfo=tz)
    # Freitag 15:00: kein Fenster mehr, also bis Mitternacht
    now = datetime(2026, 10, 9, 15, 0, tzinfo=tz)
    assert logic.exception_until(now, windows) == datetime(2026, 10, 10, 0, 0, tzinfo=tz)


def test_starts_at_and_second_window():
    from datetime import timezone

    tz = timezone.utc
    windows = [("21:00", "07:30", ["mon"]), ("22:30", "08:00", ["sat"])]
    assert logic.starts_at(datetime(2026, 10, 5, 21, 0, 0, tzinfo=tz), windows)
    assert logic.starts_at(datetime(2026, 10, 5, 20, 50, tzinfo=tz), windows, 10)
    assert not logic.starts_at(datetime(2026, 10, 6, 21, 0, tzinfo=tz), windows)
    assert logic.starts_at(datetime(2026, 10, 10, 22, 30, tzinfo=tz), windows)
    assert logic.is_in_any_window(datetime(2026, 10, 11, 7, 0), windows)
    assert not logic.is_in_any_window(datetime(2026, 10, 11, 9, 0), windows)


def test_app_matches():
    assert logic.app_matches("com.google.android.youtube.tv YouTube", ["youtube"])
    assert logic.app_matches("com.netflix.ninja", ["YouTube", "netflix"])
    assert not logic.app_matches("ar.tvplayer.tv", ["youtube"])
    assert not logic.app_matches("", ["youtube"])
    assert not logic.app_matches("youtube", [" "])
