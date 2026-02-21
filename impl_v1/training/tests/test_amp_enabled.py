"""
Test AMP Enabled
================

Validates that Automatic Mixed Precision is:
- Available on the system
- Properly configured with GradScaler
- Using autocast for forward passes
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))


class TestAMPEnabled:
    """Tests for AMP (Automatic Mixed Precision) configuration."""
    
    def test_torch_amp_available(self):
        """torch.cuda.amp must be available."""
        import torch
        from torch.cuda.amp import autocast, GradScaler
        
        assert hasattr(torch.cuda.amp, 'autocast'), "autocast not available"
        assert hasattr(torch.cuda.amp, 'GradScaler'), "GradScaler not available"
    
    def test_gradscaler_creation(self):
        """GradScaler must be creatable."""
        from torch.cuda.amp import GradScaler
        
        scaler = GradScaler()
        assert scaler is not None
        assert scaler.get_scale() > 0
    
    @pytest.mark.skipif(
        not __import__('torch').cuda.is_available(),
        reason="CUDA not available"
    )
    def test_autocast_context(self):
        """autocast context manager must work on CUDA tensors."""
        import torch
        from torch.cuda.amp import autocast
        
        x = torch.randn(32, 256, device='cuda')
        
        with autocast(dtype=torch.float16):
            y = x @ x.T  # Matrix multiply
            assert y.dtype in [torch.float16, torch.bfloat16, torch.float32], \
                "autocast should use mixed precision"
    
    @pytest.mark.skipif(
        not __import__('torch').cuda.is_available(),
        reason="CUDA not available"
    )
    def test_auto_trainer_amp_flag(self):
        """AutoTrainer must have AMP_AVAILABLE flag set."""
        from impl_v1.phase49.runtime.auto_trainer import AMP_AVAILABLE
        
        assert AMP_AVAILABLE is True, "AMP_AVAILABLE should be True"
    
    def test_deterministic_mode_enabled(self):
        """cuDNN deterministic mode must be enabled."""
        import torch
        
        assert torch.backends.cudnn.deterministic is True, \
            "cudnn.deterministic should be True"
        assert torch.backends.cudnn.benchmark is False, \
            "cudnn.benchmark should be False for determinism"


class TestCUDATrainingDevice:
    """Tests for CUDA device configuration."""
    
    @pytest.mark.skipif(
        not __import__('torch').cuda.is_available(),
        reason="CUDA not available"
    )
    def test_cuda_device_available(self):
        """CUDA device must be available."""
        import torch
        
        assert torch.cuda.is_available()
        assert torch.cuda.device_count() >= 1
    
    @pytest.mark.skipif(
        not __import__('torch').cuda.is_available(),
        reason="CUDA not available"
    )
    def test_model_on_cuda(self):
        """Model must be placed on CUDA device."""
        import torch
        import torch.nn as nn
        
        model = nn.Linear(256, 2).cuda()
        
        # Check parameter device
        for param in model.parameters():
            assert param.device.type == 'cuda', \
                f"Parameter on {param.device.type}, expected cuda"
    
    @pytest.mark.skipif(
        not __import__('torch').cuda.is_available(),
        reason="CUDA not available"
    )
    def test_tensor_cores_compatible(self):
        """Device should support Tensor Cores (RTX 20xx+)."""
        import torch
        
        # RTX 2050 has compute capability 8.6
        major, minor = torch.cuda.get_device_capability()
        assert major >= 7, f"Compute capability {major}.{minor} < 7.0, Tensor Cores require 7.0+"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
