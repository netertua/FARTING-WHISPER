"""Honest GPU / backend probe. Never claim NPU/CUDA/Vulkan if ASR cannot use it."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field


@dataclass
class GpuReport:
    gpus: list[str] = field(default_factory=list)
    has_nvidia: bool = False
    has_amd: bool = False
    cuda_devices: int = 0
    sherpa_providers: list[str] = field(default_factory=lambda: ["cpu", "cuda", "coreml"])
    asr_ep: str = "cpu"
    note: str = ""

    def summary(self) -> str:
        names = ", ".join(self.gpus) if self.gpus else "yok"
        return (
            f"GPU=[{names}] cuda={self.cuda_devices} "
            f"asr={self.asr_ep} | {self.note}"
        )


def _wmi_gpus() -> list[str]:
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        # drop virtual junk
        return [n for n in lines if "virtual" not in n.lower() and "basic" not in n.lower()]
    except Exception:
        return []


def probe_gpu() -> GpuReport:
    rep = GpuReport()
    rep.gpus = _wmi_gpus()
    low = " ".join(rep.gpus).lower()
    rep.has_nvidia = "nvidia" in low
    rep.has_amd = "amd" in low or "radeon" in low

    try:
        import ctranslate2

        rep.cuda_devices = int(ctranslate2.get_cuda_device_count() or 0)
    except Exception:
        rep.cuda_devices = 0

    # Sherpa OnlineRecognizer: only cpu|cuda|coreml (no vulkan/dml/npu EP in 1.13)
    if rep.cuda_devices > 0 and rep.has_nvidia:
        rep.asr_ep = "cuda"  # preferred if whisper/sherpa can use it
        rep.note = "NVIDIA CUDA var — istenirse whisper/cuda yolu"
    elif rep.has_amd:
        rep.asr_ep = "cpu"
        rep.note = (
            "AMD GPU goruldu ama Sherpa ASR EP: cpu only "
            "(cuda/coreml disinda vulkan YOK bu build'de). Live STT = Kroko@cpu"
        )
    else:
        rep.asr_ep = "cpu"
        rep.note = "Live STT = Kroko@cpu (Sherpa: cpu|cuda|coreml; vulkan EP yok)"
    return rep
