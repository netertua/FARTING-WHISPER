"""
DLL bootstrap: prefer Sherpa-bundled onnxruntime for ASR (CPU).
No NPU/IPU claims — ASR does not run on NPU here.
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from app.paths import app_root, resource_root

ROOT = app_root()


def _sherpa_lib_dir() -> Path | None:
    candidates = [
        resource_root() / "sherpa_onnx" / "lib",
        Path(sys.prefix) / "Lib" / "site-packages" / "sherpa_onnx" / "lib",
        Path(sys.base_prefix) / "Lib" / "site-packages" / "sherpa_onnx" / "lib",
        Path(sys.executable).resolve().parent / "_internal" / "sherpa_onnx" / "lib",
        Path(sys.executable).resolve().parent / "sherpa_onnx" / "lib",
    ]
    for p in sys.path:
        candidates.append(Path(p) / "sherpa_onnx" / "lib")
    for lib in candidates:
        if (lib / "onnxruntime.dll").is_file():
            return lib
    return None


def prefer_sherpa_ort() -> str:
    """Load Sherpa onnxruntime.dll for CPU ASR. No NPU bootstrap."""
    lib = _sherpa_lib_dir()
    if lib is None:
        return "sherpa lib not found (CPU path only)"

    ort = lib / "onnxruntime.dll"
    try:
        os.add_dll_directory(str(lib))
    except (AttributeError, OSError):
        pass
    os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
    # Explicit: no NPU marketing in env
    os.environ.pop("IPU_KROKO_BACKEND", None)
    os.environ["IPU_KROKO_ASR"] = "cpu"

    try:
        ctypes.WinDLL(str(ort))
        for extra in ("sherpa-onnx-c-api.dll", "sherpa-onnx-cxx-api.dll"):
            p = lib / extra
            if p.is_file():
                try:
                    ctypes.WinDLL(str(p))
                except OSError:
                    pass
        return f"ASR=cpu sherpa_ort={ort.name}"
    except OSError as e:
        return f"ASR=cpu preload fail {ort}: {e}"
