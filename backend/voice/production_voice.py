from __future__ import annotations

import importlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from backend.assistant.query_router import (
    QueryRouter,
    ResearchSearchPipeline,
    ResearchStatus,
    VoiceMode,
)
from backend.runtime.context_paging import PagedContextBuffer
from backend.voice.intent_router import IntentRouter
from backend.voice.language_detector import LanguageDetector
from backend.voice.streaming_pipeline import (
    AudioFrame,
    SynthesisResult,
    Transcript,
    VoiceTurnResult,
)
from scripts.device_manager import DeviceConfiguration, resolve_device_configuration


logger = logging.getLogger(__name__)

_FASTER_WHISPER_ENV_VARS = ("YGB_FASTER_WHISPER_MODEL", "FASTER_WHISPER_MODEL_PATH")
_PIPER_BINARY_ENV_VARS = ("YGB_PIPER_BIN", "PIPER_BIN")
_PIPER_DEFAULT_MODEL_ENV_VARS = ("YGB_PIPER_MODEL", "PIPER_MODEL")
_PIPER_LANGUAGE_MODEL_ENV_VARS = {
    "en": ("YGB_PIPER_MODEL_EN",),
    "hi": ("YGB_PIPER_MODEL_HI",),
    "mr": ("YGB_PIPER_MODEL_MR",),
}


def _import_optional_dependency(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def _candidate_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return Path(normalized)


def _existing_path_from_env(*env_names: str) -> tuple[Path | None, str | None]:
    for env_name in env_names:
        candidate = _candidate_path(os.getenv(env_name))
        if candidate is None:
            continue
        return candidate, env_name
    return None, None


def _resolve_executable(
    explicit_path: str | Path | None = None,
    *,
    env_names: Iterable[str] = (),
    candidates: Iterable[str] = (),
) -> str | None:
    explicit_candidate = _candidate_path(explicit_path)
    if explicit_candidate is not None:
        if explicit_candidate.exists():
            return str(explicit_candidate)
        return None

    for env_name in env_names:
        env_value = str(os.getenv(env_name, "")).strip()
        if not env_value:
            continue
        env_path = _candidate_path(env_value)
        if env_path is not None and env_path.exists():
            return str(env_path)
        resolved = shutil.which(env_value)
        if resolved:
            return resolved

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _write_wav_file(path: Path, pcm16: bytes, sample_rate: int, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(max(1, int(channels)))
        wav_file.setsampwidth(2)
        wav_file.setframerate(max(1, int(sample_rate)))
        wav_file.writeframes(pcm16)


def _normalize_audio_source(audio: AudioFrame | bytes | str | Path) -> tuple[str, Path | None]:
    if isinstance(audio, AudioFrame):
        temp_path = Path(tempfile.mkstemp(suffix=".wav")[1])
        _write_wav_file(temp_path, audio.pcm16, audio.sample_rate, audio.channels)
        return str(temp_path), temp_path

    if isinstance(audio, (bytes, bytearray)):
        temp_path = Path(tempfile.mkstemp(suffix=".wav")[1])
        payload = bytes(audio)
        if payload[:4] == b"RIFF":
            temp_path.write_bytes(payload)
        else:
            _write_wav_file(temp_path, payload, 16000, 1)
        return str(temp_path), temp_path

    if isinstance(audio, (str, Path)):
        candidate = Path(audio)
        if not candidate.exists():
            raise FileNotFoundError(f"Audio source not found: {candidate}")
        return str(candidate), None

    raise TypeError(f"Unsupported audio source: {type(audio).__name__}")


@dataclass
class ConversationTurn:
    speaker: str
    text: str
    language: str = "en"


class ConversationPager:
    def __init__(
        self,
        max_turns: int = 20,
        page_size: int = 6,
        *,
        device_configuration: Any | None = None,
        storage_root: str | Path | None = None,
        namespace: str = "production_voice",
    ) -> None:
        self.max_turns = max(1, int(max_turns))
        self.page_size = max(1, int(page_size))
        self._store = PagedContextBuffer(
            max_items=self.max_turns,
            page_size=self.page_size,
            device_configuration=device_configuration,
            storage_root=storage_root,
            namespace=namespace,
        )

    def append(self, speaker: str, text: str, language: str = "en") -> None:
        normalized = str(text or "").strip()
        if not normalized:
            return
        self._store.append(
            asdict(
                ConversationTurn(
                    speaker=str(speaker or "assistant"),
                    text=normalized,
                    language=str(language or "en"),
                )
            )
        )

    @property
    def turn_count(self) -> int:
        return self._store.item_count

    @property
    def page_count(self) -> int:
        return self._store.page_count

    @property
    def current_page(self) -> int:
        return self.page_count

    @property
    def storage_mode(self) -> str:
        return self._store.mode

    @property
    def storage_reason(self) -> str:
        return self._store.mode_reason

    @property
    def storage_path(self) -> Path | None:
        return self._store.storage_path

    def status(self) -> dict[str, Any]:
        return self._store.status()

    def render_page(self) -> str:
        recent = [
            ConversationTurn(
                speaker=str(item.get("speaker", "assistant") or "assistant"),
                text=str(item.get("text", "") or "").strip(),
                language=str(item.get("language", "en") or "en"),
            )
            for item in self._store.tail(limit=self.page_size)
            if str(item.get("text", "") or "").strip()
        ]
        if not recent:
            return "[page 1/1]"
        body = "\n".join(f"{turn.speaker}: {turn.text}" for turn in recent)
        return f"[page {self.current_page}/{self.page_count}]\n{body}"


@dataclass
class ProductionVoiceTurnResult(VoiceTurnResult):
    route_mode: str = ""
    intent_reason: str = ""
    route_reason: str = ""
    warnings: tuple[str, ...] = ()


class FasterWhisperSTT:
    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        preferred_device: str | None = None,
        compute_type: str | None = None,
        device_configuration: DeviceConfiguration | None = None,
    ) -> None:
        self.device_configuration = device_configuration or resolve_device_configuration(
            preferred_device,
            configure_runtime=False,
        )
        self.runtime_device = "cuda" if self.device_configuration.selected_device == "cuda" else "cpu"
        self.compute_type = compute_type or (
            "float16" if self.runtime_device == "cuda" else "int8"
        )
        self.dependency_available = False
        self.model_available = False
        self.available = False
        self._warnings: list[str] = []
        self._model_factory: Any | None = None
        self._model: Any | None = None
        self._module: Any | None = None

        if self.device_configuration.selected_device not in {"cuda", "cpu"}:
            self._record_warning(
                f"FasterWhisperSTT does not support {self.device_configuration.selected_device}; using cpu"
            )

        configured_model = _candidate_path(model_path)
        model_env_name = None
        if configured_model is None:
            configured_model, model_env_name = _existing_path_from_env(*_FASTER_WHISPER_ENV_VARS)
        self.model_path = configured_model

        module = _import_optional_dependency("faster_whisper")
        if module is None:
            self._record_warning("FasterWhisperSTT unavailable: faster-whisper dependency is not installed")
            return

        self._module = module
        self.dependency_available = True
        model_factory = getattr(module, "WhisperModel", None)
        if not callable(model_factory):
            self._record_warning(
                "FasterWhisperSTT unavailable: faster_whisper.WhisperModel could not be resolved"
            )
            return
        self._model_factory = model_factory

        if self.model_path is None:
            self._record_warning(
                "FasterWhisperSTT unavailable: no local faster-whisper model path configured"
            )
            return

        if not self.model_path.exists():
            source = f" from {model_env_name}" if model_env_name else ""
            self._record_warning(
                f"FasterWhisperSTT unavailable: configured model path{source} does not exist ({self.model_path})"
            )
            return

        self.model_available = True
        self.available = True

    @property
    def warning(self) -> str:
        return "; ".join(self._warnings)

    def _record_warning(self, message: str) -> None:
        self._warnings.append(message)
        logger.warning(message)

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        if not self.available or self._model_factory is None or self.model_path is None:
            raise RuntimeError(self.warning or "FasterWhisperSTT unavailable")
        try:
            self._model = self._model_factory(
                str(self.model_path),
                device=self.runtime_device,
                compute_type=self.compute_type,
            )
            return self._model
        except Exception as exc:
            self.available = False
            message = (
                f"FasterWhisperSTT failed to load local model {self.model_path}: "
                f"{type(exc).__name__}: {exc}"
            )
            self._record_warning(message)
            raise RuntimeError(message) from exc
    def transcribe(
        self,
        audio: AudioFrame | bytes | str | Path,
        *,
        language_hint: str | None = None,
        beam_size: int = 1,
    ) -> Transcript:
        start = time.perf_counter()
        model = self._ensure_model()
        audio_source, temporary_path = _normalize_audio_source(audio)
        try:
            segments, info = model.transcribe(
                audio_source,
                language=language_hint,
                beam_size=max(1, int(beam_size)),
                vad_filter=True,
            )
            text = " ".join(
                str(getattr(segment, "text", "")).strip()
                for segment in segments
                if str(getattr(segment, "text", "")).strip()
            ).strip()
            language = str(getattr(info, "language", "") or language_hint or "en")
            confidence = float(getattr(info, "language_probability", 0.0) or 0.0)
            return Transcript(
                text=text,
                language=language,
                confidence=confidence,
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:
            message = f"FasterWhisperSTT transcription failed: {type(exc).__name__}: {exc}"
            logger.warning(message)
            raise RuntimeError(message) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "dependency_available": self.dependency_available,
            "model_available": self.model_available,
            "device": self.runtime_device,
            "compute_type": self.compute_type,
            "model_path": str(self.model_path) if self.model_path is not None else None,
            "warning": self.warning,
        }


FastWhisperSTT = FasterWhisperSTT


class PiperTTS:
    def __init__(
        self,
        voice_model_path: str | Path | None = None,
        *,
        language_model_paths: Mapping[str, str | Path] | None = None,
        binary_path: str | Path | None = None,
        speaker: int | None = None,
        length_scale: float | None = None,
        preferred_device: str | None = None,
        device_configuration: DeviceConfiguration | None = None,
    ) -> None:
        self.device_configuration = device_configuration or resolve_device_configuration(
            preferred_device,
            configure_runtime=False,
        )
        self.execution_device = "cpu"
        self.speaker = speaker
        self.length_scale = length_scale
        self.dependency_available = False
        self.model_available = False
        self.available = False
        self._warnings: list[str] = []

        self.binary_path = _resolve_executable(
            binary_path,
            env_names=_PIPER_BINARY_ENV_VARS,
            candidates=("piper", "piper.exe"),
        )
        if self.binary_path is None:
            self._record_warning("PiperTTS unavailable: Piper executable could not be found")
        else:
            self.dependency_available = True

        self.voice_models: dict[str, Path] = {}
        self._load_configured_models(voice_model_path, language_model_paths)

        self.model_available = bool(self.voice_models)
        self.available = self.dependency_available and self.model_available
        if self.dependency_available and not self.model_available:
            self._record_warning("PiperTTS unavailable: no local Piper voice model path configured")

    @property
    def warning(self) -> str:
        return "; ".join(self._warnings)

    def _record_warning(self, message: str) -> None:
        self._warnings.append(message)
        logger.warning(message)

    def _register_model(self, key: str, candidate: str | Path | None, source: str) -> None:
        path = _candidate_path(candidate)
        if path is None:
            return
        if path.exists():
            self.voice_models[key] = path
            return
        self._record_warning(f"PiperTTS ignored missing model path from {source}: {path}")

    def _load_configured_models(
        self,
        voice_model_path: str | Path | None,
        language_model_paths: Mapping[str, str | Path] | None,
    ) -> None:
        self._register_model("default", voice_model_path, "voice_model_path")

        default_env_path, default_env_name = _existing_path_from_env(*_PIPER_DEFAULT_MODEL_ENV_VARS)
        if default_env_path is not None:
            self._register_model("default", default_env_path, default_env_name or "env")

        for language, env_names in _PIPER_LANGUAGE_MODEL_ENV_VARS.items():
            env_path, env_name = _existing_path_from_env(*env_names)
            if env_path is not None:
                self._register_model(language, env_path, env_name or language)

        if language_model_paths:
            for language, path in language_model_paths.items():
                self._register_model(str(language).lower(), path, f"language_model_paths[{language!r}]")

    def _resolve_voice_model(self, language: str | None) -> Path | None:
        normalized = str(language or "").strip().lower()
        return (
            self.voice_models.get(normalized)
            or self.voice_models.get("default")
            or next(iter(self.voice_models.values()), None)
        )

    def synthesize(self, text: str, language: str = "en") -> SynthesisResult:
        start = time.perf_counter()
        if not self.available or self.binary_path is None:
            raise RuntimeError(self.warning or "PiperTTS unavailable")

        voice_model = self._resolve_voice_model(language)
        if voice_model is None:
            raise RuntimeError(f"PiperTTS unavailable: no voice model configured for language '{language}'")

        output_path = Path(tempfile.mkstemp(suffix=".wav")[1])
        command = [self.binary_path, "--model", str(voice_model), "--output_file", str(output_path)]
        if self.speaker is not None:
            command.extend(["--speaker", str(int(self.speaker))])
        if self.length_scale is not None:
            command.extend(["--length_scale", str(float(self.length_scale))])

        try:
            completed = subprocess.run(
                command,
                input=str(text).encode("utf-8"),
                capture_output=True,
                check=False,
                timeout=30,
            )
            if completed.returncode != 0:
                stderr = completed.stderr.decode("utf-8", errors="ignore").strip()
                raise RuntimeError(stderr or f"Piper exited with code {completed.returncode}")
            if not output_path.exists():
                raise RuntimeError("Piper did not create the requested output file")
            audio_bytes = output_path.read_bytes()
            return SynthesisResult(
                audio=audio_bytes,
                provider=f"piper:{language}",
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:
            message = f"PiperTTS synthesis failed: {type(exc).__name__}: {exc}"
            logger.warning(message)
            raise RuntimeError(message) from exc
        finally:
            output_path.unlink(missing_ok=True)

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "dependency_available": self.dependency_available,
            "model_available": self.model_available,
            "binary_path": self.binary_path,
            "voice_models": {key: str(value) for key, value in self.voice_models.items()},
            "device": self.execution_device,
            "warning": self.warning,
        }


class ProductionVoicePipeline:
    def __init__(
        self,
        *,
        stt: FasterWhisperSTT | Any | None = None,
        tts: PiperTTS | Any | None = None,
        intent_router: IntentRouter | None = None,
        query_router: QueryRouter | None = None,
        research_pipeline: ResearchSearchPipeline | Any | None = None,
        language_detector: LanguageDetector | None = None,
        max_context_turns: int = 20,
        context_page_size: int = 6,
        preferred_device: str | None = None,
        device_configuration: DeviceConfiguration | None = None,
        context_storage_root: str | Path | None = None,
    ) -> None:
        self.device_configuration = device_configuration or resolve_device_configuration(
            preferred_device,
            configure_runtime=False,
        )
        shared_device = self.device_configuration
        self.stt = stt or FasterWhisperSTT(device_configuration=shared_device)
        self.tts = tts or PiperTTS(device_configuration=shared_device)
        self.intent_router = intent_router or IntentRouter()
        self.query_router = query_router or QueryRouter()
        self.research_pipeline = research_pipeline or ResearchSearchPipeline()
        self.language_detector = language_detector or LanguageDetector()
        self.context = ConversationPager(
            max_turns=max_context_turns,
            page_size=context_page_size,
            device_configuration=shared_device,
            storage_root=context_storage_root,
        )
        self.initialized = True

    def _base_metrics(self) -> dict[str, float]:
        return {
            "stt_available": 1.0 if bool(getattr(self.stt, "available", False)) else 0.0,
            "tts_available": 1.0 if bool(getattr(self.tts, "available", False)) else 0.0,
            "context_turns": float(self.context.turn_count),
            "context_pages": float(self.context.page_count),
            "context_disk_mode": 1.0 if self.context.storage_mode == "disk" else 0.0,
        }

    def _security_response(self, transcript: Transcript, route_reason: str) -> str:
        return (
            "Security-mode routing selected. "
            f"{route_reason}. Request retained for explicit downstream handling: {transcript.text}"
        )

    def status(self) -> dict[str, Any]:
        warnings = [warning for warning in [getattr(self.stt, "warning", ""), getattr(self.tts, "warning", "")] if warning]
        return {
            "initialized": self.initialized,
            "degraded": not (
                bool(getattr(self.stt, "available", False))
                and bool(getattr(self.tts, "available", False))
            ),
            "device": self.device_configuration.selected_device,
            "stt_available": bool(getattr(self.stt, "available", False)),
            "tts_available": bool(getattr(self.tts, "available", False)),
            "routing_available": True,
            "context_storage_mode": self.context.storage_mode,
            "context_storage_reason": self.context.storage_reason,
            "context_storage_path": str(self.context.storage_path) if self.context.storage_path is not None else None,
            "context_turns": self.context.turn_count,
            "context_pages": self.context.page_count,
            "warnings": warnings,
        }

    def process_audio(
        self,
        audio: AudioFrame | bytes | str | Path,
        *,
        synthesize_response: bool = True,
        language_hint: str | None = None,
    ) -> ProductionVoiceTurnResult:
        warnings: list[str] = []
        metrics = self._base_metrics()

        try:
            transcript = self.stt.transcribe(audio, language_hint=language_hint)
        except Exception as exc:
            message = f"STT unavailable: {exc}"
            warnings.append(message)
            logger.warning(message)
            return ProductionVoiceTurnResult(
                status="error",
                response_text=message,
                conversation_context=self.context.render_page(),
                metrics=metrics,
                route_mode="ERROR",
                route_reason=message,
                warnings=tuple(warnings),
            )

        if not transcript.text.strip():
            message = "STT produced an empty transcript"
            warnings.append(message)
            return ProductionVoiceTurnResult(
                status="error",
                transcript=transcript,
                response_text=message,
                conversation_context=self.context.render_page(),
                metrics={**metrics, "stt_latency_ms": transcript.latency_ms},
                route_mode="ERROR",
                route_reason=message,
                warnings=tuple(warnings),
            )

        detected_language = self.language_detector.detect(transcript.text)
        transcript.language = str(detected_language.get("language", transcript.language or "en"))
        self.context.append("user", transcript.text, transcript.language)

        intent = self.intent_router.route(transcript.text)
        metrics.update(
            {
                "stt_latency_ms": float(transcript.latency_ms),
                "intent_risk_score": float(getattr(intent, "risk_score", 0.0) or 0.0),
                "context_turns": float(self.context.turn_count),
                "context_pages": float(self.context.page_count),
            }
        )

        route_mode = ""
        route_reason = ""
        response_text = ""
        status = "ok"

        if not intent.allowed and str(getattr(intent, "mode", "")) != "ambiguous":
            status = "blocked"
            route_mode = "BLOCKED"
            route_reason = intent.reason
            response_text = intent.reason
        else:
            if not intent.allowed:
                ambiguity_message = (
                    "IntentRouter returned ambiguous classification; "
                    "continuing with query routing for explicit resolution"
                )
                warnings.append(ambiguity_message)
                logger.warning(ambiguity_message)
            decision = self.query_router.classify(transcript.text)
            route_mode = decision.mode.value
            route_reason = decision.reason
            metrics["routing_confidence"] = float(decision.confidence)

            if decision.mode == VoiceMode.RESEARCH:
                research_result = self.research_pipeline.search(transcript.text)
                response_text = str(research_result.summary or "No result available")
                metrics["research_elapsed_ms"] = float(getattr(research_result, "elapsed_ms", 0.0) or 0.0)
                query_result = getattr(research_result, "query_result", None)
                if query_result is not None:
                    metrics["grounding_confidence"] = float(
                        getattr(query_result, "grounding_confidence", 0.0) or 0.0
                    )
                if research_result.status == ResearchStatus.SUCCESS:
                    status = "ok"
                elif research_result.status == ResearchStatus.BLOCKED:
                    status = "blocked"
                elif research_result.status == ResearchStatus.NO_RESULTS:
                    status = "no_result"
                else:
                    status = "error"
            elif decision.mode == VoiceMode.SECURITY:
                status = "routed_security"
                response_text = self._security_response(transcript, decision.reason)
            else:
                status = "clarification"
                response_text = decision.reason

        self.context.append("assistant", response_text, transcript.language)
        metrics["context_turns"] = float(self.context.turn_count)
        metrics["context_pages"] = float(self.context.page_count)

        synthesis: SynthesisResult | None = None
        if synthesize_response and response_text:
            try:
                synthesis = self.tts.synthesize(response_text, transcript.language)
                metrics["tts_latency_ms"] = float(synthesis.latency_ms)
            except Exception as exc:
                message = f"TTS unavailable: {exc}"
                warnings.append(message)
                logger.warning(message)
                if status == "ok":
                    status = "degraded"

        return ProductionVoiceTurnResult(
            status=status,
            transcript=transcript,
            response_text=response_text,
            synthesis=synthesis,
            conversation_context=self.context.render_page(),
            metrics=metrics,
            route_mode=route_mode,
            intent_reason=intent.reason,
            route_reason=route_reason,
            warnings=tuple(warnings),
        )


def smoke_probe() -> dict[str, Any]:
    stt = FasterWhisperSTT()
    tts = PiperTTS()
    pipeline = ProductionVoicePipeline(stt=stt, tts=tts)
    return {
        "stt": stt.status(),
        "tts": tts.status(),
        "pipeline": pipeline.status(),
    }


def main() -> None:
    print(json.dumps(smoke_probe(), indent=2, sort_keys=True))


__all__ = [
    "AudioFrame",
    "ConversationPager",
    "FastWhisperSTT",
    "FasterWhisperSTT",
    "PiperTTS",
    "ProductionVoicePipeline",
    "ProductionVoiceTurnResult",
    "SynthesisResult",
    "Transcript",
    "smoke_probe",
]


if __name__ == "__main__":
    main()
