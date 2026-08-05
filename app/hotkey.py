"""
PTT hotkey — F11 basılı tut = dinle.

Çift yol:
  1) `keyboard` lib (global hook) — ana yol
  2) GetAsyncKeyState poll — yedek
  3) UI buton inject

Açılışta auto-listen YOK: önce tuş serbest (armed) olmalı.
"""
from __future__ import annotations

import ctypes
import queue
import threading
import time
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_TAB = 0x09
VK_F9 = 0x78
VK_F11 = 0x7A
VK_SPACE = 0x20
VK_PAUSE = 0x13
VK_SCROLL = 0x91
VK_F13 = 0x7C

try:
    from app.life_log import life, life_exc
except Exception:
    def life(msg, *a):  # type: ignore
        print(msg % a if a else msg)

    def life_exc(p="EXC"):  # type: ignore
        pass


def _down(vk: int) -> bool:
    try:
        return bool(user32.GetAsyncKeyState(int(vk)) & 0x8000)
    except Exception:
        return False


def vk_label(vk: int) -> str:
    special = {
        VK_TAB: "TAB",
        VK_F9: "F9",
        VK_F11: "F11",
        VK_SPACE: "Space",
        VK_PAUSE: "Pause",
        VK_SCROLL: "ScrollLock",
        VK_F13: "F13",
    }
    if vk in special:
        return special[vk]
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    return f"VK0x{vk:02X}"


def _vk_to_keyboard_name(vk: int) -> str:
    """keyboard lib key name."""
    if vk == VK_F11:
        return "f11"
    if vk == VK_F9:
        return "f9"
    if 0x70 <= vk <= 0x87:
        return f"f{vk - 0x6F}"
    if vk == VK_SPACE:
        return "space"
    if vk == VK_PAUSE:
        return "pause"
    if vk == VK_SCROLL:
        return "scroll lock"
    if 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    return ""


@dataclass
class PttEvent:
    kind: str
    source: str
    detail: str = ""
    t: float = 0.0


def _parse_vk_list(value) -> list[int]:
    if value is None:
        return []
    raw = list(value) if isinstance(value, (list, tuple, set)) else [value]
    out: list[int] = []
    for v in raw:
        if v is None or v is False or v == "":
            continue
        v = int(v, 0) if isinstance(v, str) else int(v)
        if v > 0 and v not in out:
            out.append(v)
    return out


class GpdStartHotkey:
    """Hold-to-talk: plain single keys (default F11)."""

    def __init__(
        self,
        poll_ms: int = 12,
        keyboard_alias_vk: int | None = None,
        keyboard_alias_vks: list[int] | None = None,
        swallow_alias: bool = True,
        xinput_mask: int = 0,
        startup_grace_s: float = 1.0,
        hold_confirm_ms: int = 30,
        enable_xinput: bool = False,
        require_alt: bool = False,
        combo_vk: int | None = None,
        require_ctrl: bool = False,
        require_shift: bool = False,
        enable_chord: bool = False,
        **kwargs,
    ) -> None:
        self.poll_ms = max(8, int(poll_ms))
        vks = _parse_vk_list(keyboard_alias_vks) if keyboard_alias_vks is not None else []
        if not vks and keyboard_alias_vk:
            vks = _parse_vk_list(keyboard_alias_vk)
        if not vks:
            vks = [VK_F11]
        self.keyboard_alias_vks = vks
        self.keyboard_alias_vk = vks[0]
        self.combo_vk = int(combo_vk) if combo_vk is not None else VK_TAB
        self.enable_chord = bool(enable_chord)
        self.require_ctrl = bool(require_ctrl)
        self.require_shift = bool(require_shift)
        self.require_alt = False
        self.swallow_alias = bool(swallow_alias)
        self.xinput_mask = 0
        self.startup_grace_s = max(0.6, float(startup_grace_s))
        self.hold_confirm_ms = max(15, int(hold_confirm_ms))
        self._running = False
        self._thread: threading.Thread | None = None
        self._latched = False
        self._armed = False
        self._t0 = 0.0
        self._seen_true_since: float | None = None
        self._last_source = "unknown"
        self.events: queue.Queue[PttEvent] = queue.Queue()
        # keyboard-lib + async shared state
        self._kb_down_vks: set[int] = set()
        self._kb_lock = threading.Lock()
        self._hooks_registered = False
        self._use_keyboard_lib = False

    def describe(self) -> str:
        parts = [vk_label(vk) for vk in self.keyboard_alias_vks]
        return " | ".join(parts) + " (hold)"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._t0 = time.time()
        self._latched = False
        self._armed = False
        self._seen_true_since = None
        with self._kb_lock:
            self._kb_down_vks.clear()
        life("hotkey.start %s", self.describe())
        self._install_keyboard_hooks()
        self._thread = threading.Thread(target=self._loop, name="PTTLoop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._uninstall_keyboard_hooks()
        if self._thread:
            self._thread.join(timeout=1.5)
            self._thread = None

    def poll_events(self) -> list[PttEvent]:
        out: list[PttEvent] = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        return out

    def inject_ui_down(self) -> None:
        self._armed = True
        self._latched = True
        self._last_source = "ui"
        self._emit("down", "ui", "button")

    def inject_ui_up(self) -> None:
        self._latched = False
        with self._kb_lock:
            self._kb_down_vks.clear()
        self._emit("up", "ui", "button")

    def _emit(self, kind: str, source: str, detail: str = "") -> None:
        try:
            self.events.put_nowait(
                PttEvent(kind=kind, source=source, detail=detail, t=time.time())
            )
        except Exception:
            pass
        life("PTT %s %s %s", kind, source, detail)

    def _install_keyboard_hooks(self) -> None:
        try:
            import keyboard as kb

            for vk in self.keyboard_alias_vks:
                name = _vk_to_keyboard_name(vk)
                if not name:
                    continue

                def _on_press(e, _vk=vk, _name=name):
                    with self._kb_lock:
                        first = _vk not in self._kb_down_vks
                        self._kb_down_vks.add(_vk)
                    if first:
                        life("KB-LIB DOWN %s", _name)

                def _on_release(e, _vk=vk, _name=name):
                    with self._kb_lock:
                        had = _vk in self._kb_down_vks
                        self._kb_down_vks.discard(_vk)
                    if had:
                        life("KB-LIB UP %s", _name)

                kb.on_press_key(name, _on_press, suppress=bool(self.swallow_alias))
                kb.on_release_key(name, _on_release, suppress=bool(self.swallow_alias))

            self._hooks_registered = True
            self._use_keyboard_lib = True
            life("keyboard-lib hooks OK suppress=%s keys=%s", self.swallow_alias, self.describe())
        except Exception as e:
            self._hooks_registered = False
            self._use_keyboard_lib = False
            life("keyboard-lib FAIL (%s) — async-only fallback", e)

    def _uninstall_keyboard_hooks(self) -> None:
        if not self._hooks_registered:
            return
        try:
            import keyboard as kb

            kb.unhook_all()
        except Exception:
            pass
        self._hooks_registered = False

    def _pressed_now(self) -> tuple[bool, str, str]:
        """Hook set VEYA GetAsyncKeyState — ikisinden biri yeter."""
        with self._kb_lock:
            hook_set = set(self._kb_down_vks)

        for vk in self.keyboard_alias_vks:
            async_down = _down(vk)
            hook_down = vk in hook_set
            # keyboard.is_pressed yedek
            lib_down = False
            if self._use_keyboard_lib:
                try:
                    import keyboard as kb

                    name = _vk_to_keyboard_name(vk)
                    if name:
                        lib_down = bool(kb.is_pressed(name))
                except Exception:
                    lib_down = False
            if async_down or hook_down or lib_down:
                if hook_down:
                    src = "hook"
                elif lib_down:
                    src = "kblib"
                else:
                    src = "async"
                return True, src, vk_label(vk)
        return False, "none", ""

    def _loop(self) -> None:
        release_need = 3
        release_streak = 0
        clear_need = 5
        clear_streak = 0
        beat = 0
        while self._running:
            try:
                # 1) Grace period — acilis auto-listen yok
                if time.time() - self._t0 < self.startup_grace_s:
                    with self._kb_lock:
                        self._kb_down_vks.clear()
                    self._seen_true_since = None
                    time.sleep(self.poll_ms / 1000.0)
                    continue

                pressed, source, detail = self._pressed_now()
                t = time.time()

                # 2) Arm: once hepsi serbest
                if not self._armed:
                    any_async = any(_down(vk) for vk in self.keyboard_alias_vks)
                    with self._kb_lock:
                        any_hook = bool(self._kb_down_vks)
                    if not any_async and not any_hook:
                        clear_streak += 1
                        if clear_streak >= clear_need:
                            self._armed = True
                            self._seen_true_since = None
                            self._latched = False
                            life("PTT ARMED idle — hold F11")
                    else:
                        clear_streak = 0
                        # sticky temizle (async yoksa hook state bozulmus olabilir)
                        if not any_async:
                            with self._kb_lock:
                                self._kb_down_vks.clear()
                    time.sleep(self.poll_ms / 1000.0)
                    continue

                # heartbeat her ~5sn
                beat += 1
                if beat % 400 == 0:
                    life("PTT heartbeat armed latched=%s", self._latched)

                if pressed:
                    release_streak = 0
                    if self._seen_true_since is None:
                        self._seen_true_since = t
                    if (not self._latched) and (t - self._seen_true_since) * 1000 >= self.hold_confirm_ms:
                        self._latched = True
                        self._last_source = source
                        self._emit("down", source, detail)
                else:
                    self._seen_true_since = None
                    if self._latched:
                        release_streak += 1
                        if release_streak >= release_need:
                            self._latched = False
                            release_streak = 0
                            with self._kb_lock:
                                self._kb_down_vks.clear()
                            self._emit("up", self._last_source, "release")
                            life("PTT RELEASE confirmed")
                    else:
                        release_streak = 0
            except Exception:
                life_exc("ptt loop")
            time.sleep(self.poll_ms / 1000.0)


class HoldHotkey(GpdStartHotkey):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
