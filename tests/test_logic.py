"""Tests der reinen Logik (ohne Home Assistant)."""

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
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


def test_school_night_windows():
    from datetime import date

    # Ferien ab Montag 2026-10-12; Feiertag Freitag 2026-10-09
    def school(day):
        return day.weekday() < 5 and day != date(2026, 10, 9) and day < date(2026, 10, 12)

    def days(day):
        return school(logic.school_window_day("21:00", day))

    # Mittwochabend vor Schultag: gesperrt, auch Donnerstagmorgen
    assert logic.is_in_window(datetime(2026, 10, 7, 21, 30), "21:00", "07:30", days)
    assert logic.is_in_window(datetime(2026, 10, 8, 6, 0), "21:00", "07:30", days)
    # Donnerstagabend vor Feiertag: frei
    assert not logic.is_in_window(datetime(2026, 10, 8, 22, 0), "21:00", "07:30", days)
    # Sonntagabend vor Ferienbeginn: frei
    assert not logic.is_in_window(datetime(2026, 10, 11, 22, 0), "21:00", "07:30", days)
    # Vormittags beginnendes Fenster bezieht sich auf den Tag selbst
    assert logic.school_window_day("00:00", date(2026, 10, 7)) == date(2026, 10, 7)
    assert logic.school_window_day("12:00", date(2026, 10, 7)) == date(2026, 10, 8)
    # Ende einer Ausnahme folgt den Schulabenden
    tz = UTC
    now = datetime(2026, 10, 8, 15, 0, tzinfo=tz)
    assert logic.exception_until(now, [("21:00", "07:30", days)]) == datetime(
        2026, 10, 9, 0, 0, tzinfo=tz
    )


def test_holiday_dates():
    from datetime import date

    first = date(2026, 10, 10)
    # ganztägig 12.10. bis einschließlich 23.10. (Ende exklusiv)
    events = [(date(2026, 10, 12), date(2026, 10, 24))]
    assert logic.holiday_dates(events, first, 4) == {date(2026, 10, 12), date(2026, 10, 13)}
    # Termin mit Uhrzeit, endet um Mitternacht: Folgetag zählt nicht
    events = [(datetime(2026, 10, 10, 0, 0), datetime(2026, 10, 11, 0, 0))]
    assert logic.holiday_dates(events, first, 4) == {date(2026, 10, 10)}


def test_daily_limit_for_and_allowed_apps():
    assert logic.daily_limit_for(90, None, None, True, True) == 90
    assert logic.daily_limit_for(90, 180, None, True, False) == 180
    assert logic.daily_limit_for(90, 180, 0, True, True) == 0
    assert logic.daily_limit_for(90, 180, 240, False, True) == 240
    assert logic.app_blocked("com.google.android.youtube.tv", ["youtube"], ["tvkids"])
    assert not logic.app_blocked("com.google.android.youtube.tvkids", ["youtube"], ["tvkids"])
    assert not logic.app_blocked("com.netflix.ninja", ["youtube"], [])


def test_bonus_status():
    rs = logic.RuleState
    d = logic.evaluate(rs(in_window=True, bonus_active=True))
    assert (d.status, d.restricted) == ("bonus", False)
    d = logic.evaluate(rs(in_window=True, bonus_active=True, limit_reached=True))
    assert (d.status, d.restricted) == ("limit", True)
    d = logic.evaluate(rs(in_window=True, bonus_active=True, has_blocked_apps=True))
    assert not d.apps_blocked
    d = logic.evaluate(rs(in_window=True, bonus_active=True, has_blocked_apps=True,
                          app_block_always=True))
    assert d.apps_blocked


def test_away_status():
    rs = logic.RuleState
    assert logic.evaluate(rs(away=True)).status == "away"
    assert logic.evaluate(rs(away=True, exception_active=True)).status == "exception"
    assert logic.evaluate(rs(away=True, locked=True)).status == "locked"
