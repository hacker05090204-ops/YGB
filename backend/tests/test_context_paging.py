from __future__ import annotations

from backend.runtime.context_paging import PagedContextBuffer
from scripts.device_manager import DeviceConfiguration


def _device_configuration(*, selected_device: str, total_memory_gb: float) -> DeviceConfiguration:
    return DeviceConfiguration(
        requested_device=selected_device,
        selected_device=selected_device,
        torch_device="cuda:0" if selected_device == "cuda" else selected_device,
        device_name=f"test-{selected_device}",
        accelerator=selected_device,
        distributed_backend="nccl" if selected_device == "cuda" else "gloo",
        mixed_precision="fp16" if selected_device == "cuda" else "fp32",
        amp_enabled=selected_device == "cuda",
        bf16_supported=False,
        pin_memory=selected_device == "cuda",
        non_blocking=selected_device == "cuda",
        supports_distributed_training=selected_device == "cuda",
        is_colab=False,
        torch_available=True,
        torch_version="test",
        cuda_available=selected_device == "cuda",
        mps_available=selected_device == "mps",
        gpu_count=1 if selected_device == "cuda" else 0,
        total_memory_gb=total_memory_gb,
        cuda_version="12.1" if selected_device == "cuda" else "",
        fallback_reason="",
    )


def test_paged_context_buffer_uses_disk_for_low_vram_and_trims_oldest(tmp_path):
    buffer = PagedContextBuffer(
        max_items=3,
        page_size=2,
        device_configuration=_device_configuration(selected_device="cuda", total_memory_gb=2.0),
        storage_root=tmp_path,
        namespace="phase17",
        context_id="voice-session",
    )

    for index in range(4):
        buffer.append({"speaker": "user", "text": f"turn-{index}"})

    assert buffer.mode == "disk"
    assert "cuda_low_vram" in buffer.mode_reason
    assert buffer.page_count == 2
    assert [item["text"] for item in buffer.items()] == ["turn-1", "turn-2", "turn-3"]
    assert buffer.storage_path is not None
    assert buffer.storage_path.exists()


def test_paged_context_buffer_cpu_fallback_stays_in_memory(tmp_path):
    buffer = PagedContextBuffer(
        max_items=4,
        page_size=2,
        device_configuration=_device_configuration(selected_device="cpu", total_memory_gb=0.0),
        storage_root=tmp_path,
        namespace="phase17",
        context_id="cpu-session",
    )

    buffer.append({"speaker": "user", "text": "hello world"})

    assert buffer.mode == "memory"
    assert buffer.mode_reason == "cpu_only_fallback_memory"
    assert buffer.storage_path is None
    assert buffer.tail(limit=1) == [{"speaker": "user", "text": "hello world"}]
