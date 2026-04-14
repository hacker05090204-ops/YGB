"""
Phase49 test configuration.

Sets environment variables needed for test collection:
- YGB_ALLOW_MOCK_BACKEND: Allows g37_gpu_training_backend to import
  without real CUDA. Required for CI/test environments.
"""
import os

# Allow mock backend for testing — strictly test-safe, no production impact
os.environ.setdefault("YGB_ALLOW_MOCK_BACKEND", "1")

# Seed required auth secrets so Phase49 test collection remains self-contained.
# These defaults are pytest-only and do not affect production deployments.
os.environ.setdefault(
    "JWT_SECRET",
    "8f3c1e6b0d9247a18e4c5b6d7f8091a2c3e4f5a6b7c8d9e0f112233445566778",
)
os.environ.setdefault(
    "YGB_HMAC_SECRET",
    "91b4e7c2d5f8a103b6c9e2f4a7d8c1e3f5b7a9c2d4e6f8a0b1c3d5e7f9a2c4e6",
)
os.environ.setdefault(
    "YGB_VIDEO_JWT_SECRET",
    "7c2e5a8d1f4b9c0e3a6d8f1b4c7e9a2d5f8b0c3e6a9d1f4b7c0e2a5d8f1b4c6",
)
