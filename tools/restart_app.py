"""Kill existing FARTING-WHISPER and relaunch (WMI — survives agent job)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "restart.txt"
PYW = Path.home() / "AppData/Local/Programs/Python/Python311/pythonw.exe"
if not PYW.is_file():
    PYW = Path(sys.executable)


def log(msg: str) -> None:
    LOG.parent.mkdir(exist_ok=True)
    line = f"{time.strftime('%H:%M:%S')} {msg}\n"
    print(line, end="", flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)


def kill_stt() -> None:
    try:
        import psutil
    except ImportError:
        return
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = p.info.get("cmdline") or []
            if cl and "-m" in cl and "app.stt_app" in cl:
                log(f"kill {p.pid}")
                p.kill()
        except Exception as e:
            log(f"kill err {e}")


def launch_wmi() -> int | None:
    import win32com.client  # type: ignore

    cmd = f'"{PYW}" -u -m app.stt_app'
    try:
        wmi = win32com.client.GetObject("winmgmts:")
        # fallback below if pywin32 missing
    except Exception:
        wmi = None
    if wmi is None:
        # pure ctypes / subprocess via Win32_Process
        try:
            import wmi as wmi_mod  # type: ignore

            c = wmi_mod.WMI()
            pid, ret = c.Win32_Process.Create(CommandLine=cmd, CurrentDirectory=str(ROOT))
            log(f"wmi-mod ret={ret} pid={pid}")
            return int(pid) if ret == 0 else None
        except Exception:
            pass
        # powershell WMI one-liner
        import subprocess

        ps = (
            f'$r=([wmiclass]"Win32_Process").Create(\'{cmd}\', r\'{ROOT}\'); '
            f'Write-Output $r.ReturnValue; Write-Output $r.ProcessId'
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            timeout=30,
        )
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        log(f"ps wmi out={lines}")
        if len(lines) >= 2 and lines[0] == "0":
            return int(lines[1])
        return None

    # unused branch
    return None


def launch_wmi_simple() -> int | None:
    """Use PowerShell Win32_Process.Create — reliable detach from agent job."""
    import subprocess

    cmd = f'\\"{PYW}\\" -u -m app.stt_app'.replace("\\\\", "\\")
    # cleaner:
    cmd_line = f'"{PYW}" -u -m app.stt_app'
    ps = (
        f"$r = ([wmiclass]\"Win32_Process\").Create('{cmd_line}', '{ROOT}'); "
        f"Write-Output \"$($r.ReturnValue) $($r.ProcessId)\""
    )
    out = subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", ps],
        text=True,
        timeout=30,
    ).strip()
    log(f"wmi {out}")
    parts = out.split()
    if len(parts) >= 2 and parts[0] == "0":
        return int(parts[1])
    return None


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    log("=== restart ===")
    kill_stt()
    time.sleep(1.0)
    pid = launch_wmi_simple()
    if not pid:
        log("launch failed")
        return 1
    log(f"launched pid={pid}")
    time.sleep(12)
    try:
        import psutil

        log(f"alive={psutil.pid_exists(pid)}")
    except Exception:
        pass
    try:
        import ctypes

        h = ctypes.windll.user32.FindWindowW(None, "FARTING-WHISPER")
        log(f"hwnd={int(h) if h else 0}")
        if h:
            ctypes.windll.user32.ShowWindow(h, 9)
            ctypes.windll.user32.SetForegroundWindow(h)
    except Exception as e:
        log(f"hwnd err {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
