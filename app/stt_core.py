"""
FARTING-WHISPER core (no UI). Used by tray/CTK app.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from app.paths import app_root, ensure_logs_dir, resource_root

ROOT = app_root()
RES = resource_root()
LOG_DIR = ensure_logs_dir()


def _config_path() -> Path:
    for base in (ROOT, RES):
        for name in ("config-grok-build.json", "config.json"):
            p = base / name
            if p.is_file():
                return p
    return ROOT / "config-grok-build.json"


CFG_PATH = _config_path()


def setup_log(gui: bool = True) -> logging.Logger:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    log_dir = ensure_logs_dir()
    fh = RotatingFileHandler(
        log_dir / "grok-voice.log", maxBytes=1_500_000, backupCount=2, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    for name in ("grok_voice", "ipu_kroko.asr", "stt_app"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        lg.handlers.clear()
        lg.addHandler(fh)
        if not gui:
            import sys

            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(fmt)
            lg.addHandler(sh)
        lg.propagate = False
    return logging.getLogger("stt_app")


def load_config() -> dict:
    path = _config_path()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_model_dir(cfg: dict) -> Path:
    rel = cfg.get("asr", {}).get("modelDir", "model/kroko-tr-128l")
    candidates = [
        ROOT / rel,
        RES / rel,
        ROOT / "model" / "kroko-tr-128l",
        RES / "model" / "kroko-tr-128l",
        ROOT.parent / "model" / "kroko-tr-128l",
    ]
    for c in candidates:
        if (c / "encoder.int8.onnx").is_file():
            return c
    raise FileNotFoundError("Kroko model not found")


class SttCore:
    """Hold-to-talk STT → inject wherever cursor/focus is."""

    def __init__(self, on_status: Callable[[str], None] | None = None) -> None:
        from app.dll_bootstrap import prefer_sherpa_ort

        prefer_sherpa_ort()

        from app.asr_engine import KrokoEngine
        from app.hotkey import GpdStartHotkey
        from app.inject import Injector

        self.log = setup_log(gui=True)
        self.cfg = load_config()
        self.on_status = on_status or (lambda s: None)
        self._partial = ""
        self._listening = False
        self._lock = threading.Lock()
        self._running = False

        asr = self.cfg.get("asr") or {}
        stream = self.cfg.get("streaming") or {}
        inj = self.cfg.get("inject") or {}
        hk = self.cfg.get("hotkey") or {}

        model_dir = resolve_model_dir(self.cfg)
        self.engine = KrokoEngine(
            model_dir=model_dir,
            sample_rate=int(asr.get("sampleRate", 16000)),
            threads=int(asr.get("threads", 3)),
            decode_interval_ms=int(stream.get("decodeIntervalMs", 12)),
            blocksize=int(stream.get("blocksize", 320)),
            preferred_mic=stream.get("preferredMic") or "",
            flush_timeout_s=float(stream.get("flushTimeoutS", 20)),
        )
        self.injector = Injector(
            live_stream=True,
            smart_paste_console=False,
            force_smart_paste=False,
            char_delay_ms=0,
            prefer_grok=False,
        )
        self.injector.ensure_type_worker()

        plain = hk.get("hardwareAliasVks") or [122]
        self.hotkey = GpdStartHotkey(
            keyboard_alias_vks=plain,
            enable_chord=False,
            # swallow True: F11 diger app'e gitmesin (fullscreen vs)
            # probe artik hook OR async — swallow yuzunden kacmaz
            swallow_alias=True,
            enable_xinput=False,
            startup_grace_s=1.0,
            hold_confirm_ms=30,
        )
        self.engine.set_text_callback(self._on_delta)
        self.mic_label = f"[{self.engine.device_index}] {self.engine.device_name}"
        self.hotkey_label = self.hotkey.describe()
        self.log.info("SttCore ready mic=%s hk=%s", self.mic_label, self.hotkey_label)

    def _status(self, s: str) -> None:
        try:
            self.on_status(s)
        except Exception:
            pass

    def _on_delta(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._partial = (self._partial + text)[-200:]
        try:
            self.injector.type_unicode(text)
        except Exception as e:
            self.log.warning("inject: %s", e)

    def _on_down(self, source: str, detail: str) -> None:
        with self._lock:
            if self._listening:
                return
            self._listening = True
            self._partial = ""
        self.log.info("LISTEN ON %s (user hold)", detail)
        try:
            # ONCE hedefi kilitle (UI status'tan once — odak Cursor'da kalsin)
            self.injector.freeze_session_target()
            root = getattr(self.injector, "root", None)
            title = ""
            try:
                if root:
                    title = self.injector._window_title(int(root))  # noqa: SLF001
            except Exception:
                pass
            self.log.info("TARGET root=%s title=%r", root, title)
            if not root:
                self.log.warning(
                    "No target — click Notepad/Cursor first, then hold F11"
                )
            self.engine.start_session()
            self._status(f"Listening… ({detail})")
        except Exception as e:
            self.log.error("start: %s", e)
            self.injector.unfreeze_session_target()
            with self._lock:
                self._listening = False
            self._status(f"Error: {e}")

    def _on_up(self, source: str, detail: str) -> None:
        with self._lock:
            if not self._listening:
                return
        # F11 release: no new audio. Only flush audio queued while held.
        self.log.info("LISTEN OFF %s — stop capture, flush held audio only", detail)
        self._status("Recording stopped — flushing held audio…")
        try:
            final = self.engine.stop_session() or ""
            try:
                self.injector.wait_type_idle(6.0)
            except Exception:
                pass
            peak = getattr(self.engine, "_peak", 0.0)
            self.log.info(
                "HOLD OFF done peak=%.3f len=%s FULL=%r",
                peak,
                len(final),
                final,
            )
            self._status(f"Ready  peak={peak:.2f}  {len(final)} chars")
        except Exception as e:
            self.log.error("stop: %s", e)
            self._status(f"Error: {e}")
        finally:
            self.injector.unfreeze_session_target()
            with self._lock:
                self._listening = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.injector.start_tracker()
        self.hotkey.start()
        self._status("Ready — hold F11 (does not listen on startup)")
        self.log.info("IDLE ready — no listen until F11 hold")
        # poll hotkey events on background thread
        threading.Thread(target=self._poll_loop, name="SttPoll", daemon=True).start()

    def _poll_loop(self) -> None:
        while self._running:
            try:
                for ev in self.hotkey.poll_events():
                    self.log.info("PTT event %s src=%s %s", ev.kind, ev.source, ev.detail)
                    if ev.kind == "down":
                        self._on_down(ev.source, ev.detail)
                    elif ev.kind == "up":
                        self._on_up(ev.source, ev.detail)
            except Exception as e:
                self.log.warning("poll: %s", e)
            time.sleep(0.012)

    def stop(self) -> None:
        self._running = False
        try:
            if self._listening:
                self.engine.stop_session()
        except Exception:
            pass
        try:
            self.hotkey.stop()
        except Exception:
            pass
        try:
            self.injector.stop_tracker()
        except Exception:
            pass
        try:
            self.engine.shutdown()
        except Exception:
            pass
        self._status("Stopped")

    @property
    def listening(self) -> bool:
        return self._listening

    @property
    def partial(self) -> str:
        with self._lock:
            return self._partial
