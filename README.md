# FARTING-WHISPER

Local hold-to-talk speech-to-text for **Windows**.

Hold **F11** → text is typed into the focused app.  
Runs **fully offline** on **CPU**. No cloud. No API key. No CUDA required.

Built with **[Grok Build](https://x.ai)** (xAI).

**Free software. Do not sell it.** See [`LICENSE`](LICENSE).

---

## Why FARTING-WHISPER?

| Option | Problem |
|--------|---------|
| **Win + H** (Windows dictation) | Needs internet / Microsoft cloud services. Unreliable on ships, satcom, or offline machines. |
| **OpenAI Whisper / faster-whisper** | Heavy stack, often wants a **CUDA** GPU, high resource use, painful setup for simple live typing. |
| **FARTING-WHISPER** | **Kroko TR-128L** streaming ASR via **Sherpa-ONNX** on **CPU**. Local model, hold-to-talk, inject into any window. |

This project exists because those options were a bad fit for real offline / low-resource use.  
ASR model in this repo: **Kroko Turkish + English** (`model/kroko-tr-128l/`). Other Sherpa/Kroko language packs can replace that folder if you want.

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

If `model/kroko-tr-128l/*.onnx` files are tiny pointers after clone, run:

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

Debug (console window):

```bat
run-debug.bat
```

### 5. Use

1. Click the target app (Notepad, browser, editor…).  
2. **Hold F11** and speak.  
3. **Release F11** — recording stops; remaining audio is flushed and typed.

Tray icon: show window, restart engine, quit.

---

## Project layout

```
FARTING-WHISPER/
  app/                  # UI + STT engine + hotkey + inject
  model/kroko-tr-128l/  # Kroko TR/EN ONNX (int8)
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

## Credits

- **Kroko TR-128L** + **Sherpa-ONNX** — on-device ASR  
- **Grok Build** (xAI) — used to build this project  
