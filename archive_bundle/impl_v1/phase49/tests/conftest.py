"""
Phase49 test configuration.

Sets environment variables needed for test collection:
- YGB_ALLOW_MOCK_BACKEND: Allows g37_gpu_training_backend to import
  without real CUDA. Required for CI/test environments.
"""
import os

# Allow mock backend for testing — strictly test-safe, no production impact
os.environ.setdefault("YGB_ALLOW_MOCK_BACKEND", "1")
