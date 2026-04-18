from __future__ import annotations

import math
import sys
from array import array
from dataclasses import dataclass


@dataclass(frozen=True)
class EnergyVAD:
    frame_ms: int = 30
    hop_ms: int = 10
    energy_threshold_db: float = -42.0
    min_speech_ms: int = 120
    min_silence_ms: int = 250
    padding_ms: int = 100

    def detect_segments(self, pcm16: bytes, sample_rate: int, channels: int = 1) -> list[tuple[int, int]]:
        return detect_segments(pcm16, sample_rate, channels=channels, vad=self)

    def strip_silence(self, pcm16: bytes, sample_rate: int, channels: int = 1) -> bytes:
        return strip_silence(pcm16, sample_rate, channels=channels, vad=self)


def _align_pcm16(pcm16: bytes) -> bytes:
    if not pcm16:
        return b""
    aligned_length = len(pcm16) - (len(pcm16) % 2)
    return bytes(pcm16[:aligned_length])


def _pcm_values(pcm16: bytes) -> array:
    aligned = _align_pcm16(pcm16)
    values = array("h")
    values.frombytes(aligned)
    if sys.byteorder != "little":
        values.byteswap()
    return values


def _energy_db(samples: array) -> float:
    if not samples:
        return -120.0
    energy = sum(int(sample) * int(sample) for sample in samples) / float(len(samples))
    if energy <= 0.0:
        return -120.0
    rms = math.sqrt(energy)
    reference = 32768.0
    return 20.0 * math.log10(max(rms / reference, 1e-8))


def _merge_segments(segments: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not segments:
        return []
    ordered = sorted(segments)
    merged: list[list[int]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        current = merged[-1]
        if start <= current[1]:
            current[1] = max(current[1], end)
            continue
        merged.append([start, end])
    return [(start, end) for start, end in merged]


def detect_segments(
    pcm16: bytes,
    sample_rate: int,
    channels: int = 1,
    *,
    vad: EnergyVAD | None = None,
) -> list[tuple[int, int]]:
    config = vad or EnergyVAD()
    if sample_rate <= 0 or channels <= 0:
        return []

    values = _pcm_values(pcm16)
    total_values = len(values)
    if total_values == 0:
        return []

    frame_values = max(channels, int(sample_rate * max(1, config.frame_ms) / 1000) * channels)
    hop_values = max(channels, int(sample_rate * max(1, config.hop_ms) / 1000) * channels)
    min_speech_values = max(channels, int(sample_rate * max(1, config.min_speech_ms) / 1000) * channels)
    min_silence_values = max(channels, int(sample_rate * max(1, config.min_silence_ms) / 1000) * channels)
    padding_values = max(0, int(sample_rate * max(0, config.padding_ms) / 1000) * channels)

    if total_values < frame_values:
        return []

    segments: list[tuple[int, int]] = []
    active_start: int | None = None
    last_speech_end: int | None = None
    trailing_silence = 0

    for frame_start in range(0, total_values - frame_values + 1, hop_values):
        frame_end = min(total_values, frame_start + frame_values)
        frame_db = _energy_db(values[frame_start:frame_end])
        is_speech = frame_db >= float(config.energy_threshold_db)

        if is_speech:
            if active_start is None:
                active_start = max(0, frame_start - padding_values)
            last_speech_end = min(total_values, frame_end + padding_values)
            trailing_silence = 0
            continue

        if active_start is None or last_speech_end is None:
            continue

        trailing_silence += hop_values
        if trailing_silence >= min_silence_values:
            if last_speech_end - active_start >= min_speech_values:
                segments.append((active_start, last_speech_end))
            active_start = None
            last_speech_end = None
            trailing_silence = 0

    if active_start is not None and last_speech_end is not None:
        if last_speech_end - active_start >= min_speech_values:
            segments.append((active_start, last_speech_end))

    return _merge_segments(segments)


def strip_silence(
    pcm16: bytes,
    sample_rate: int,
    channels: int = 1,
    *,
    vad: EnergyVAD | None = None,
) -> bytes:
    aligned = _align_pcm16(pcm16)
    if not aligned:
        return b""

    segments = detect_segments(aligned, sample_rate, channels=channels, vad=vad)
    if not segments:
        return b""

    total_values = len(aligned) // 2
    if len(segments) == 1 and segments[0] == (0, total_values):
        return aligned

    return b"".join(aligned[start * 2 : end * 2] for start, end in segments)


__all__ = ["EnergyVAD", "detect_segments", "strip_silence"]
