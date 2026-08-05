# FARTING-WHISPER

Local hold-to-talk STT for Windows. **Hold F11** → text goes into the focused app.  
**Fully offline. CPU only. Free. Do not sell this.**

Built with **[Grok Build](https://x.ai)** (xAI).

---

## Why this exists

**Win+H** needs the internet / Microsoft cloud. Useless on a ship, bad satcom, or air-gapped desk.

**OpenAI Whisper / faster-whisper** wants CUDA, eats RAM/VRAM, and is a pain to install for simple live typing.  
**FARTING-WHISPER** is the götlük answer: same job, **local**, **CPU**, no OpenAI tax, no cloud.

| | Win+H | Whisper / faster-whisper | FARTING-WHISPER |
|--|--------|---------------------------|-----------------|
| Internet | Yes | No* | **No** |
| GPU / CUDA | — | Usually yes | **No — CPU** |
| Live PTT → any app | Meh | DIY hell | **F11 hold** |
| Price | “Free” + account | Free + suffering | **Free — don’t sell it** |

\*Offline Whisper exists; live PC-wide PTT on a laptop still sucks.

**ASR:** [Kroko](https://github.com/k2-fsa/sherpa-onnx) **TR-128L** (Turkish + English) via **Sherpa-ONNX**.  
Other Kroko / Sherpa language packs can replace `model/kroko-tr-128l/` if you want.

---

## Rules

- **Free forever.** Personal use OK.  
- **No selling.** No paid forks, no paywall, no “premium” of this app.  
- See [`LICENSE`](LICENSE).

---

## Install (Windows)

Python 3.11+, mic.

```bat
cd FARTING-WHISPER
python -m pip install -r requirements.txt
run.bat
```

Debug: `run-debug.bat` · or `python -m app.stt_app`

**Use:** click target app → **hold F11** → speak → release.

Model: `model/kroko-tr-128l/` (~150 MB). GitHub upload: use **Git LFS** if `encoder.int8.onnx` is rejected (>100 MB).

---

**FARTING-WHISPER** — offline CPU STT. Whisper can keep the CUDA bill.
