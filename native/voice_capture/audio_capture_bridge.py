"""
Native Audio Capture Bridge — Python ctypes interface to WASAPI audio capture.

Provides a Python generator of audio chunks from the native audio capture DLL.
Falls back to PyAudio or simulated capture if the native DLL is not available.
"""

import ctypes
import logging
import os
import struct
import time
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# Paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CAPTURE_DIR = Path(__file__).resolve().parent
_CAPTURE_LIB = "native_audio_capture.dll" if os.name == "nt" else "libnative_audio_capture.so"


class NativeAudioCapture:
    """
    Python bridge to native WASAPI audio capture.

    If the native DLL is not built, falls back to PyAudio.
    Provides a chunked audio generator for streaming to STT.
    """

    def __init__(self, sample_rate: int = 16000, chunk_size: int = 4096,
                 channels: int = 1, bits_per_sample: int = 16):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.bits_per_sample = bits_per_sample
        self._lib: Optional[ctypes.CDLL] = None
        self._fallback_stream = None
        self._mode = "NONE"

        self._load_native()

    def _load_native(self):
        """Try to load native WASAPI capture DLL."""
        lib_path = _CAPTURE_DIR / _CAPTURE_LIB
        if not lib_path.exists():
            logger.info(
                f"[AUDIO] Native capture DLL not found: {lib_path}. "
                f"Will use PyAudio fallback."
            )
            self._mode = "PYAUDIO"
            return

        try:
            self._lib = ctypes.CDLL(str(lib_path))

            # Configure function signatures
            self._lib.audio_capture_init.restype = ctypes.c_int
            self._lib.audio_capture_init.argtypes = [
                ctypes.c_int, ctypes.c_int, ctypes.c_int,  # sample_rate, channels, bits
            ]

            self._lib.audio_capture_read.restype = ctypes.c_int
            self._lib.audio_capture_read.argtypes = [
                ctypes.c_char_p, ctypes.c_int,  # buffer, buffer_size
            ]

            self._lib.audio_capture_stop.restype = None
            self._lib.audio_capture_stop.argtypes = []

            # Initialize
            rc = self._lib.audio_capture_init(
                self.sample_rate, self.channels, self.bits_per_sample
            )
            if rc == 0:
                self._mode = "NATIVE"
                logger.info("[AUDIO] Native WASAPI capture initialized")
            else:
                logger.warning(f"[AUDIO] Native init failed (rc={rc}), using PyAudio fallback")
                self._lib = None
                self._mode = "PYAUDIO"

        except Exception as e:
            logger.warning(f"[AUDIO] Native load failed: {e}, using PyAudio fallback")
            self._lib = None
            self._mode = "PYAUDIO"

    def capture_chunks(self, duration_s: float = 0, max_chunks: int = 0) -> Generator[bytes, None, None]:
        """
        Generator yielding audio chunks.

        Args:
            duration_s: Total capture duration (0 = unlimited)
            max_chunks: Max chunks to yield (0 = unlimited)

        Yields:
            bytes: PCM audio chunks (16-bit, mono)
        """
        if self._mode == "NATIVE":
            yield from self._capture_native(duration_s, max_chunks)
        elif self._mode == "PYAUDIO":
            yield from self._capture_pyaudio(duration_s, max_chunks)
        else:
            logger.error("[AUDIO] No capture backend available")

    def _capture_native(self, duration_s: float, max_chunks: int) -> Generator[bytes, None, None]:
        """Capture from native WASAPI DLL."""
        buf = ctypes.create_string_buffer(self.chunk_size)
        start = time.time()
        chunks = 0

        while True:
            if duration_s > 0 and (time.time() - start) >= duration_s:
                break
            if max_chunks > 0 and chunks >= max_chunks:
                break

            bytes_read = self._lib.audio_capture_read(buf, self.chunk_size)
            if bytes_read > 0:
                yield buf.raw[:bytes_read]
                chunks += 1
            else:
                time.sleep(0.01)  # Brief sleep to avoid busy-wait

    def _capture_pyaudio(self, duration_s: float, max_chunks: int) -> Generator[bytes, None, None]:
        """Capture from PyAudio (fallback)."""
        try:
            import pyaudio
        except ImportError:
            logger.error("[AUDIO] PyAudio not installed. Cannot capture audio.")
            return

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size // 2,  # 16-bit = 2 bytes/sample
            )

            start = time.time()
            chunks = 0

            while True:
                if duration_s > 0 and (time.time() - start) >= duration_s:
                    break
                if max_chunks > 0 and chunks >= max_chunks:
                    break

                try:
                    data = stream.read(self.chunk_size // 2, exception_on_overflow=False)
                    yield data
                    chunks += 1
                except IOError:
                    continue

        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def stop(self):
        """Stop capture."""
        if self._mode == "NATIVE" and self._lib:
            self._lib.audio_capture_stop()
        self._mode = "STOPPED"

    def get_status(self) -> dict:
        """Get capture status."""
        return {
            "mode": self._mode,
            "sample_rate": self.sample_rate,
            "chunk_size": self.chunk_size,
            "channels": self.channels,
            "bits_per_sample": self.bits_per_sample,
            "native_available": self._lib is not None,
        }


# Singleton
_capture: Optional[NativeAudioCapture] = None


def get_audio_capture() -> NativeAudioCapture:
    """Get or create the singleton NativeAudioCapture."""
    global _capture
    if _capture is None:
        _capture = NativeAudioCapture()
    return _capture
