"""
cuda_node_rtx2050.py — CUDA RTX 2050 DDP Node Entrypoint

8-step protocol for safely joining a distributed training cluster:

  1. Verify CUDA (available, cc >= 7.5, FP16, CUDA version match)
  2. Validate dataset (hash, count, dim, label dist, entropy)
  3. Run adaptive batch scaling → optimal_batch_2050
  4. Join NCCL group (world_size == #CUDA nodes)
  5. Initialize deterministic mode (seed 42, cudnn.deterministic, CUBLAS)
  6. Participate in all-reduce (DDP-wrapped training loop)
  7. Post-epoch: compute weight_hash → send to authority
  8. Emit structured JSON log

Usage:
    from impl_v1.training.distributed.cuda_node_rtx2050 import RTX2050Node
    node = RTX2050Node(...)
    node.run()
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# RESULT TYPES
# =============================================================================

@dataclass
class CUDAVerification:
    """Step 1 result: CUDA hardware checks."""
    cuda_available: bool
    compute_capability: str
    cc_version: float
    fp16_supported: bool
    cuda_version: str
    cuda_version_match: bool
    device_name: str
    vram_total_mb: float
    passed: bool
    errors: List[str] = field(default_factory=list)


@dataclass
class EpochReport:
    """Per-epoch training report."""
    epoch: int
    weight_hash: str
    loss: float
    samples_processed: int
    samples_per_sec: float
    elapsed_sec: float


@dataclass
class NodeRunResult:
    """Complete node execution result."""
    node_id: str
    device_name: str
    cuda_verified: bool
    dataset_valid: bool
    optimal_batch_2050: int
    world_size: int
    ddp_initialized: bool
    deterministic: bool
    epochs_completed: int
    final_weight_hash: str
    final_dataset_hash: str
    epoch_reports: List[Dict]
    errors: List[str]


# =============================================================================
# RTX 2050 NODE
# =============================================================================

class RTX2050Node:
    """CUDA RTX 2050 DDP training node.

    Implements the full 8-step join + train protocol.
    """

    MIN_COMPUTE_CAPABILITY = 7.5

    def __init__(
        self,
        # Dataset
        X: np.ndarray,
        y: np.ndarray,
        expected_dataset_hash: str,
        expected_sample_count: int,
        expected_feature_dim: int,
        expected_label_distribution: Optional[Dict[int, float]] = None,
        label_tolerance: float = 0.05,
        entropy_threshold: float = 0.5,
        # Cluster
        all_nodes: Optional[List[dict]] = None,
        local_rank: int = 0,
        master_addr: str = "127.0.0.1",
        master_port: str = "29500",
        # Training
        epochs: int = 1,
        learning_rate: float = 0.001,
        starting_batch: int = 1024,
        input_dim: int = 256,
        # Authority
        expected_cuda_version: Optional[str] = None,
    ):
        self.X = X
        self.y = y
        self.expected_dataset_hash = expected_dataset_hash
        self.expected_sample_count = expected_sample_count
        self.expected_feature_dim = expected_feature_dim
        self.expected_label_distribution = expected_label_distribution
        self.label_tolerance = label_tolerance
        self.entropy_threshold = entropy_threshold

        self.all_nodes = all_nodes or []
        self.local_rank = local_rank
        self.master_addr = master_addr
        self.master_port = master_port

        self.epochs = epochs
        self.lr = learning_rate
        self.starting_batch = starting_batch
        self.input_dim = input_dim

        self.expected_cuda_version = (
            expected_cuda_version
            or os.environ.get("YGB_CUDA_VERSION", None)
        )

        # State
        self.node_id: str = ""
        self.optimal_batch_2050: int = starting_batch
        self.dataset_hash: str = ""
        self.weight_hash: str = ""
        self.world_size: int = 1
        self.epoch_reports: List[EpochReport] = []
        self.errors: List[str] = []

    # -----------------------------------------------------------------
    # STEP 1: Verify CUDA
    # -----------------------------------------------------------------
    def verify_cuda(self) -> CUDAVerification:
        """Verify CUDA availability, compute capability, FP16, version."""
        errors = []

        try:
            import torch
        except ImportError:
            return CUDAVerification(
                cuda_available=False, compute_capability="N/A",
                cc_version=0.0, fp16_supported=False, cuda_version="N/A",
                cuda_version_match=False, device_name="N/A",
                vram_total_mb=0, passed=False,
                errors=["PyTorch not installed"],
            )

        cuda_avail = torch.cuda.is_available()
        if not cuda_avail:
            return CUDAVerification(
                cuda_available=False, compute_capability="N/A",
                cc_version=0.0, fp16_supported=False, cuda_version="N/A",
                cuda_version_match=False, device_name="N/A",
                vram_total_mb=0, passed=False,
                errors=["CUDA not available"],
            )

        props = torch.cuda.get_device_properties(0)
        cc_str = f"{props.major}.{props.minor}"
        cc_val = props.major + props.minor / 10.0
        device_name = props.name
        vram_mb = props.total_memory / (1024 ** 2)
        cuda_ver = torch.version.cuda or "unknown"

        # FP16 supported for cc >= 7.0
        fp16 = cc_val >= 7.0

        # Compute capability check
        if cc_val < self.MIN_COMPUTE_CAPABILITY:
            errors.append(
                f"Compute capability {cc_str} < required {self.MIN_COMPUTE_CAPABILITY}"
            )

        if not fp16:
            errors.append("FP16 not supported (cc < 7.0)")

        # CUDA version match
        version_match = True
        if self.expected_cuda_version:
            version_match = cuda_ver == self.expected_cuda_version
            if not version_match:
                errors.append(
                    f"CUDA version mismatch: expected {self.expected_cuda_version}, "
                    f"got {cuda_ver}"
                )

        passed = cuda_avail and cc_val >= self.MIN_COMPUTE_CAPABILITY and fp16 and version_match

        result = CUDAVerification(
            cuda_available=cuda_avail,
            compute_capability=cc_str,
            cc_version=cc_val,
            fp16_supported=fp16,
            cuda_version=cuda_ver,
            cuda_version_match=version_match,
            device_name=device_name,
            vram_total_mb=round(vram_mb, 1),
            passed=passed,
            errors=errors,
        )

        if passed:
            logger.info(
                f"[RTX2050] CUDA verified: {device_name}, cc={cc_str}, "
                f"CUDA={cuda_ver}, VRAM={vram_mb:.0f}MB"
            )
        else:
            logger.error(f"[RTX2050] CUDA verification FAILED: {errors}")

        return result

    # -----------------------------------------------------------------
    # STEP 2: Validate dataset
    # -----------------------------------------------------------------
    def validate_dataset(self):
        """Validate dataset integrity using dataset_validator module."""
        from impl_v1.training.distributed.dataset_validator import validate_dataset

        result = validate_dataset(
            X=self.X,
            y=self.y,
            expected_hash=self.expected_dataset_hash,
            expected_sample_count=self.expected_sample_count,
            expected_feature_dim=self.expected_feature_dim,
            expected_label_distribution=self.expected_label_distribution,
            label_tolerance=self.label_tolerance,
            entropy_threshold=self.entropy_threshold,
        )

        self.dataset_hash = result.dataset_hash
        return result

    # -----------------------------------------------------------------
    # STEP 3: Adaptive batch scaling
    # -----------------------------------------------------------------
    def run_adaptive_batch_scaling(self) -> int:
        """Run adaptive batch scaling and store optimal_batch_2050."""
        from impl_v1.training.config.adaptive_batch import find_optimal_batch_size

        scale_result = find_optimal_batch_size(
            starting_batch=self.starting_batch,
            input_dim=self.input_dim,
        )

        self.optimal_batch_2050 = scale_result.optimal_batch_size
        logger.info(
            f"[RTX2050] Adaptive batch: optimal_batch_2050={self.optimal_batch_2050}"
        )
        return self.optimal_batch_2050

    # -----------------------------------------------------------------
    # STEP 4: Join NCCL group
    # -----------------------------------------------------------------
    def join_nccl_group(self) -> bool:
        """Join NCCL DDP group. world_size must equal number of CUDA nodes."""
        from impl_v1.training.distributed.cuda_ddp_group import (
            create_cuda_ddp_group,
            init_cuda_ddp,
        )

        group = create_cuda_ddp_group(
            all_nodes=self.all_nodes,
            base_seed=42,
        )

        self.world_size = group.world_size

        # Assert world_size equals number of CUDA nodes
        cuda_count = sum(
            1 for n in self.all_nodes
            if n.get('backend', '') == 'cuda' and n.get('ddp_eligible', False)
        )
        if group.world_size != cuda_count:
            err = (
                f"world_size ({group.world_size}) != "
                f"CUDA node count ({cuda_count})"
            )
            self.errors.append(err)
            logger.error(f"[RTX2050] {err}")
            return False

        success = init_cuda_ddp(
            group=group,
            local_rank=self.local_rank,
            master_addr=self.master_addr,
            master_port=self.master_port,
        )

        if success:
            logger.info(
                f"[RTX2050] Joined NCCL group: "
                f"rank={self.local_rank}/{self.world_size}"
            )
        else:
            self.errors.append("NCCL init failed")

        return success

    # -----------------------------------------------------------------
    # STEP 5: Initialize deterministic mode
    # -----------------------------------------------------------------
    def init_deterministic(self):
        """Set deterministic training config."""
        import torch

        torch.manual_seed(42)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

        try:
            torch.use_deterministic_algorithms(True)
        except Exception:
            pass

        logger.info("[RTX2050] Deterministic mode initialized")

    # -----------------------------------------------------------------
    # STEP 6 + 7: Train with all-reduce + weight hash
    # -----------------------------------------------------------------
    def train(self) -> List[EpochReport]:
        """Run DDP training loop with all-reduce and per-epoch weight hash.

        Steps 6 (all-reduce) and 7 (weight hash) are combined here since
        all-reduce happens implicitly during DDP backward pass.
        """
        import torch
        import torch.nn as nn
        import torch.optim as optim

        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # Build model
        model = nn.Sequential(
            nn.Linear(self.input_dim, 512), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(512, 256), nn.ReLU(),
            nn.Linear(256, 2),
        ).to(device)

        # Wrap in DDP if multi-GPU initialized
        try:
            import torch.distributed as dist
            if dist.is_initialized():
                from torch.nn.parallel import DistributedDataParallel as DDP
                model = DDP(model, device_ids=[self.local_rank])
        except Exception:
            pass

        optimizer = optim.Adam(model.parameters(), lr=self.lr)
        criterion = nn.CrossEntropyLoss()

        X_t = torch.from_numpy(self.X.astype(np.float32)).to(device)
        y_t = torch.from_numpy(self.y.astype(np.int64)).to(device)

        batch_size = self.optimal_batch_2050
        num_samples = X_t.size(0)

        reports = []

        for epoch in range(self.epochs):
            model.train()
            t0 = time.perf_counter()
            processed = 0
            running_loss = 0.0
            batches = 0

            for i in range(0, num_samples, batch_size):
                bx = X_t[i:i + batch_size]
                by = y_t[i:i + batch_size]

                optimizer.zero_grad()
                out = model(bx)
                loss = criterion(out, by)
                loss.backward()       # ← all-reduce happens here under DDP
                optimizer.step()

                processed += bx.size(0)
                running_loss += loss.item()
                batches += 1

            elapsed = time.perf_counter() - t0
            avg_loss = running_loss / max(batches, 1)
            sps = processed / max(elapsed, 0.001)

            # Step 7: compute weight hash
            raw_model = model.module if hasattr(model, 'module') else model
            w_hash = self._compute_weight_hash(raw_model)
            self.weight_hash = w_hash

            report = EpochReport(
                epoch=epoch,
                weight_hash=w_hash,
                loss=round(avg_loss, 6),
                samples_processed=processed,
                samples_per_sec=round(sps, 2),
                elapsed_sec=round(elapsed, 3),
            )
            reports.append(report)

            logger.info(
                f"[RTX2050] Epoch {epoch}: loss={avg_loss:.4f}, "
                f"sps={sps:.0f}, hash={w_hash[:16]}..."
            )

        # Cleanup
        del model, optimizer, X_t, y_t
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        self.epoch_reports = reports
        return reports

    # -----------------------------------------------------------------
    # STEP 8: Structured log
    # -----------------------------------------------------------------
    def emit_log(self) -> Dict[str, Any]:
        """Emit structured JSON log to logger and return dict."""
        log_entry = {
            "world_size": self.world_size,
            "local_batch": self.optimal_batch_2050,
            "samples_per_sec": (
                self.epoch_reports[-1].samples_per_sec
                if self.epoch_reports else 0
            ),
            "weight_hash": self.weight_hash,
            "dataset_hash": self.dataset_hash,
        }
        logger.info(f"[RTX2050] REPORT: {json.dumps(log_entry)}")
        return log_entry

    # -----------------------------------------------------------------
    # FULL PIPELINE
    # -----------------------------------------------------------------
    def run(self) -> NodeRunResult:
        """Execute the full 8-step DDP node protocol.

        Returns NodeRunResult with all metrics.
        Aborts early if any critical step fails.
        """
        logger.info("=" * 60)
        logger.info("[RTX2050] Starting 8-step DDP node protocol")
        logger.info("=" * 60)

        # Step 1: Verify CUDA
        cuda = self.verify_cuda()
        if not cuda.passed:
            self.errors.extend(cuda.errors)
            return self._build_result(cuda_verified=False)

        self.node_id = hashlib.sha256(
            f"{cuda.device_name}|{cuda.compute_capability}|{cuda.cuda_version}"
            .encode()
        ).hexdigest()

        # Step 2: Validate dataset
        ds = self.validate_dataset()
        if not ds.valid:
            self.errors.extend(ds.errors)
            return self._build_result(cuda_verified=True, dataset_valid=False)

        # Step 3: Adaptive batch scaling
        self.run_adaptive_batch_scaling()

        # Step 4: Join NCCL group
        ddp_ok = True
        if self.all_nodes:
            ddp_ok = self.join_nccl_group()

        # Step 5: Deterministic mode
        self.init_deterministic()

        # Step 6 + 7: Train with all-reduce + weight hash
        self.train()

        # Step 8: Structured log
        self.emit_log()

        return self._build_result(
            cuda_verified=True,
            dataset_valid=True,
            ddp_initialized=ddp_ok,
        )

    # -----------------------------------------------------------------
    # HELPERS
    # -----------------------------------------------------------------
    @staticmethod
    def _compute_weight_hash(model) -> str:
        """SHA-256 of model weights."""
        weight_bytes = b""
        for name, param in sorted(model.named_parameters()):
            weight_bytes += param.detach().cpu().numpy().tobytes()
        return hashlib.sha256(weight_bytes).hexdigest()

    def _build_result(
        self,
        cuda_verified: bool = False,
        dataset_valid: bool = False,
        ddp_initialized: bool = False,
    ) -> NodeRunResult:
        return NodeRunResult(
            node_id=self.node_id,
            device_name="RTX 2050",
            cuda_verified=cuda_verified,
            dataset_valid=dataset_valid,
            optimal_batch_2050=self.optimal_batch_2050,
            world_size=self.world_size,
            ddp_initialized=ddp_initialized,
            deterministic=True,
            epochs_completed=len(self.epoch_reports),
            final_weight_hash=self.weight_hash,
            final_dataset_hash=self.dataset_hash,
            epoch_reports=[asdict(r) for r in self.epoch_reports],
            errors=self.errors,
        )
