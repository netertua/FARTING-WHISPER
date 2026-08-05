# FARTING-WHISPER

**Local hold-to-talk speech-to-text for Windows.**  
Hold **F11** → live text lands in whatever app you focused. No cloud. No API key. No upload.

### Free. Always.

**FARTING-WHISPER is a free application.**  
Nobody may sell it. Nobody may charge money for it, wrap it as a paid product, or put it behind a paywall. No “premium fork” of this app for cash. Personal use, share the source, improve it — **don’t sell it**. See [`LICENSE`](LICENSE).

> Built with **[Grok Build](https://x.ai)** (xAI). Grok Build is early / shipping fast — still young, still cooking. This repo is **not** a roast of Grok Build. The roasts below are reserved for the usual cloud-first speech circus.

---

## What it is

| Piece | Choice |
|--------|--------|
| **Product** | FARTING-WHISPER |
| **Price** | **Free** — no commercial sale |
| **ASR** | **Kroko TR-128L** streaming (Turkish + English) |
| **Runtime** | [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) on **CPU** |
| **UI** | CustomTkinter dark + orange, system tray |
| **Hotkey** | **F11** hold-to-talk (release = flush held audio only) |
| **Target** | Focused / last-clicked window (PC-wide inject) |
| **Privacy** | 100% on-device — works with **no internet** |

Bundled model path: `model/kroko-tr-128l/`  
(`encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx`, `tokens.txt`)

---

## Why not Windows + H (Win+H)?

Windows has built-in dictation: **Win + H**.

We did **not** build FARTING-WHISPER because we hate the shortcut. We built it because **Win+H is not a real offline tool**.

- **Win+H expects connectivity.** Microsoft’s voice stack is cloud-backed for recognition quality. No reliable net → no reliable dictation.  
- **Ships, offshore, remote work:** people at sea, on vessels, on bad VSAT, on metered or blocked links cannot depend on “just open Win+H”. Bandwidth is expensive, latency is ugly, and the link drops when the weather or the provider feels like it.  
- **Privacy / air-gap:** some desks never send mic audio off the machine. Win+H is the wrong architecture for that.  
- **PC-wide hold-to-talk:** we need **F11 hold → stream into the focused app**, not a floating cloud dictation bar that vanishes when the network does.

**That’s why we use Kroko ASR** (Kroko TR-128L) via Sherpa-ONNX: a compact **streaming**, **on-device** model. Turkish + English. CPU. No API key. No upload. If the ship has power and a microphone, FARTING-WHISPER still types.

---

## Why not Whisper / faster-whisper / WhisperX?

Captain’s brief. Straight talk.

### OpenAI Whisper (the original)
Brilliant for **offline files**. Awkward for **live PC-wide PTT** on a normal laptop.  
Big weights, batch DNA, cold starts that feel like waiting for a research demo. Great paper energy. Weak “type while I talk into Notepad” energy.

### faster-whisper
Faster than stock Whisper. Still Whisper’s worldview: **transcribe a clip**, not **stream into the focused window with zero ceremony**. You still drag a heavy stack (CTranslate2, model size, VRAM drama) for a job that should feel like a keyboard.

### WhisperX
Alignment, diarization, pipeline flex — excellent for **post-production**. Overkill for **hold F11 and dunk text into Cursor**. If your problem is podcast chapters, use WhisperX. If your problem is *talk → characters appear now*, you brought a cinema camera to a text message.

### So… why **FARTING-WHISPER**?
Because the name is the joke and the product is the opposite of the joke:

- **Streaming** Kroko, not file-batch Whisper  
- **~150 MB** int8 pack, CPU-friendly  
- **No OpenAI account**, no telemetry ritual, no “paste your key”  
- **Sherpa-ONNX** local graph, not a cloud round-trip  
- **Works offline** — including where Win+H is a non-starter (ships, bad satcom, air-gapped desks)  
- Built for **hold-to-talk → inject**, not for “render my meeting tomorrow”  
- **Free** — not a product to sell

OpenAI can keep the cloud, the waitlist energy, and the name recognition.  
We’ll keep the local lane and the F11 key.

---

## Built with Grok Build

This app was authored and iterated with **Grok Build** (xAI).

Grok Build is **new** — early stage, still evolving. That means:

- We **do** credit it in this README.  
- We **don’t** dunk on it. Give the tool room to grow.  
- If something’s rough, blame the human with the mic, not the forge.

---

## Quick start (Windows)

**Needs:** Python 3.11+, mic, Windows 10/11. **Internet is not required to run recognition** (only to `pip install` once, if packages are not already present).

```bat
cd FARTING-WHISPER
python -m pip install -r requirements.txt
run.bat
```

Debug (console):

```bat
run-debug.bat
```

Or:

```bat
python -m app.stt_app
```

### Hotkey

1. Click the target app (Notepad, browser, IDE…).  
2. **Hold F11** and speak.  
3. **Release F11** — no new audio is captured; queued audio flushes and finishes typing.

Tray: hide to tray, restart engine, quit.

---

## Config

Primary config: `config-grok-build.json`  
Fallback: `config.json`

Useful keys:

- `asr.modelDir` → `model/kroko-tr-128l`  
- `asr.threads` → CPU threads  
- `hotkey.hardwareAliasVks` → default `[122]` = **F11**  
- `streaming.decodeIntervalMs` / `blocksize` → latency vs load  

Logs: `logs/life.log`, `logs/grok-voice.log` (created at runtime).

---

## Repo layout

```
FARTING-WHISPER/
  app/                 # tray UI + STT core + inject + hotkey
  model/kroko-tr-128l/ # Kroko TR streaming ONNX (int8)
  config-grok-build.json
  requirements.txt
  run.bat
  run-debug.bat
  LICENSE
  README.md
```

---

## GitHub note (model size)

`encoder.int8.onnx` is **~146 MB**. GitHub rejects blobs **> 100 MB** without **Git LFS**.

```bash
git lfs install
git lfs track "model/**/*.onnx"
git add .gitattributes
git add .
git commit -m "Initial FARTING-WHISPER release"
git remote add origin https://github.com/<you>/FARTING-WHISPER.git
git push -u origin main
```

`.gitattributes` is already set for ONNX → LFS.

---

## Dependencies (runtime)

- `sherpa-onnx` — ASR  
- `sounddevice` — mic  
- `numpy`  
- `customtkinter` + `pystray` + `Pillow` — UI / tray  
- `keyboard` — global F11 hook  
- `pyperclip` — clipboard helpers where used  

**Not used:** Streamlit, PyTorch, CUDA-required stacks, OpenAI API, Win+H / cloud dictation.

---

## License — free, no selling

**Not MIT.** MIT would allow someone to sell copies. That is the opposite of the project intent.

FARTING-WHISPER is released under a **Free Non-Commercial** license (`LICENSE`):

- Use it free  
- Share and modify free  
- **Do not sell the app**  
- **Do not charge for access / paid redistributions of this app**  

Upstream model weights and libraries (Kroko, Sherpa-ONNX, pip packages) keep their own licenses — respect those when you redistribute.

---

## Credits

- **Kroko TR-128L** streaming ASR (on-device) — why this works at sea and offline  
- **Sherpa-ONNX** / k2-fsa ecosystem  
- **Grok Build** (xAI) — build forge for this project  
- You — for preferring local tools over “upload your voice real quick”

---

**FARTING-WHISPER** — local speech that actually types. Free. Offline.  
Win+H can keep the cloud. We’ll keep the ship.  
Whisper can stay famous. We’ll stay offline.
