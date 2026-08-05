# FARTING-WHISPER

Local hold-to-talk speech-to-text for **Windows**.

Hold **F11** → text is typed into the focused app.  
Runs **fully offline** on **CPU**. No cloud. No API key. No CUDA required.

Built with **[Grok Build](https://x.ai)** (xAI).

**Free software. Do not sell it.** See [`LICENSE`](LICENSE).

---

## Why this was built

At sea, speech tools fall apart.

- **Win + H** leans on Microsoft / Azure cloud. Bad satcom, no link, or blocked traffic → dictation dies.  
- **Whisper / faster-whisper** often want **CUDA**, heavy RAM/VRAM, and a long install fight — not something you want to debug mid-voyage.  
- Commercial “smart” ASR assumes office Wi‑Fi, not a ship.

**FARTING-WHISPER** is a small local answer: **Kroko TR-128L** (Turkish + English) via **Sherpa-ONNX** on **CPU**, hold-to-talk, type into any focused window. Built because shipboard ASR needed to **just work offline**.

Other Sherpa/Kroko language packs can replace `model/kroko-tr-128l/` if you need another language.

---

## Clone and run

### 1. Requirements

- Windows 10/11  
- Python **3.11+**  
- Microphone  
- [Git](https://git-scm.com/) + [Git LFS](https://git-lfs.com/) (model files are large)

### 2. Clone

```bat
git lfs install
git clone https://github.com/netertua/FARTING-WHISPER.git
cd FARTING-WHISPER
```

If `model/kroko-tr-128l/*.onnx` files look like tiny pointers after clone:

```bat
git lfs pull
```

### 3. Install dependencies

```bat
python -m pip install -r requirements.txt
```

### 4. Start

```bat
run.bat
```

Or:

```bat
python -m app.stt_app
```

Debug (console):

```bat
run-debug.bat
```

### 5. Use

1. Click the target app (Notepad, browser, editor…).  
2. **Hold F11** and speak.  
3. **Release F11** — recording stops; remaining audio is flushed and typed.

Tray: show window, restart engine, quit.

---

## Models (switch / download)

Default: **Turkish 128L** bundled in `model/kroko-tr-128l/`.

In the app UI you can pick another language (EN, DE, FR, ES, IT, PT, …), **Download / Apply**, then the engine restarts on that pack.

- Community catalog page: [Banafo/Kroko-ASR](https://huggingface.co/Banafo/Kroko-ASR) (original Kroko `.data` packs)  
- This app downloads **Sherpa-ONNX int8** packs (encoder/decoder/joiner/tokens) from  
  [hudaiapa88/sherpa-stt-onnx](https://huggingface.co/hudaiapa88/sherpa-stt-onnx) — same Kroko Zipformer family, format our CPU runtime can load.  
- **Refresh list** uses the Hugging Face API to list folders (UVR-style). Offline: built-in catalog still works; download needs internet once.

## Project layout

```
FARTING-WHISPER/
  app/                  # UI + STT engine + hotkey + inject + model catalog
  model/kroko-tr-128l/  # default TR 128L ONNX (int8)
  model/kroko-*-*/      # optional downloads
  config-grok-build.json
  requirements.txt
  run.bat
  run-debug.bat
  LICENSE
  README.md
```

---

## License

Free for personal use. **No commercial sale** of this app.  
Full terms: [`LICENSE`](LICENSE).

Upstream (Sherpa-ONNX, Kroko weights, pip packages) keep their own licenses.

---

## Authors & credits

| | |
|--|--|
| **Idea owner / author** | **Capt. Can Yapıcı** ([@netertua](https://github.com/netertua)) |
| **Collaboration & programming** | **Cansu Yapıcı** ([@netertuas-sissy](https://github.com/netertuas-sissy)) |
| **Build tooling** | [Grok Build](https://x.ai) (xAI) |
| **ASR** | Kroko TR-128L + Sherpa-ONNX |

---

**FARTING-WHISPER** — offline CPU speech-to-text for places the cloud does not reach.
