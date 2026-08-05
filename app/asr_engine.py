"""
Sherpa-ONNX Kroko live STT — net pipeline

MANTIK (tek dogru model):
  F11 BASILI  = dinle/kaydet (chunk -> kuyruk -> model -> metin stream yaz)
  F11 BIRAK   = YENI kayit YOK (capture=False HEMEN)
                kuyrukta / modelde kalan is BITENE kadar devam + yaz
                (birakildiktan sonra konusulan ASLA kayda girmez)

Mic cihaz process boyu acik (acilis gecikmesi yok).
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger("ipu_kroko.asr")

try:
    from app.life_log import life, life_exc
except Exception:
    def life(msg, *a):  # type: ignore
        log.info(msg if not a else msg % a)

    def life_exc(p="EXC"):  # type: ignore
        log.exception(p)


class KrokoEngine:
    def __init__(
        self,
        model_dir: Path,
        sample_rate: int = 16000,
        threads: int = 6,
        provider_chain: list[str] | None = None,
        decoding_method: str = "greedy_search",
        decode_interval_ms: int = 12,
        blocksize: int = 320,
        preferred_mic: str = "",
        flush_timeout_s: float = 20.0,
        **kwargs,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.sample_rate = sample_rate
        self.threads = max(2, int(threads))
        self.decoding_method = decoding_method
        self.decode_interval_ms = max(8, int(decode_interval_ms))
        self.blocksize = int(blocksize)
        self.flush_timeout_s = max(5.0, float(flush_timeout_s))
        self.preferred_mic = preferred_mic or ""
        self.device_index: int | None = None
        self.device_name: str = ""

        self._recognizer = None
        self._provider_used = "cpu"
        self._stream = None
        self._on_text: Callable[[str], None] | None = None

        self._stream_lock = threading.Lock()
        # capture=True SADECE F11 basili — birakinca False, bir daha True olmaz flush'ta
        self._capture = False
        self._flushing = False
        self._typed = ""
        self._last_raw = ""
        self._session_lock = threading.Lock()
        self._alive = True
        self._mic_ready = threading.Event()
        self._peak = 0.0
        self._cb_count = 0
        self._frames_at_release = 0
        self._t0 = 0.0
        self._audio_q: queue.Queue = queue.Queue(maxsize=800)

        self._init_recognizer()
        self.discover_and_select_mic(preferred=self.preferred_mic)
        threading.Thread(target=self._mic_loop, name="Mic", daemon=True).start()
        self._mic_ready.wait(timeout=5.0)
        threading.Thread(target=self._decode_loop, name="Decode", daemon=True).start()
        log.info(
            "READY provider=%s thr=%s mic=[%s] | F11=kayit, release=flush only (no new audio)",
            self._provider_used,
            self.threads,
            self.device_index,
        )

    @property
    def provider_used(self) -> str:
        return self._provider_used

    def set_text_callback(self, cb: Callable[[str], None]) -> None:
        self._on_text = cb

    def discover_and_select_mic(
        self, preferred: str = "", prefer_index: int | None = None
    ) -> dict:
        from app.mic_discover import auto_select_mic

        mic = auto_select_mic(preferred=preferred or self.preferred_mic, prefer_index=prefer_index)
        if mic is None:
            self.device_index = None
            self.device_name = ""
            return {"index": None, "name": ""}
        self.device_index = mic.index
        self.device_name = mic.name
        log.info("Mic: %s", mic.label())
        return {"index": mic.index, "name": mic.name}

    def set_device_index(self, index: int | None) -> None:
        from app.mic_discover import list_input_devices

        if index is None:
            self.discover_and_select_mic()
            return
        for d in list_input_devices():
            if d.index == int(index):
                self.device_index = d.index
                self.device_name = d.name
                return

    def _paths(self) -> dict[str, Path]:
        d = self.model_dir
        return {
            "encoder": d / "encoder.int8.onnx",
            "decoder": d / "decoder.int8.onnx",
            "joiner": d / "joiner.int8.onnx",
            "tokens": d / "tokens.txt",
        }

    def _init_recognizer(self) -> None:
        from app.dll_bootstrap import prefer_sherpa_ort

        prefer_sherpa_ort()
        import sherpa_onnx

        paths = self._paths()
        for p in paths.values():
            if not p.is_file():
                raise FileNotFoundError(p)

        last_err = None
        # dml string unsupported in some builds -> falls back cpu inside sherpa
        for prov in ("cpu",):
            try:
                self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                    tokens=str(paths["tokens"]),
                    encoder=str(paths["encoder"]),
                    decoder=str(paths["decoder"]),
                    joiner=str(paths["joiner"]),
                    num_threads=self.threads,
                    sample_rate=self.sample_rate,
                    feature_dim=80,
                    decoding_method=self.decoding_method,
                    provider=prov,
                    enable_endpoint_detection=False,
                )
                self._provider_used = prov
                log.info("Kroko ready provider=%s threads=%s", prov, self.threads)
                break
            except Exception as e:
                last_err = e
                self._recognizer = None
        if not self._recognizer:
            raise RuntimeError(f"Kroko init failed: {last_err}")

    def start_session(self) -> None:
        with self._session_lock:
            self._capture = False
            self._flushing = False
            while True:
                try:
                    self._audio_q.get_nowait()
                except queue.Empty:
                    break
            with self._stream_lock:
                self._stream = None
            if not self._recognizer:
                raise RuntimeError("no recognizer")
            self._typed = ""
            self._last_raw = ""
            self._peak = 0.0
            self._cb_count = 0
            self._frames_at_release = 0
            self._t0 = time.time()
            with self._stream_lock:
                self._stream = self._recognizer.create_stream()
            # ATOMIC: sadece bundan sonra mic callback ses yazar
            self._capture = True
            log.info("HOLD ON — recording")
            life("HOLD ON")

    def stop_session(self) -> str:
        """
        HOLD OFF:
          1) capture=False HEMEN  -> birakildiktan sonra konusulan KAYDA GIRMEZ
          2) o ana kadar kuyruktaki SES tamamini modele bas
          3) model bitene kadar decode + stream yaz
          4) mic cihaz acik kalir
        """
        with self._session_lock:
            # --- 1) Dinleme/kayit KAPAT (yeni ses yok) ---
            self._capture = False
            self._frames_at_release = self._cb_count
            q_at_release = self._audio_q.qsize()
            self._flushing = True
            log.info(
                "HOLD OFF — kayit DURDU frames=%s queue=%s | simdi SADECE kuyruk+model flush",
                self._frames_at_release,
                q_at_release,
            )

            # --- 2) Kuyrugu tamamen bosalt + decode (sabit sn degil, is bitene) ---
            t0 = time.time()
            idle = 0
            while time.time() - t0 < self.flush_timeout_s:
                n = self._drain_to_stream()
                self._decode_and_emit()
                busy = False
                with self._stream_lock:
                    if self._stream is not None and self._recognizer is not None:
                        try:
                            busy = bool(self._recognizer.is_ready(self._stream))
                        except Exception:
                            busy = False
                if n == 0 and self._audio_q.qsize() == 0 and not busy:
                    idle += 1
                    if idle >= 12:
                        break
                else:
                    idle = 0
                time.sleep(0.01)

            log.info(
                "QUEUE FLUSH done in %.2fs typed_len=%s (no new mic frames after release)",
                time.time() - t0,
                len(self._typed),
            )

            # --- 3) Model utterance sonu (sadece buffer'daki ses, yeni mic yok) ---
            self._end_utterance_write_all()
            self._flushing = False

            with self._stream_lock:
                self._stream = None

            typed = self._typed
            log.info(
                "HOLD DONE peak=%.3f frames_held=%s typed_len=%s FULL=%r",
                self._peak,
                self._frames_at_release,
                len(typed),
                typed,
            )
            # guvenlik: release sonrasi hic frame eklenmemeli
            if self._cb_count > self._frames_at_release:
                log.error(
                    "BUG: release sonrasi %s frame kaydedildi!",
                    self._cb_count - self._frames_at_release,
                )
            life("HOLD DONE len=%s", len(typed))
            return typed

    def _drain_to_stream(self) -> int:
        n = 0
        try:
            while True:
                chunk = self._audio_q.get_nowait()
                with self._stream_lock:
                    if self._stream is not None:
                        self._stream.accept_waveform(self.sample_rate, chunk)
                n += 1
        except queue.Empty:
            pass
        return n

    def _decode_and_emit(self) -> str:
        with self._stream_lock:
            if self._stream is None or self._recognizer is None:
                return ""
            while self._recognizer.is_ready(self._stream):
                self._recognizer.decode_stream(self._stream)
            text = (self._recognizer.get_result(self._stream) or "").strip()
        if text:
            self._emit_live(text)
        return text

    def _end_utterance_write_all(self) -> None:
        """Kayitli ses bitti — model son token'lari versin, hepsini stream yaz."""
        with self._stream_lock:
            if self._stream is None or self._recognizer is None:
                return
            try:
                # Teknik sessizlik (mic degil) — model buffer flush
                tail = np.zeros(int(0.35 * self.sample_rate), dtype=np.float32)
                self._stream.accept_waveform(self.sample_rate, tail)
                self._stream.input_finished()
            except Exception:
                life_exc("end_utt")
                return

        prev = ""
        stable = 0
        for _ in range(80):
            with self._stream_lock:
                if self._stream is None or self._recognizer is None:
                    break
                while self._recognizer.is_ready(self._stream):
                    self._recognizer.decode_stream(self._stream)
                text = (self._recognizer.get_result(self._stream) or "").strip()
            if text:
                self._emit_live(text)
            if text == prev and text:
                stable += 1
                if stable >= 10:
                    break
            else:
                stable = 0
            prev = text
            time.sleep(0.03)

        if prev:
            self._emit_live(prev)
            log.info("[END] full_len=%s text=%r", len(prev), prev)

    def _emit_live(self, raw: str) -> None:
        """Model hyp buyudukce ANINDA yaz — uzunluk/cumle esigi YOK."""
        from app.text_delta import compute_delta

        raw = (raw or "").strip()
        if not raw or raw == self._last_raw:
            return
        delta = compute_delta(self._typed, raw)
        if not delta:
            self._last_raw = raw
            return

        self._last_raw = raw
        self._typed = raw
        ms = int((time.time() - self._t0) * 1000) if self._t0 else 0
        log.info(
            "[STREAM +%sms] +%r total=%s peak=%.2f cap=%s flush=%s",
            ms,
            delta[:60],
            len(raw),
            self._peak,
            self._capture,
            self._flushing,
        )
        if not self._on_text:
            return
        try:
            # Hand full delta to injector; char_delay_ms paces keystrokes (typewriter).
            self._on_text(delta)
        except Exception:
            life_exc("emit")

    def _decode_loop(self) -> None:
        interval = self.decode_interval_ms / 1000.0
        while self._alive:
            try:
                # hold sirasinda: kayit+decode
                # flush session_lock'ta yapilir; hold'da burasi calisir
                if self._capture and not self._flushing:
                    self._drain_to_stream()
                    self._decode_and_emit()
            except Exception as e:
                log.warning("decode: %s", e)
            time.sleep(interval)

    def _mic_loop(self) -> None:
        import sounddevice as sd

        while self._alive:
            dev = self.device_index

            def callback(indata, frames, time_info, status):  # noqa: ARG001
                # KRITIK: sadece _capture True iken kuyruga yaz
                # release sonrasi _capture=False -> konusulan YAZILMAZ/KAYDEDILMEZ
                if not self._capture:
                    return
                try:
                    mono = indata[:, 0] if indata.ndim > 1 else indata
                    samples = np.ascontiguousarray(mono, dtype=np.float32)
                    p = float(np.max(np.abs(samples))) if samples.size else 0.0
                    if p > self._peak:
                        self._peak = p
                    self._cb_count += 1
                    try:
                        self._audio_q.put_nowait(samples.copy())
                    except queue.Full:
                        try:
                            self._audio_q.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            self._audio_q.put_nowait(samples.copy())
                        except queue.Full:
                            pass
                except Exception:
                    pass

            try:
                with sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=self.blocksize,
                    device=dev,
                    callback=callback,
                ):
                    self._mic_ready.set()
                    log.info("Mic device ALWAYS open [%s] %s (capture gated by F11)", dev, self.device_name)
                    while self._alive:
                        time.sleep(0.05)
            except Exception as e:
                self._mic_ready.clear()
                log.error("mic: %s", e)
                time.sleep(1.0)

    def shutdown(self) -> None:
        self._alive = False
        self._capture = False
        self._flushing = False
        with self._stream_lock:
            self._stream = None
