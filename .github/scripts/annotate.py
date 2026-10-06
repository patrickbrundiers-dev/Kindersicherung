"""Gibt das Ende des Testlogs als Annotation aus, damit es ohne Log-Zugriff lesbar ist."""

import pathlib

log = pathlib.Path("ci.log")
if log.exists():
    text = log.read_text(errors="replace")[-8000:]
    msg = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::warning title=ci-log::{msg}")
