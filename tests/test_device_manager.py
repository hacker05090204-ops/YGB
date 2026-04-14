from __future__ import annotations

from types import SimpleNamespace

from scripts.colab_setup import build_colab_setup_summary
from scripts.device_manager import resolve_device_configuration


class _FakeCUDA:
    def __init__(
        self,
        *,
        available: bool,
        bf16_supported: bool = False,
        name: str = "Fake CUDA GPU",
        total_memory: int = 8 * 1024**3,
    ) -> None:
        self._available = available
        self._bf16_supported = bf16_supported
        self._name = name
        self._total_memory = total_memory

    def is_available(self) -> bool:
        return self._available

    def device_count(self) -> int:
        return 1 if self._available else 0

    def get_device_properties(self, index: int):
        if not self._available:
            raise RuntimeError("cuda unavailable")
        return SimpleNamespace(name=self._name, total_memory=self._total_memory)

    def get_device_name(self, index: int) -> str:
        if not self._available:
            raise RuntimeError("cuda unavailable")
        return self._name

    def is_bf16_supported(self) -> bool:
        return self._bf16_supported


class _FakeMPSBackend:
    def __init__(self, *, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


def _fake_torch(
    *,
    cuda_available: bool,
    mps_available: bool,
    bf16_supported: bool = False,
    cuda_version: str = "12.1",
):
    return SimpleNamespace(
        __version__="fake-torch",
        version=SimpleNamespace(cuda=cuda_version),
        cuda=_FakeCUDA(
            available=cuda_available,
            bf16_supported=bf16_supported,
        ),
        backends=SimpleNamespace(
            mps=_FakeMPSBackend(available=mps_available),
            cuda=SimpleNamespace(matmul=SimpleNamespace(allow_tf32=True)),
            cudnn=SimpleNamespace(allow_tf32=True),
        ),
        device=lambda name: f"device<{name}>",
    )


def test_resolve_device_configuration_uses_cuda_when_available(monkeypatch) -> None:
    monkeypatch.delenv("YGB_FORCE_CPU", raising=False)
    monkeypatch.delenv("YGB_COLAB", raising=False)

    config = resolve_device_configuration(
        torch_module=_fake_torch(cuda_available=True, mps_available=False, bf16_supported=True),
        configure_runtime=False,
    )

    assert config.selected_device == "cuda"
    assert config.torch_device == "cuda:0"
    assert config.distributed_backend == "nccl"
    assert config.amp_enabled is True
    assert config.mixed_precision == "bf16"
    assert config.pin_memory is True


def test_resolve_device_configuration_uses_mps_when_cuda_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("YGB_FORCE_CPU", raising=False)

    config = resolve_device_configuration(
        torch_module=_fake_torch(cuda_available=False, mps_available=True),
        configure_runtime=False,
    )

    assert config.selected_device == "mps"
    assert config.torch_device == "mps"
    assert config.distributed_backend == "gloo"
    assert config.amp_enabled is False


def test_force_cpu_override_wins_over_available_cuda(monkeypatch) -> None:
    monkeypatch.setenv("YGB_FORCE_CPU", "1")

    config = resolve_device_configuration(
        torch_module=_fake_torch(cuda_available=True, mps_available=False),
        configure_runtime=False,
    )

    assert config.selected_device == "cpu"
    assert "YGB_FORCE_CPU" in config.fallback_reason


def test_resolve_device_configuration_without_torch_falls_back_to_cpu(monkeypatch) -> None:
    monkeypatch.delenv("YGB_FORCE_CPU", raising=False)
    monkeypatch.delenv("YGB_COLAB", raising=False)

    config = resolve_device_configuration(torch_module=None, configure_runtime=False)

    assert config.selected_device == "cpu"
    assert config.torch_available is False
    assert config.mixed_precision == "fp32"


def test_build_colab_setup_summary_supports_cpu_only_runtime(monkeypatch) -> None:
    monkeypatch.setenv("YGB_COLAB", "1")

    summary = build_colab_setup_summary(
        validate_imports=False,
        torch_module=None,
    )

    assert summary["is_colab"] is True
    assert summary["device"]["selected_device"] == "cpu"
    assert "scripts/run_ybg_training_colab.py --dry-run" in summary["recommended_commands"]["dry_run_training"]
