"""Install / resource roots for dev and PyInstaller frozen builds."""
from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Writable install root (logs, optional local config overrides)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_root() -> Path:
    """Bundled read-only assets (model, default config, package data)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def ensure_logs_dir() -> Path:
    d = app_root() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d
