"""Target tracking + Unicode SendInput (v01 live stream) + optional smart paste."""
from __future__ import annotations

import ctypes
import queue
import threading
import time
from ctypes import POINTER, CFUNCTYPE, wintypes

import pyperclip

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
HC_ACTION = 0
GA_ROOT = 2
INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
VK_CONTROL = 0x11
VK_V = 0x56
VK_RETURN = 0x0D
ASFW_ANY = 0xFFFFFFFF

LowLevelMouseProc = CFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]


# Console-ish class names → prefer Ctrl+V smart paste
_CONSOLE_CLASSES = {
    "consolewindowclass",
    "cascadia_hosting_window_class",
    "mintty",
    "putty",
    "vsterminal",
    "chrome_widgetwin_1",  # some terminals embed
}


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


class Injector:
    def __init__(
        self,
        smart_paste_console: bool = False,
        char_delay_ms: int = 0,
        prefer_grok: bool = False,
        force_smart_paste: bool = False,
        live_stream: bool = True,
    ) -> None:
        # live_stream=True → always SendInput Unicode (v01 C# LivePaste style).
        # Never Ctrl+V — user asked for AI-like char stream, not paste dumps.
        self.live_stream = bool(live_stream)
        self.smart_paste_console = bool(smart_paste_console) and not self.live_stream
        self.char_delay_ms = char_delay_ms
        self.prefer_grok = prefer_grok
        self.force_smart_paste = bool(force_smart_paste) and not self.live_stream
        self._lock = threading.Lock()
        self.root: int | None = None
        self.focus_hwnd: int | None = None
        self._exclude: int | None = None
        self._hook = None
        self._proc = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._pid = kernel32.GetCurrentProcessId()
        # During PTT: freeze target — mouse clicks must not retarget mid-stream
        self._freeze_target = False
        self._last_external_root: int | None = None
        self._last_external_focus: int | None = None
        # Async type queue (like C# TextInjector worker) — decode thread never blocks
        self._type_q: queue.Queue[str | None] = queue.Queue()
        self._type_worker: threading.Thread | None = None
        self._type_worker_started = False

    def set_exclude(self, hwnd: int | None) -> None:
        with self._lock:
            self._exclude = int(hwnd) if hwnd else None

    def lock_target(self, root: int, focus: int | None = None) -> None:
        if not root or not user32.IsWindow(root):
            return
        if not self._is_external(root):
            return
        with self._lock:
            self.root = int(root)
            self.focus_hwnd = int(focus or root)
            self._last_external_root = self.root
            self._last_external_focus = self.focus_hwnd

    def note_external_foreground(self) -> None:
        """Surekli: dis pencere odaktaysa hatirla (F11 once Cursor vs)."""
        if self._freeze_target:
            return
        fg = user32.GetForegroundWindow()
        if not fg or not self._is_external(fg):
            return
        root = user32.GetAncestor(fg, GA_ROOT) or fg
        if not self._is_external(root):
            return
        with self._lock:
            self._last_external_root = int(root)
            self._last_external_focus = int(fg)
            if not self._freeze_target:
                self.root = int(root)
                self.focus_hwnd = int(fg)

    def _window_title(self, hwnd: int) -> str:
        try:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 2)
            user32.GetWindowTextW(hwnd, buf, n + 2)
            return (buf.value or "")[:80]
        except Exception:
            return ""

    def _resolve_external_target(self) -> tuple[int | None, int | None]:
        """En iyi dis pencere: FG > son dis > mouse alti > cursor pos."""
        candidates: list[tuple[int, int]] = []

        fg = user32.GetForegroundWindow()
        if fg and self._is_external(fg):
            root = user32.GetAncestor(fg, GA_ROOT) or fg
            if self._is_external(root):
                candidates.append((int(root), int(fg)))

        with self._lock:
            le_r = self._last_external_root
            le_f = self._last_external_focus
            mr = self.root
            mf = self.focus_hwnd
        for r, f in ((le_r, le_f), (mr, mf)):
            if r and user32.IsWindow(r) and self._is_external(r):
                candidates.append((int(r), int(f or r)))

        # Mouse altindaki pencere
        try:
            pt = POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                hit = user32.WindowFromPoint(pt)
                if hit and self._is_external(hit):
                    root = user32.GetAncestor(hit, GA_ROOT) or hit
                    if self._is_external(root):
                        candidates.append((int(root), int(hit)))
        except Exception:
            pass

        for r, f in candidates:
            if r and user32.IsWindow(r) and self._is_external(r):
                return r, f if f and user32.IsWindow(f) else r
        return None, None

    def freeze_session_target(self) -> None:
        """
        F11 basildigi AN: Cursor/aktif dis pencereyi kilitle.
        STT penceresi seciliyse -> onceki dis hedefe don.
        Asla STT app'e yazma.
        """
        target_root, target_focus = self._resolve_external_target()

        if not target_root or not self._is_external(target_root):
            # freeze yine ac — type aninda FG tekrar denenecek
            with self._lock:
                self._freeze_target = True
            try:
                from app.life_log import life

                life("TARGET none at freeze (FG may be STT)")
            except Exception:
                pass
            return

        with self._lock:
            self.root = int(target_root)
            self.focus_hwnd = int(target_focus or target_root)
            self._last_external_root = self.root
            self._last_external_focus = self.focus_hwnd
            self._freeze_target = True

        try:
            from app.life_log import life

            life(
                "TARGET freeze root=%s title=%r",
                target_root,
                self._window_title(int(target_root)),
            )
        except Exception:
            pass

        # Odak STT'ye kactiysa HEDEFE geri ver (Cursor'a don)
        self._ensure_fg(int(target_root))

    def unfreeze_session_target(self) -> None:
        with self._lock:
            self._freeze_target = False

    def lock_foreground(self) -> None:
        self.note_external_foreground()

    def start_tracker(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="MouseTarget", daemon=True)
        self._thread.start()
        # FG izleyici — Cursor seciliyken hatirla
        threading.Thread(target=self._fg_watch, name="FgWatch", daemon=True).start()

    def stop_tracker(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _fg_watch(self) -> None:
        while self._running:
            try:
                self.note_external_foreground()
            except Exception:
                pass
            time.sleep(0.08)

    def _is_ours(self, hwnd: int) -> bool:
        if not hwnd:
            return False
        # ayni process = bizim (CTK + child)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == self._pid:
            return True
        with self._lock:
            ex = self._exclude
        if not ex:
            return False
        if hwnd == ex:
            return True
        return user32.IsChild(ex, hwnd) != 0

    def _is_external(self, hwnd: int) -> bool:
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        if self._is_ours(hwnd):
            return False
        return True

    def _remember(self, pt: POINT) -> None:
        with self._lock:
            if self._freeze_target:
                return  # mid-PTT: do not jump to other windows
        hit = user32.WindowFromPoint(pt)
        if not hit or not self._is_external(hit):
            return
        root = user32.GetAncestor(hit, GA_ROOT) or hit
        if not self._is_external(root):
            return
        with self._lock:
            self.root = root
            self.focus_hwnd = hit
            self._last_external_root = root
            self._last_external_focus = hit

    def _mouse_proc(self, code, wparam, lparam):
        if code == HC_ACTION and wparam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
            info = ctypes.cast(lparam, POINTER(MSLLHOOKSTRUCT)).contents
            self._remember(info.pt)
        return user32.CallNextHookEx(self._hook, code, wparam, lparam)

    def _loop(self) -> None:
        self._proc = LowLevelMouseProc(self._mouse_proc)
        # user32 module handle is more reliable for LL hooks
        hmod = kernel32.LoadLibraryW("user32.dll")
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, hmod, 0)
        msg = wintypes.MSG()
        while self._running:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _ensure_fg(self, root: int) -> None:
        user32.AllowSetForegroundWindow(ASFW_ANY)
        fg = user32.GetForegroundWindow()
        if fg == root or user32.GetAncestor(fg, GA_ROOT) == root:
            return
        cur = kernel32.GetCurrentThreadId()
        tid = user32.GetWindowThreadProcessId(root, None)
        attached = False
        if tid and tid != cur:
            attached = bool(user32.AttachThreadInput(cur, tid, True))
        user32.BringWindowToTop(root)
        user32.SetForegroundWindow(root)
        if attached:
            user32.AttachThreadInput(cur, tid, False)

    def _send_inputs(self, inputs: list[INPUT]) -> None:
        if not inputs:
            return
        arr = (INPUT * len(inputs))(*inputs)
        user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))

    def _unicode_char(self, ch: str) -> list[INPUT]:
        code = ord(ch)
        down = INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, None)))
        up = INPUT(
            type=INPUT_KEYBOARD,
            u=INPUT_UNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)),
        )
        return [down, up]

    def _key_vk(self, vk: int, down: bool) -> INPUT:
        flags = 0 if down else KEYEVENTF_KEYUP
        return INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=KEYBDINPUT(vk, 0, flags, 0, None)))

    def ensure_type_worker(self) -> None:
        """Start background typer (call once at app start)."""
        if self._type_worker_started:
            return
        self._type_worker_started = True
        self._type_worker = threading.Thread(
            target=self._type_worker_loop, name="TextInjector", daemon=True
        )
        self._type_worker.start()

    def enqueue_type(self, text: str) -> None:
        """Queue text for live Unicode typing (non-blocking)."""
        if not text:
            return
        self.ensure_type_worker()
        try:
            self._type_q.put_nowait(text)
        except Exception:
            self._type_unicode_sync(text)

    def wait_type_idle(self, timeout: float = 3.0) -> None:
        """Final sonrasi kuyruk bitsin — yarim yazma kalmasin."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self._type_q.empty():
                time.sleep(0.05)
                if self._type_q.empty():
                    return
            time.sleep(0.03)

    def _type_worker_loop(self) -> None:
        while True:
            try:
                item = self._type_q.get()
            except Exception:
                break
            if item is None:
                break
            try:
                self._type_unicode_sync(item)
            except Exception:
                pass

    def type_unicode(self, text: str) -> None:
        """Public API: live_stream uses async queue; else sync (optional paste)."""
        if not text:
            return
        if self.live_stream:
            self.enqueue_type(text)
            return
        self._type_unicode_sync(text)

    def _type_unicode_sync(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            root = self.root
            focus = self.focus_hwnd
            frozen = self._freeze_target
        if not root or not user32.IsWindow(root):
            if not frozen:
                self.lock_foreground()
            with self._lock:
                root = self.root
                focus = self.focus_hwnd
        # Live: kilitli DIS hedefe yaz. Bizim pencereye ASLA yazma.
        if self.live_stream:
            if not root or not user32.IsWindow(root) or not self._is_external(root):
                with self._lock:
                    root = self._last_external_root
                    focus = self._last_external_focus
            if not root or not user32.IsWindow(root) or not self._is_external(root):
                # son sans: anlik dis FG / mouse
                r2, f2 = self._resolve_external_target()
                root, focus = r2, f2
            if not root or not user32.IsWindow(root) or not self._is_external(root):
                return  # guvenli: hedef yoksa yazma (STT'ye basma)
            # Odak bizdeyse veya baska yerdeyse -> hedefe zorla don
            fg = user32.GetForegroundWindow()
            if not fg or self._is_ours(fg) or (user32.GetAncestor(fg, GA_ROOT) or fg) != root:
                self._ensure_fg(root)
            self._send_unicode_chars(text)
            return

        use_smart = bool(self.force_smart_paste and text)
        target = focus or root
        if self.smart_paste_console and target and not use_smart:
            cls = _class_name(target).lower()
            root_cls = _class_name(root).lower() if root else ""
            if cls in _CONSOLE_CLASSES or root_cls in _CONSOLE_CLASSES:
                use_smart = True
            if "console" in cls or "cascadia" in cls or "terminal" in cls:
                use_smart = True

        if use_smart and len(text) >= 1:
            self._smart_paste(text)
            return

        self._send_unicode_chars(text)

    def _send_unicode_chars(self, text: str) -> None:
        """Spectre / C# LivePaste style: KEYEVENTF_UNICODE per character."""
        batch: list[INPUT] = []
        for ch in text:
            if ch == "\r":
                continue
            if ch == "\n":
                batch.append(self._key_vk(VK_RETURN, True))
                batch.append(self._key_vk(VK_RETURN, False))
            else:
                batch.extend(self._unicode_char(ch))
            # smaller batches = more stream-like feel
            if len(batch) >= 16:
                self._send_inputs(batch)
                batch.clear()
                if self.char_delay_ms:
                    time.sleep(self.char_delay_ms / 1000.0)
        if batch:
            self._send_inputs(batch)
            if self.char_delay_ms:
                time.sleep(self.char_delay_ms / 1000.0)

    def _smart_paste(self, text: str) -> None:
        """Clipboard + Ctrl+V (Superlux ExecuteSmartPaste style), restore clipboard."""
        try:
            old = pyperclip.paste()
        except Exception:
            old = None
        try:
            pyperclip.copy(text)
            time.sleep(0.02)
            self._send_inputs(
                [
                    self._key_vk(VK_CONTROL, True),
                    self._key_vk(VK_V, True),
                    self._key_vk(VK_V, False),
                    self._key_vk(VK_CONTROL, False),
                ]
            )
            time.sleep(0.05)
        finally:
            if old is not None:
                try:
                    pyperclip.copy(old)
                except Exception:
                    pass

    def press_enter(self) -> None:
        self._send_inputs([self._key_vk(VK_RETURN, True), self._key_vk(VK_RETURN, False)])
