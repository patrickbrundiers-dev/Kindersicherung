"""Tests der reinen Logik (ohne Home Assistant)."""

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path

_path = Path(__file__).parent.parent / "custom_components" / "kindersicherung" / "logic.py"
_spec = importlib.util.spec_from_file_location("ks_logic", _path)
logic = importlib.util.module_from_spec(_spec)
sys.modules["ks_logic"] = logic
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


def test_evaluate():
    rs = logic.RuleState
    assert logic.evaluate(rs(enabled=False, in_window=True)).status == "off"
    d = logic.evaluate(rs(in_window=True))
    assert (d.status, d.restricted, d.apps_blocked) == ("window", True, False)
    d = logic.evaluate(rs(in_window=True, paused=True))
    assert (d.status, d.restricted) == ("paused", False)
    d = logic.evaluate(rs(in_window=True, paused=True, limit_reached=True))
    assert (d.status, d.restricted) == ("limit", True)
    d = logic.evaluate(rs(in_window=True, exception_active=True, has_blocked_apps=True,
                          app_block_always=True))
    assert (d.status, d.restricted, d.apps_blocked) == ("exception", False, False)
    d = logic.evaluate(rs(has_blocked_apps=True, app_block_always=True))
    assert (d.status, d.apps_blocked) == ("free", True)
    assert not logic.evaluate(rs(has_blocked_apps=True)).apps_blocked
    assert logic.evaluate(rs(has_blocked_apps=True, in_window=True)).apps_blocked
    assert not logic.evaluate(
        rs(has_blocked_apps=True, app_block_always=True, app_released=True)
    ).apps_blocked
    assert logic.evaluate(rs(locked=True, in_window=True)).status == "locked"


def test_sessions():
    gap = timedelta(minutes=2)
    t0 = datetime(2026, 11, 10, 21, 0)
    s = logic.Session(logic.SESSION_FREE)
    # Beginn der Regeln: läuft noch aus der freien Zeit
    logic.update_session(s, True, t0, True, gap)
    assert s.status == "free"
    assert logic.session_action(s, True, "off") == "turn_off"
    assert logic.session_action(s, True, "confirm") == "confirm"
    assert logic.session_action(s, True, "none") == "ok"
    assert logic.session_action(s, False, "off") == "ok"

    # kurz aus/nicht verfügbar: gleiche Sitzung
    s.status = logic.SESSION_CONFIRMED
    logic.update_session(s, False, t0, True, gap)
    logic.update_session(s, False, t0 + timedelta(seconds=30), True, gap)
    assert s.off_since == t0
    logic.update_session(s, True, t0 + timedelta(seconds=60), True, gap)
    assert s.status == "confirmed" and s.off_since is None
    assert logic.session_action(s, True, "off") == "ok"

    # länger aus: neue Sitzung braucht Bestätigung
    logic.update_session(s, False, t0 + timedelta(minutes=2), True, gap)
    logic.update_session(s, True, t0 + timedelta(minutes=5), True, gap)
    assert s.status == "new"
    assert logic.session_action(s, True, "none") == "confirm"

    # Regeln vorbei: frei, Freigaben enden
    s.status = logic.SESSION_CONFIRMED
    logic.update_session(s, True, t0 + timedelta(hours=11), False, gap)
    assert s.status == "free"

    # Freigabe mit Ablauf
    s = logic.Session(logic.SESSION_CONFIRMED, confirmed_until=t0 + timedelta(minutes=60))
    logic.update_session(s, True, t0 + timedelta(minutes=59), True, gap)
    assert s.status == "confirmed"
    logic.update_session(s, True, t0 + timedelta(minutes=60), True, gap)
    assert s.status == "new"

    # Speichern und Laden
    s = logic.Session(logic.SESSION_CONFIRMED, off_since=t0)
    assert logic.Session.from_dict(s.as_dict()) == logic.Session(
        logic.SESSION_CONFIRMED, off_since=t0
    )
    assert logic.Session.from_dict({"status": "kaputt"}).status == "new"
