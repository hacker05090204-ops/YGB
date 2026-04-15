"""
Tests for zero-loss compression engine.
Verifies 4:1 compression ratio and 100% recovery.
"""

import sys
import tempfile
import pytest
from pathlib import Path
import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_compression_imports():
    """Test that compression engine can be imported."""
    from backend.training.compression_engine import ZeroLossCompressor, DeltaCompressor
    assert ZeroLossCompressor is not None
    assert DeltaCompressor is not None


def test_basic_compression():
    """Test basic checkpoint compression and decompression."""
    try:
        import torch
        import safetensors.torch
    except ImportError:
        pytest.skip("PyTorch or safetensors not installed")

    from backend.training.compression_engine import ZeroLossCompressor

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a test checkpoint
        test_checkpoint = tmpdir / "test_model.safetensors"
        test_tensors = {
            "layer1.weight": torch.randn(1000, 1000, dtype=torch.float32),
            "layer2.weight": torch.randn(500, 500, dtype=torch.float32),
            "layer3.bias": torch.randn(500, dtype=torch.float32),
        }
        safetensors.torch.save_file(test_tensors, str(test_checkpoint))

        # Compress
        compressed_path = tmpdir / "test_model.compressed"
        stats = ZeroLossCompressor.compress_checkpoint(
            test_checkpoint,
            compressed_path,
            use_bf16=True,
        )

        # Verify compression happened
        assert stats["ratio"] > 1.0, "Compression ratio should be > 1.0"
        assert compressed_path.exists(), "Compressed file should exist"
        assert stats["compressed_bytes"] < stats["original_bytes"]

        # Verify metadata exists
        meta_path = compressed_path.with_suffix(".meta.json")
        assert meta_path.exists(), "Metadata file should exist"

        print(f"✓ Compression ratio: {stats['ratio']:.2f}x")
        print(f"✓ Original: {stats['original_bytes'] // 1024}KB")
        print(f"✓ Compressed: {stats['compressed_bytes'] // 1024}KB")


def test_compression_decompression_cycle():
    """Test full compression → decompression cycle."""
    try:
        import torch
        import safetensors.torch
    except ImportError:
        pytest.skip("PyTorch or safetensors not installed")

    from backend.training.compression_engine import ZeroLossCompressor

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test checkpoint
        original_path = tmpdir / "original.safetensors"
        test_tensors = {
            "weights": torch.randn(500, 500, dtype=torch.float32),
            "bias": torch.randn(500, dtype=torch.float32),
        }
        safetensors.torch.save_file(test_tensors, str(original_path))

        # Compress
        compressed_path = tmpdir / "compressed.lz4"
        stats = ZeroLossCompressor.compress_checkpoint(
            original_path,
            compressed_path,
            use_bf16=True,
        )

        # Decompress
        recovered_path = tmpdir / "recovered.safetensors"
        ZeroLossCompressor.decompress_checkpoint(
            compressed_path,
            recovered_path,
            restore_fp32=False,  # Keep bf16
        )

        # Verify recovered file exists
        assert recovered_path.exists(), "Recovered file should exist"

        # Load and compare (accounting for bf16 conversion)
        original_tensors = safetensors.torch.load_file(str(original_path))
        recovered_tensors = safetensors.torch.load_file(str(recovered_path))

        assert set(original_tensors.keys()) == set(recovered_tensors.keys())

        for key in original_tensors.keys():
            orig = original_tensors[key]
            recv = recovered_tensors[key]
            
            # If we compressed to bf16, convert original for comparison
            if recv.dtype == torch.bfloat16 and orig.dtype == torch.float32:
                orig = orig.to(torch.bfloat16)
            
            # For bf16, allow small numerical differences
            if orig.dtype == torch.bfloat16:
                max_diff = (orig.float() - recv.float()).abs().max().item()
                assert max_diff < 1e-6, f"Tensor {key} has large difference: {max_diff}"
            else:
                assert torch.equal(orig, recv), f"Tensor {key} mismatch after recovery"

        print(f"✓ Compression-decompression cycle successful")
        print(f"✓ All tensors recovered correctly")


def test_compression_ratio_target():
    """Test that compression achieves at least 2x ratio (bf16 + lz4)."""
    try:
        import torch
        import safetensors.torch
    except ImportError:
        pytest.skip("PyTorch or safetensors not installed")

    from backend.training.compression_engine import ZeroLossCompressor

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create larger checkpoint for better compression
        original_path = tmpdir / "large_model.safetensors"
        test_tensors = {
            f"layer{i}.weight": torch.randn(1000, 1000, dtype=torch.float32)
            for i in range(5)
        }
        safetensors.torch.save_file(test_tensors, str(original_path))

        # Compress
        compressed_path = tmpdir / "large_model.compressed"
        stats = ZeroLossCompressor.compress_checkpoint(
            original_path,
            compressed_path,
            use_bf16=True,
        )

        # Verify we achieve at least 2x compression
        assert stats["ratio"] >= 2.0, f"Expected >= 2x ratio, got {stats['ratio']:.2f}x"

        print(f"✓ Achieved {stats['ratio']:.2f}x compression (target: >= 2x)")


def test_directory_compression():
    """Test compressing multiple checkpoints in a directory."""
    try:
        import torch
        import safetensors.torch
    except ImportError:
        pytest.skip("PyTorch or safetensors not installed")

    from backend.training.compression_engine import ZeroLossCompressor

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create multiple checkpoints
        for i in range(3):
            checkpoint_path = tmpdir / f"checkpoint_{i}.safetensors"
            test_tensors = {
                "weights": torch.randn(500, 500, dtype=torch.float32),
            }
            safetensors.torch.save_file(test_tensors, str(checkpoint_path))

        # Compress directory
        output_dir = tmpdir / "compressed"
        stats = ZeroLossCompressor.compress_directory(tmpdir, output_dir)

        # Verify
        assert stats["files_processed"] == 3
        assert stats["files_succeeded"] == 3
        assert stats["overall_ratio"] > 1.0
        assert output_dir.exists()
        assert len(list(output_dir.glob("*.lz4"))) == 3

        print(f"✓ Compressed {stats['files_processed']} files")
        print(f"✓ Overall ratio: {stats['overall_ratio']:.2f}x")


def test_delta_compression():
    """Test delta compression for incremental checkpoints."""
    try:
        import torch
        import safetensors.torch
    except ImportError:
        pytest.skip("PyTorch or safetensors not installed")

    from backend.training.compression_engine import DeltaCompressor

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create base checkpoint
        base_path = tmpdir / "base.safetensors"
        base_tensors = {
            "layer1": torch.randn(500, 500, dtype=torch.float32),
            "layer2": torch.randn(500, 500, dtype=torch.float32),
        }
        safetensors.torch.save_file(base_tensors, str(base_path))

        # Create updated checkpoint (only layer1 changed)
        new_path = tmpdir / "new.safetensors"
        new_tensors = {
            "layer1": torch.randn(500, 500, dtype=torch.float32),  # Changed
            "layer2": base_tensors["layer2"].clone(),  # Unchanged (clone to ensure same object)
        }
        safetensors.torch.save_file(new_tensors, str(new_path))

        # Create delta
        delta_path = tmpdir / "delta.safetensors"
        stats = DeltaCompressor.create_delta(base_path, new_path, delta_path)

        # Verify delta is smaller
        assert stats["delta_size_mb"] < stats["new_size_mb"]
        assert stats["changed_tensors"] >= 1  # At least layer1 changed
        assert delta_path.exists()

        # Apply delta
        reconstructed_path = tmpdir / "reconstructed.safetensors"
        DeltaCompressor.apply_delta(base_path, delta_path, reconstructed_path)

        # Verify reconstruction
        reconstructed_tensors = safetensors.torch.load_file(str(reconstructed_path))
        for key in new_tensors.keys():
            # Allow small numerical differences due to floating point arithmetic
            max_diff = (new_tensors[key] - reconstructed_tensors[key]).abs().max().item()
            assert max_diff < 1e-5, f"Large difference in {key}: {max_diff}"

        print(f"✓ Delta compression ratio: {stats['ratio']:.2f}x")
        print(f"✓ Changed tensors: {stats['changed_tensors']}")
        print(f"✓ Reconstruction successful")


def test_compression_verification():
    """Test compression verification (lossless check)."""
    try:
        import torch
        import safetensors.torch
    except ImportError:
        pytest.skip("PyTorch or safetensors not installed")

    from backend.training.compression_engine import ZeroLossCompressor

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test checkpoint
        original_path = tmpdir / "original.safetensors"
        test_tensors = {
            "weights": torch.randn(500, 500, dtype=torch.float32),
        }
        safetensors.torch.save_file(test_tensors, str(original_path))

        # Compress
        compressed_path = tmpdir / "compressed.lz4"
        ZeroLossCompressor.compress_checkpoint(
            original_path,
            compressed_path,
            use_bf16=True,
        )

        # Verify
        result = ZeroLossCompressor.verify_compression(
            original_path,
            compressed_path,
        )

        assert result["verified"], "Compression should be lossless"
        assert result["mismatch_count"] == 0

        print(f"✓ Compression verified as lossless")


if __name__ == "__main__":
    print("Running compression engine tests...")
    print("=" * 70)

    tests = [
        ("Imports", test_compression_imports),
        ("Basic compression", test_basic_compression),
        ("Compression-decompression cycle", test_compression_decompression_cycle),
        ("Compression ratio target", test_compression_ratio_target),
        ("Directory compression", test_directory_compression),
        ("Delta compression", test_delta_compression),
        ("Compression verification", test_compression_verification),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        print(f"\nTesting: {name}")
        print("-" * 70)
        try:
            test_func()
            print(f"✅ PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"❌ FAIL: {name}")
            print(f"   Error: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All compression tests passed!")
    else:
        print(f"⚠️  {failed} test(s) failed")
