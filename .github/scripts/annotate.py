"""Gibt die wichtigen Zeilen des Testlogs als Annotation aus (ohne Log-Zugriff lesbar)."""

import pathlib

log = pathlib.Path("ci.log")
if log.exists():
    keep = []
    for line in log.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if (
            stripped.startswith(("E ", "E\t", "FAILED", "ERROR", "tests/", "=", "_"))
            or " passed" in stripped
            or " failed" in stripped
            or "rror" in stripped[:40]
        ):
            keep.append(line[:300])
    text = "\n".join(keep)[-3500:]
    msg = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::warning title=ci-log::{msg}")
