"""
FARTING-WHISPER — local hold-to-talk STT (CustomTkinter + tray).
No console window (start with pythonw).
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from app.paths import app_root

ROOT = app_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.life_log import install_hooks

install_hooks()

import customtkinter as ctk
from PIL import Image, ImageDraw

APP_NAME = "FARTING-WHISPER"
APP_TAGLINE = "Local Kroko ASR — not Whisper cosplay"

ORANGE = "#FF6B00"
ORANGE_HOVER = "#FF8533"
ORANGE_DIM = "#CC5500"
BG = "#1A1A1A"
CARD = "#242424"
TEXT = "#F0F0F0"
MUTED = "#888888"
GREEN = "#2ECC71"
RED = "#E74C3C"

ABOUT_TEXT = (
    "Why Kroko ASR?\n"
    "Kroko is a compact streaming speech model (TR + EN) that runs fully on-device "
    "through Sherpa-ONNX. It is built for live hold-to-talk: ~150 MB model, CPU-friendly, "
    "partial text while you speak. No cloud, no API key, no upload.\n\n"
    "What is Kroko?\n"
    "A lightweight streaming encoder–decoder ASR pack (Kroko TR-128L) meant for realtime "
    "dictation — not hour-long file transcription.\n\n"
    "Why Whisper is heavy (and awkward locally)\n"
    "Whisper is great for offline files. Locally it is a different story: large weights, "
    "slow cold start, batch-first design, and real-time PC-wide PTT wants a fat GPU and a "
    "lot of patience. On a laptop it often feels like waiting for a research demo, not "
    "typing with your voice.\n\n"
    "Why this app works offline\n"
    "• Streaming Kroko via Sherpa-ONNX on CPU (no CUDA required)\n"
    "• Audio never leaves the machine\n"
    "• F11 hold → inject into the focused / last-clicked window\n"
    "• Built for live use; Whisper is built for files\n\n"
    "FARTING-WHISPER is the local lane. Real Whisper can keep the cloud and the waiting room."
)


def _make_icon(size: int = 64, listening: bool = False) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, size - 3, size - 3], fill=(26, 26, 26, 255), outline=(255, 107, 0, 255), width=3)
    cx, cy = size // 2, size // 2 - 2
    col = (255, 107, 0, 255) if not listening else (46, 204, 113, 255)
    d.rounded_rectangle([cx - 8, cy - 14, cx + 8, cy + 6], radius=8, fill=col)
    d.arc([cx - 14, cy - 4, cx + 14, cy + 16], 0, 180, fill=col, width=3)
    d.line([cx, cy + 16, cx, cy + 22], fill=col, width=3)
    d.line([cx - 8, cy + 22, cx + 8, cy + 22], fill=col, width=3)
    return img


class SttTrayApp:
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title(APP_NAME)
        self.root.geometry("480x780")
        self.root.minsize(420, 680)
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass

        self._core = None
        self._tray = None
        self._tray_thread = None
        self._status = "Loading…"
        self._model_entries = []
        self._model_by_label = {}
        self._build_ui()
        self.root.after(200, self._boot_engine)

    def _build_ui(self) -> None:
        head = ctk.CTkFrame(self.root, fg_color=CARD, corner_radius=16)
        head.pack(fill="x", padx=18, pady=(18, 10))
        ctk.CTkLabel(
            head,
            text=APP_NAME,
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=ORANGE,
        ).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(
            head,
            text="Hold F11 → live type into any app",
            font=ctk.CTkFont(size=13),
            text_color=MUTED,
        ).pack(anchor="w", padx=18, pady=(0, 4))
        ctk.CTkLabel(
            head,
            text=APP_TAGLINE,
            font=ctk.CTkFont(size=12),
            text_color=ORANGE_DIM,
        ).pack(anchor="w", padx=18, pady=(0, 16))

        self.card = ctk.CTkFrame(self.root, fg_color=CARD, corner_radius=16)
        self.card.pack(fill="x", padx=18, pady=8)

        self.dot = ctk.CTkLabel(self.card, text="●", font=ctk.CTkFont(size=18), text_color=MUTED)
        self.dot.pack(anchor="w", padx=18, pady=(18, 0))
        self.lbl_status = ctk.CTkLabel(
            self.card,
            text="Loading…",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT,
            wraplength=400,
            justify="left",
        )
        self.lbl_status.pack(anchor="w", padx=18, pady=(4, 12))

        self.lbl_mic = ctk.CTkLabel(self.card, text="Mic: —", font=ctk.CTkFont(size=13), text_color=MUTED)
        self.lbl_mic.pack(anchor="w", padx=18, pady=2)
        self.lbl_hk = ctk.CTkLabel(self.card, text="Hotkey: F11", font=ctk.CTkFont(size=13), text_color=MUTED)
        self.lbl_hk.pack(anchor="w", padx=18, pady=2)
        self.lbl_hint = ctk.CTkLabel(
            self.card,
            text="Target: mouse / focus  ·  F11=record  ·  release=flush only",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
        )
        self.lbl_hint.pack(anchor="w", padx=18, pady=(2, 4))
        self.lbl_gpu = ctk.CTkLabel(
            self.card,
            text="ASR: CPU · Kroko streaming (Sherpa-ONNX)",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
        )
        self.lbl_gpu.pack(anchor="w", padx=18, pady=(2, 4))

        # --- Model picker (UVR-style download + switch) ---
        ctk.CTkLabel(
            self.card,
            text="ASR model",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ORANGE,
        ).pack(anchor="w", padx=18, pady=(8, 2))
        self.lbl_model = ctk.CTkLabel(
            self.card,
            text="Model: Turkish 128L (default)",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
        )
        self.lbl_model.pack(anchor="w", padx=18, pady=(0, 4))
        self.cmb_model = ctk.CTkComboBox(
            self.card,
            values=["Turkish · 128L (default, bundled)"],
            width=400,
            height=32,
            fg_color="#1E1E1E",
            border_color=ORANGE_DIM,
            button_color=ORANGE_DIM,
            button_hover_color=ORANGE,
            dropdown_fg_color="#1E1E1E",
            command=self._on_model_pick,
        )
        self.cmb_model.pack(fill="x", padx=18, pady=(0, 4))
        model_btn = ctk.CTkFrame(self.card, fg_color="transparent")
        model_btn.pack(fill="x", padx=18, pady=(0, 4))
        self.btn_model_dl = ctk.CTkButton(
            model_btn,
            text="Download / Apply model",
            fg_color=ORANGE,
            hover_color=ORANGE_HOVER,
            text_color="#111",
            height=32,
            corner_radius=10,
            command=self._apply_selected_model,
        )
        self.btn_model_dl.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.btn_model_refresh = ctk.CTkButton(
            model_btn,
            text="Refresh list",
            fg_color="#333",
            hover_color="#444",
            text_color=TEXT,
            width=110,
            height=32,
            corner_radius=10,
            command=self._refresh_model_list,
        )
        self.btn_model_refresh.pack(side="right")
        self.lbl_model_prog = ctk.CTkLabel(
            self.card,
            text="Source: Hugging Face Kroko · sherpa int8 packs",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            wraplength=420,
            justify="left",
        )
        self.lbl_model_prog.pack(anchor="w", padx=18, pady=(0, 8))
        self.root.after(100, self._load_model_combo)

        ctk.CTkLabel(self.card, text="Last text", font=ctk.CTkFont(size=12), text_color=MUTED).pack(
            anchor="w", padx=18, pady=(8, 2)
        )
        self.txt_partial = ctk.CTkTextbox(
            self.card,
            height=72,
            fg_color="#1E1E1E",
            text_color=TEXT,
            border_color=ORANGE_DIM,
            border_width=1,
            corner_radius=10,
            font=ctk.CTkFont(size=13),
        )
        self.txt_partial.pack(fill="x", padx=18, pady=(0, 12))
        self.txt_partial.insert("1.0", "—")
        self.txt_partial.configure(state="disabled")

        ctk.CTkLabel(
            self.card,
            text="Why local Kroko (not Whisper)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ORANGE,
        ).pack(anchor="w", padx=18, pady=(4, 2))
        self.txt_about = ctk.CTkTextbox(
            self.card,
            height=100,
            fg_color="#1E1E1E",
            text_color=MUTED,
            border_color="#333",
            border_width=1,
            corner_radius=10,
            font=ctk.CTkFont(size=11),
            wrap="word",
        )
        self.txt_about.pack(fill="x", padx=18, pady=(0, 16))
        self.txt_about.insert("1.0", ABOUT_TEXT)
        self.txt_about.configure(state="disabled")

        btn_row = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(4, 8))

        self.btn_listen = ctk.CTkButton(
            btn_row,
            text="F11 / Hold = Listen",
            fg_color=ORANGE,
            hover_color=ORANGE_HOVER,
            text_color="#111",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            corner_radius=12,
        )
        self.btn_listen.pack(fill="x", pady=4)
        self.btn_listen.bind("<ButtonPress-1>", self._ui_ptt_down)
        self.btn_listen.bind("<ButtonRelease-1>", self._ui_ptt_up)

        self.btn_tray = ctk.CTkButton(
            btn_row,
            text="Hide to tray",
            fg_color="#333",
            hover_color="#444",
            text_color=TEXT,
            height=40,
            corner_radius=12,
            command=self._hide_to_tray,
        )
        self.btn_tray.pack(fill="x", pady=4)

        self.btn_restart = ctk.CTkButton(
            btn_row,
            text="Restart engine",
            fg_color=ORANGE_DIM,
            hover_color=ORANGE,
            text_color="#111",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            corner_radius=12,
            command=self._restart,
        )
        self.btn_restart.pack(fill="x", pady=4)

        self.btn_quit = ctk.CTkButton(
            btn_row,
            text="Quit",
            fg_color="#3A1515",
            hover_color="#5A2020",
            text_color="#FFAAAA",
            height=36,
            corner_radius=12,
            command=self._quit,
        )
        self.btn_quit.pack(fill="x", pady=(4, 12))

        foot = ctk.CTkLabel(
            self.root,
            text="Local only · tray always on · Whisper can stay in the cloud",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
        )
        foot.pack(pady=(0, 12))

        self.root.after(300, self._tick_ui)

    def _flash_hint(self) -> None:
        self._set_status("Keyboard: hold F11 and speak", ok=True)

    def _ui_ptt_down(self, _event=None) -> None:
        try:
            if self._core and self._core.hotkey:
                self._core.hotkey.inject_ui_down()
                self._set_status("Listening… (UI button)", ok=None)
        except Exception as e:
            self._set_status(f"UI down error: {e}", ok=False)

    def _ui_ptt_up(self, _event=None) -> None:
        try:
            if self._core and self._core.hotkey:
                self._core.hotkey.inject_ui_up()
        except Exception as e:
            self._set_status(f"UI up error: {e}", ok=False)

    def _set_status(self, s: str, ok: bool | None = None) -> None:
        self._status = s
        self.lbl_status.configure(text=s)
        if ok is True:
            self.dot.configure(text_color=GREEN)
        elif ok is False:
            self.dot.configure(text_color=RED)
        elif "Listening" in s:
            self.dot.configure(text_color=ORANGE)
        else:
            self.dot.configure(text_color=GREEN if "Ready" in s else MUTED)

    def _boot_engine(self) -> None:
        def work():
            try:
                from app.stt_core import SttCore

                def on_status(s: str):
                    def _u():
                        try:
                            self._set_status(s)
                        except Exception:
                            pass

                    self.root.after(0, _u)

                core = SttCore(on_status=on_status)
                core.start()
                self._core = core
                self.root.after(0, lambda: self._on_engine_ready(core))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"Error: {e}", ok=False))

        threading.Thread(target=work, daemon=True).start()
        self._start_tray()

    def _load_model_combo(self) -> None:
        from app.model_catalog import find_by_local_dir, list_catalog
        from app.stt_core import load_config

        try:
            entries = list_catalog()
        except Exception:
            entries = []
        self._model_entries = entries
        labels = []
        self._model_by_label = {}
        for m in entries:
            mark = " ✓" if m.is_installed() else " (download)"
            lab = f"{m.label}{mark}"
            labels.append(lab)
            self._model_by_label[lab] = m
            self._model_by_label[m.label] = m
        if not labels:
            labels = ["Turkish · 128L (default, bundled)"]
        self.cmb_model.configure(values=labels)
        # select current from config
        try:
            cfg = load_config()
            rel = (cfg.get("asr") or {}).get("modelDir", "model/kroko-tr-128l")
            cur = find_by_local_dir(rel)
            if cur:
                for lab, ent in self._model_by_label.items():
                    if ent.id == cur.id and lab in labels:
                        self.cmb_model.set(lab)
                        self.lbl_model.configure(
                            text=f"Model: {cur.label}" + (" · installed" if cur.is_installed() else "")
                        )
                        break
            else:
                self.cmb_model.set(labels[0])
        except Exception:
            self.cmb_model.set(labels[0])

    def _on_model_pick(self, choice: str) -> None:
        m = self._model_by_label.get(choice)
        if not m:
            return
        st = "installed" if m.is_installed() else "not downloaded (~150 MB)"
        self.lbl_model.configure(text=f"Model: {m.label} · {st}")
        self.lbl_model_prog.configure(text=f"Path: {m.local_dir}")

    def _refresh_model_list(self) -> None:
        self.lbl_model_prog.configure(text="Refreshing list from Hugging Face…")

        def work():
            try:
                from app.model_catalog import refresh_catalog_from_hf

                entries = refresh_catalog_from_hf()
                self._model_entries = entries
                labels = []
                self._model_by_label = {}
                for m in entries:
                    mark = " ✓" if m.is_installed() else " (download)"
                    lab = f"{m.label}{mark}"
                    labels.append(lab)
                    self._model_by_label[lab] = m

                def ui():
                    self.cmb_model.configure(values=labels or ["(empty)"])
                    if labels:
                        self.cmb_model.set(labels[0])
                    self.lbl_model_prog.configure(
                        text=f"Found {len(labels)} models · HF list OK"
                    )

                self.root.after(0, ui)
            except Exception as e:
                self.root.after(
                    0,
                    lambda: self.lbl_model_prog.configure(text=f"Refresh failed: {e}"),
                )

        threading.Thread(target=work, daemon=True).start()

    def _apply_selected_model(self) -> None:
        choice = self.cmb_model.get()
        m = self._model_by_label.get(choice)
        if not m:
            # try strip ✓ / (download)
            for lab, ent in self._model_by_label.items():
                if choice.startswith(ent.label):
                    m = ent
                    break
        if not m:
            self._set_status("Pick a model first", ok=False)
            return
        self.btn_model_dl.configure(state="disabled")
        self._set_status(f"Model: {m.label}…", ok=None)

        def work():
            try:
                from app.model_catalog import apply_model_to_config, download_model

                def prog(s: str):
                    self.root.after(0, lambda t=s: self.lbl_model_prog.configure(text=t))

                if not m.is_installed():
                    prog("Downloading (~150 MB, needs internet)…")
                    download_model(m, on_progress=prog)
                apply_model_to_config(m)
                self.root.after(
                    0,
                    lambda: self.lbl_model.configure(text=f"Model: {m.label} · loading…"),
                )
                # unload old engine, load new
                self.root.after(0, self._restart)
                self.root.after(
                    0,
                    lambda: self.lbl_model_prog.configure(
                        text=f"Active: {m.local_dir} · engine restarting"
                    ),
                )
            except Exception as e:
                self.root.after(
                    0, lambda: self._set_status(f"Model error: {e}", ok=False)
                )
                self.root.after(
                    0, lambda: self.lbl_model_prog.configure(text=f"Failed: {e}")
                )
            finally:
                self.root.after(0, lambda: self.btn_model_dl.configure(state="normal"))
                self.root.after(500, self._load_model_combo)

        threading.Thread(target=work, daemon=True).start()

    def _on_engine_ready(self, core) -> None:
        self.lbl_mic.configure(text=f"Mic: {core.mic_label}")
        self.lbl_hk.configure(text=f"Hotkey: {core.hotkey_label}")
        prov = getattr(core.engine, "provider_used", "cpu")
        model_name = "Kroko"
        try:
            from app.model_catalog import find_by_local_dir
            from app.stt_core import load_config

            rel = (load_config().get("asr") or {}).get("modelDir", "")
            ent = find_by_local_dir(rel)
            if ent:
                model_name = ent.label
                self.lbl_model.configure(text=f"Model: {ent.label} · active")
        except Exception:
            pass
        self.lbl_gpu.configure(
            text=f"ASR: {prov.upper()} · {model_name}"
        )
        self._set_status("Ready — hold F11", ok=True)
        try:
            self.root.update_idletasks()
            hwnd = int(self.root.winfo_id())
            import ctypes

            user32 = ctypes.windll.user32
            GA_ROOT = 2
            root_hwnd = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
            core.injector.set_exclude(root_hwnd)
        except Exception:
            pass

    def _tick_ui(self) -> None:
        if self._core is not None:
            p = self._core.partial
            self.txt_partial.configure(state="normal")
            self.txt_partial.delete("1.0", "end")
            self.txt_partial.insert("1.0", p or "—")
            self.txt_partial.configure(state="disabled")
            if self._core.listening:
                self.dot.configure(text_color=ORANGE)
                self.btn_listen.configure(fg_color=GREEN, text="● Listening…")
            else:
                self.btn_listen.configure(fg_color=ORANGE, text="F11 = Listen (hold)")
        self.root.after(200, self._tick_ui)

    def _start_tray(self) -> None:
        def run_tray():
            try:
                import pystray

                icon_img = _make_icon(64, False)

                def show(icon=None, item=None):
                    self.root.after(0, self._show_window)

                def quit_app(icon=None, item=None):
                    self.root.after(0, self._quit)

                def restart(icon=None, item=None):
                    self.root.after(0, self._restart)

                menu = pystray.Menu(
                    pystray.MenuItem("Show window", show, default=True),
                    pystray.MenuItem("Restart engine", restart),
                    pystray.MenuItem("Quit", quit_app),
                )
                self._tray = pystray.Icon(
                    "farting_whisper",
                    icon_img,
                    f"{APP_NAME} (F11)",
                    menu,
                )
                self._tray.run()
            except Exception:
                pass

        self._tray_thread = threading.Thread(target=run_tray, name="Tray", daemon=True)
        self._tray_thread.start()

    def _hide_to_tray(self) -> None:
        self.root.withdraw()
        if self._tray:
            try:
                self._tray.notify("In tray — hold F11 to talk", APP_NAME)
            except Exception:
                pass

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.attributes("-topmost", True)
            self.root.after(200, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

    def _restart(self) -> None:
        self._set_status("Restarting…", ok=None)

        def work():
            try:
                if self._core:
                    self._core.stop()
                    self._core = None
                from app.stt_core import SttCore

                def on_status(s: str):
                    self.root.after(0, lambda: self._set_status(s))

                core = SttCore(on_status=on_status)
                core.start()
                self._core = core
                self.root.after(0, lambda: self._on_engine_ready(core))
                self.root.after(0, lambda: self._set_status("Ready — hold F11", ok=True))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(f"Restart error: {e}", ok=False))

        threading.Thread(target=work, daemon=True).start()

    def _quit(self) -> None:
        try:
            if self._core:
                self._core.stop()
        except Exception:
            pass
        try:
            if self._tray:
                self._tray.stop()
        except Exception:
            pass
        try:
            from app.single_instance import release

            release()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    from app.single_instance import ensure_single_or_exit, release

    ensure_single_or_exit()
    try:
        SttTrayApp().run()
    finally:
        release()


if __name__ == "__main__":
    main()
