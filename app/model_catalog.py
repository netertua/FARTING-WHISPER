"""
Kroko model catalog + download (UVR-style).

Official Kroko community page (Banafo):
  https://huggingface.co/Banafo/Kroko-ASR
  → ships .data packs for Kroko native runtime (not raw Sherpa files).

This app uses **Sherpa-ONNX** int8 packs (encoder/decoder/joiner/tokens).
Compatible packs are pulled from:
  https://huggingface.co/hudaiapa88/sherpa-stt-onnx
  (Kroko Zipformer family, same languages)

Default bundled model stays: model/kroko-tr-128l (TR 128L).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.paths import app_root, resource_root

HF_BANAFO = "https://huggingface.co/Banafo/Kroko-ASR"
HF_SHERPA_REPO = "hudaiapa88/sherpa-stt-onnx"
HF_API_TREE = f"https://huggingface.co/api/models/{HF_SHERPA_REPO}/tree/main"
HF_RESOLVE = f"https://huggingface.co/{HF_SHERPA_REPO}/resolve/main"

# Files required by sherpa OnlineRecognizer.from_transducer
SHERPA_FILES = (
    "encoder.int8.onnx",
    "decoder.int8.onnx",
    "joiner.int8.onnx",
    "tokens.txt",
)

LANG_NAMES = {
    "tr": "Turkish",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "sv": "Swedish",
    "iw": "Hebrew",
}


@dataclass
class ModelEntry:
    id: str
    label: str
    lang: str
    local_dir: str  # relative to app root, e.g. model/kroko-tr-128l
    hf_path: str  # e.g. tr/kroko_128l
    size_hint: str = "~150 MB"
    bundled: bool = False

    def abs_dir(self) -> Path:
        root = app_root()
        p = root / self.local_dir
        if (p / "encoder.int8.onnx").is_file():
            return p
        res = resource_root() / self.local_dir
        if (res / "encoder.int8.onnx").is_file():
            return res
        return p

    def is_installed(self) -> bool:
        d = self.abs_dir()
        return all((d / f).is_file() for f in SHERPA_FILES)


# Built-in catalog (works offline for listing; download needs net)
DEFAULT_CATALOG: list[ModelEntry] = [
    ModelEntry(
        id="tr-128l",
        label="Turkish · 128L (default, bundled)",
        lang="tr",
        local_dir="model/kroko-tr-128l",
        hf_path="tr/kroko_128l",
        bundled=True,
    ),
    ModelEntry(
        id="tr-64l",
        label="Turkish · 64L",
        lang="tr",
        local_dir="model/kroko-tr-64l",
        hf_path="tr/kroko_64l",
    ),
    ModelEntry(
        id="en-128l",
        label="English · 128L",
        lang="en",
        local_dir="model/kroko-en-128l",
        hf_path="en/kroko_128l",
    ),
    ModelEntry(
        id="en-64l",
        label="English · 64L",
        lang="en",
        local_dir="model/kroko-en-64l",
        hf_path="en/kroko_64l",
    ),
    ModelEntry(
        id="de-128l",
        label="German · 128L",
        lang="de",
        local_dir="model/kroko-de-128l",
        hf_path="de/kroko_128l",
    ),
    ModelEntry(
        id="fr-128l",
        label="French · 128L",
        lang="fr",
        local_dir="model/kroko-fr-128l",
        hf_path="fr/kroko_128l",
    ),
    ModelEntry(
        id="es-128l",
        label="Spanish · 128L",
        lang="es",
        local_dir="model/kroko-es-128l",
        hf_path="es/kroko_128l",
    ),
    ModelEntry(
        id="it-128l",
        label="Italian · 128L",
        lang="it",
        local_dir="model/kroko-it-128l",
        hf_path="it/kroko_128l",
    ),
    ModelEntry(
        id="pt-128l",
        label="Portuguese · 128L",
        lang="pt",
        local_dir="model/kroko-pt-128l",
        hf_path="pt/kroko_128l",
    ),
]


def list_catalog() -> list[ModelEntry]:
    return list(DEFAULT_CATALOG)


def find_entry(model_id: str) -> ModelEntry | None:
    for m in DEFAULT_CATALOG:
        if m.id == model_id:
            return m
    return None


def find_by_local_dir(rel: str) -> ModelEntry | None:
    rel = (rel or "").replace("\\", "/").strip("/")
    for m in DEFAULT_CATALOG:
        if m.local_dir.replace("\\", "/") == rel:
            return m
    return None


def refresh_catalog_from_hf(timeout: float = 20.0) -> list[ModelEntry]:
    """
    UVR-style: list language/kroko_* folders from HF API and merge into catalog.
    Network required. Falls back to DEFAULT_CATALOG on failure.
    """
    try:
        req = urllib.request.Request(
            HF_API_TREE,
            headers={"User-Agent": "FARTING-WHISPER/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            tree = json.loads(r.read().decode("utf-8"))
    except Exception:
        return list_catalog()

    found: list[ModelEntry] = []
    # top-level lang dirs
    for item in tree:
        if item.get("type") != "directory":
            continue
        lang = item.get("path", "").strip("/")
        if not re.fullmatch(r"[a-z]{2}", lang):
            continue
        try:
            req2 = urllib.request.Request(
                f"{HF_API_TREE}/{lang}",
                headers={"User-Agent": "FARTING-WHISPER/1.0"},
            )
            with urllib.request.urlopen(req2, timeout=timeout) as r2:
                sub = json.loads(r2.read().decode("utf-8"))
        except Exception:
            continue
        for s in sub:
            if s.get("type") != "directory":
                continue
            path = s.get("path", "")  # e.g. en/kroko_128l
            name = path.split("/")[-1]
            m = re.match(r"kroko_(\d+)l", name, re.I)
            if not m:
                continue
            layers = m.group(1)
            mid = f"{lang}-{layers}l"
            label = f"{LANG_NAMES.get(lang, lang.upper())} · {layers}L"
            local = f"model/kroko-{lang}-{layers}l"
            bundled = lang == "tr" and layers == "128" and (
                (app_root() / "model" / "kroko-tr-128l" / "encoder.int8.onnx").is_file()
            )
            if bundled:
                local = "model/kroko-tr-128l"
            found.append(
                ModelEntry(
                    id=mid,
                    label=label + (" (bundled)" if bundled else ""),
                    lang=lang,
                    local_dir=local,
                    hf_path=path,
                    bundled=bundled,
                )
            )

    if not found:
        return list_catalog()
    # prefer default catalog order, append extras from API
    by_id = {m.id: m for m in DEFAULT_CATALOG}
    for m in found:
        by_id.setdefault(m.id, m)
    return list(by_id.values())


def download_model(
    entry: ModelEntry,
    on_progress: Callable[[str], None] | None = None,
    timeout: float = 600.0,
) -> Path:
    """
    Download 4 Sherpa files into entry.local_dir under app_root.
    Returns local directory path.
    """
    dest = app_root() / entry.local_dir
    dest.mkdir(parents=True, exist_ok=True)
    progress = on_progress or (lambda s: None)

    for fname in SHERPA_FILES:
        url = f"{HF_RESOLVE}/{entry.hf_path}/{fname}"
        out = dest / fname
        if out.is_file() and out.stat().st_size > 1000:
            progress(f"OK {fname} (cached)")
            continue
        progress(f"Downloading {fname}…")
        tmp = out.with_suffix(out.suffix + ".part")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FARTING-WHISPER/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as f:
                total = resp.headers.get("Content-Length")
                total_i = int(total) if total and total.isdigit() else 0
                done = 0
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total_i:
                        pct = int(100 * done / total_i)
                        progress(f"{fname}  {pct}%  ({done // 1_000_000} MB)")
            tmp.replace(out)
            progress(f"OK {fname}")
        except Exception:
            if tmp.is_file():
                try:
                    tmp.unlink()
                except Exception:
                    pass
            raise

    if not entry.is_installed():
        raise FileNotFoundError(f"Model incomplete: {dest}")
    progress(f"Installed → {dest.name}")
    return dest


def apply_model_to_config(entry: ModelEntry) -> Path:
    """Write asr.modelDir into config next to the exe / project root."""
    from app.stt_core import _config_path, load_config

    cfg_path = _config_path()
    # Prefer writable root config
    root_cfg = app_root() / "config-grok-build.json"
    if root_cfg.is_file() or not cfg_path.is_file():
        cfg_path = root_cfg
    cfg = {}
    if cfg_path.is_file():
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
    asr = cfg.setdefault("asr", {})
    asr["modelDir"] = entry.local_dir.replace("\\", "/")
    asr["modelId"] = entry.id
    asr["modelLabel"] = entry.label
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return cfg_path
