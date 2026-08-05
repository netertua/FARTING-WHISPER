"""File-only life-cycle log. No heartbeat spam. Does not print to console."""
from __future__ import annotations

import atexit
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

from app.paths import ensure_logs_dir

_LOG = ensure_logs_dir()
_PATH = _LOG / "life.log"
_lock = threading.Lock()


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def life(msg: str, *args) -> None:
    """Write to logs/life.log only — never stdout (avoids noise / fake ASR)."""
    try:
        line = msg if not args else (msg % args)
    except Exception:
        line = f"{msg} {args}"
    text = f"{_ts()} [{threading.current_thread().name}] {line}\n"
    with _lock:
        try:
            with _PATH.open("a", encoding="utf-8") as f:
                f.write(text)
                f.flush()
        except Exception:
            pass


def life_exc(prefix: str = "EXC") -> None:
    life("%s\n%s", prefix, traceback.format_exc())


def install_hooks() -> None:
    life("=== life_log install pid=%s ===", __import__("os").getpid())

    def _atexit():
        life("atexit fired")

    atexit.register(_atexit)

    def _excepthook(etype, value, tb):
        life("sys.excepthook %s: %s", etype, value)
        try:
            with _PATH.open("a", encoding="utf-8") as f:
                traceback.print_exception(etype, value, tb, file=f)
                f.flush()
        except Exception:
            pass
        sys.__excepthook__(etype, value, tb)

    sys.excepthook = _excepthook

    try:
        import faulthandler

        fh = open(_LOG / "faulthandler.txt", "a", encoding="utf-8")
        faulthandler.enable(file=fh, all_threads=True)
        life("faulthandler enabled")
    except Exception as e:
        life("faulthandler fail: %s", e)

    # No heartbeat thread — was spam ("heartbeat n=…") and confused users / logs
