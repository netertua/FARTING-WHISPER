"""Microphone / sound input discovery + auto-select."""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from typing import Any

log = logging.getLogger("ipu_kroko.mic")

# Prefer real mics; deprioritize virtual/loopback/stereo mix
_BOOST = (
    "microphone",
    "mikrofon",
    "mic",
    "array",
    "headset",
    "kulaklik",
    "wo mic",
    "realtek",
    "amd audio",
    "smart amp",
    "digital mic",
    "internal",
    "built-in",
    "dahili",
)
_PENALTY = (
    "stereo mix",
    "what u hear",
    "wave out",
    "loopback",
    "cable",
    "vb-audio",
    "voicemeeter",
    "virtual",
    "mapper",
    "primary sound capture",  # often a wrapper; still usable but lower
    "output",
    "speaker",
    "hoparlor",
)


@dataclass
class MicDevice:
    index: int
    name: str
    hostapi: str
    channels: int
    default_samplerate: float
    is_default: bool
    score: float

    def label(self) -> str:
        mark = " [DEFAULT]" if self.is_default else ""
        return f"[{self.index}] {self.name}{mark} ({self.channels}ch)"


def _score_name(name: str, is_default: bool) -> float:
    n = name.lower()
    s = 0.0
    if is_default:
        s += 5.0
    for w in _BOOST:
        if w in n:
            s += 3.0
    for w in _PENALTY:
        if w in n:
            s -= 8.0
    # usb mics often good
    if "usb" in n and "mic" in n:
        s += 2.0
    return s


def list_input_devices() -> list[MicDevice]:
    import sounddevice as sd

    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    default_in = None
    try:
        default_in = sd.default.device[0]
    except Exception:
        pass
    if isinstance(default_in, (list, tuple)):
        default_in = default_in[0]

    out: list[MicDevice] = []
    for i, d in enumerate(devices):
        ch = int(d.get("max_input_channels") or 0)
        if ch <= 0:
            continue
        name = str(d.get("name") or f"device-{i}")
        # fix mojibake sometimes
        try:
            name = name.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore") or name
        except Exception:
            pass
        hai = int(d.get("hostapi") or 0)
        ha_name = ""
        try:
            ha_name = str(hostapis[hai].get("name") or "")
        except Exception:
            ha_name = str(hai)
        is_def = default_in is not None and int(default_in) == i
        score = _score_name(name, is_def)
        # WASAPI/DirectSound prefer a bit over MME for latency
        if "wasapi" in ha_name.lower():
            score += 1.5
        elif "directsound" in ha_name.lower():
            score += 0.5
        out.append(
            MicDevice(
                index=i,
                name=name,
                hostapi=ha_name,
                channels=ch,
                default_samplerate=float(d.get("default_samplerate") or 0),
                is_default=is_def,
                score=score,
            )
        )
    out.sort(key=lambda m: (-m.score, m.index))
    return out


def auto_select_mic(preferred: str = "", prefer_index: int | None = None) -> MicDevice | None:
    """
    preferred: substring match on name (case-insensitive)
    prefer_index: force device index if valid input
    """
    mics = list_input_devices()
    if not mics:
        log.warning("No input devices found")
        return None

    if prefer_index is not None:
        for m in mics:
            if m.index == int(prefer_index):
                log.info("Mic forced index=%s %s", m.index, m.name)
                return m

    pref = (preferred or "").strip().lower()
    if pref:
        for m in mics:
            if pref in m.name.lower():
                log.info("Mic match preferred=%r -> %s", preferred, m.label())
                return m
        log.warning("preferredMic %r not found — auto", preferred)

    # highest score
    best = mics[0]
    log.info(
        "Mic AUTO -> %s score=%.1f hostapi=%s",
        best.label(),
        best.score,
        best.hostapi,
    )
    return best


def devices_as_dicts() -> list[dict[str, Any]]:
    return [asdict(m) | {"label": m.label()} for m in list_input_devices()]


def probe_levels(device_index: int, seconds: float = 0.35, samplerate: int = 16000) -> float:
    """Return rough RMS 0..1 for quick liveness check."""
    import numpy as np
    import sounddevice as sd

    try:
        rec = sd.rec(
            int(seconds * samplerate),
            samplerate=samplerate,
            channels=1,
            dtype="float32",
            device=device_index,
        )
        sd.wait()
        x = np.squeeze(rec)
        if x.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(np.square(x))))
        return min(1.0, rms * 8.0)
    except Exception as e:
        log.warning("probe mic %s failed: %s", device_index, e)
        return -1.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for m in list_input_devices():
        print(f"{m.score:5.1f}  {m.label()}  ({m.hostapi})")
    a = auto_select_mic()
    print("AUTO:", a.label() if a else None)
