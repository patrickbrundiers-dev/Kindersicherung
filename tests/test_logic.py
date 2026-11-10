"""Tests der reinen Logik (ohne Home Assistant)."""

import importlib.util
from datetime import datetime, timedelta, UTC
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

    tz = UTC
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

    tz = UTC
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


def test_parse_time_accepts_seconds():
    assert logic.parse_time("07:30") == logic.parse_time("07:30:00")
    assert logic.parse_time("23:59:59").second == 59


def test_window_end_is_exclusive_and_start_inclusive():
    tue = datetime(2026, 10, 6, 0, 0)
    assert logic.is_in_window(tue.replace(hour=8), "08:00", "09:00", ALL)
    assert not logic.is_in_window(tue.replace(hour=9), "08:00", "09:00", ALL)
    assert not logic.is_in_window(tue.replace(hour=7, minute=59), "08:00", "09:00", ALL)


def test_window_without_weekdays_is_off():
    now = datetime(2026, 10, 6, 12, 0)
    assert not logic.is_in_window(now, "00:00", "00:00", [])
    assert not logic.is_in_window(now, "21:00", "07:30", [])
    assert not logic.is_in_any_window(now, [])


def test_window_intervals_all_day_and_overnight():

    tz = UTC
    now = datetime(2026, 10, 6, 12, 0, tzinfo=tz)  # Dienstag
    # ganztägig nur Dienstag: genau ein Kalendertag
    assert logic.window_intervals(now, [("08:00", "08:00", ["tue"])]) == [
        (datetime(2026, 10, 6, tzinfo=tz), datetime(2026, 10, 7, tzinfo=tz))
    ]
    # über Mitternacht: Ende am Folgetag, sortiert
    intervals = logic.window_intervals(now, [("21:00", "07:30", ["mon", "wed"])])
    assert intervals == [
        (datetime(2026, 10, 5, 21, 0, tzinfo=tz), datetime(2026, 10, 6, 7, 30, tzinfo=tz)),
        (datetime(2026, 10, 7, 21, 0, tzinfo=tz), datetime(2026, 10, 8, 7, 30, tzinfo=tz)),
    ]


def test_next_midnight_keeps_timezone():
    from datetime import timezone

    tz = timezone(timedelta(hours=1))
    assert logic.next_midnight(datetime(2026, 10, 6, 23, 59, tzinfo=tz)) == datetime(
        2026, 10, 7, tzinfo=tz
    )
    assert logic.next_midnight(datetime(2026, 10, 6, 0, 0, tzinfo=tz)) == datetime(
        2026, 10, 7, tzinfo=tz
    )


def test_exception_until_all_day_window_runs_to_midnight():

    tz = UTC
    now = datetime(2026, 10, 6, 15, 0, tzinfo=tz)
    windows = [("00:00", "19:00", ALL)]
    assert logic.exception_until(now, windows) == datetime(2026, 10, 7, tzinfo=tz)


def test_starts_at_ignores_seconds():

    tz = UTC
    windows = [("21:00", "07:30", ["mon"])]
    assert logic.starts_at(datetime(2026, 10, 5, 21, 0, 42, tzinfo=tz), windows)
    assert not logic.starts_at(datetime(2026, 10, 5, 21, 1, tzinfo=tz), windows)


def test_app_matches_none_and_case():
    assert not logic.app_matches(None, ["youtube"])
    assert logic.app_matches("YOUTUBE", ["  youtube  "])
    assert not logic.app_matches("youtube", [])


def test_weekday_lists_are_identical():
    """const.WEEKDAYS (Editor) und logic.WEEKDAY_KEYS (Prüfung) müssen übereinstimmen."""
    from custom_components.kindersicherung.const import WEEKDAYS

    assert WEEKDAYS == logic.WEEKDAY_KEYS
