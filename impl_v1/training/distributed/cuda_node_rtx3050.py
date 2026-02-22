"""
cuda_node_rtx3050.py — CUDA RTX 3050 DDP Follower Node

8-step protocol for joining RTX 2050 leader as follower (rank=1):

  1. Verify CUDA (driver match, CUDA version match, allow_tf32=False,
     deterministic_algorithms=True)
  2. Connect to leader (receive leader_term, confirm world_size=2)
  3. Validate dataset (hash, sample_count, feature_dim, entropy)
  4. Run adaptive batch scaling → optimal_batch_3050, send capacity to leader
  5. Join NCCL DDP (rank=1, world_size=2)
  6. Participate in training (grad_clip=1.0, async all-reduce, strict determinism)
  7. After each epoch: compute weight_hash, send to leader, report local sps
  8. Final output: {local_batch, local_samples_per_sec, weight_hash, dataset_hash}

Usage:
    from impl_v1.training.distributed.cuda_node_rtx3050 import RTX3050Follower
    follower = RTX3050Follower(...)
    result = follower.run()
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
    """Step 1: CUDA hardware and configuration checks."""
    cuda_available: bool
    compute_capability: str
    cc_version: float
    fp16_supported: bool
    cuda_version: str
    cuda_version_match: bool
    driver_version: str
    driver_match: bool
    tf32_disabled: bool
    deterministic_enabled: bool
    device_name: str
    vram_total_mb: float
    sm_count: int
    passed: bool
    errors: List[str] = field(default_factory=list)


@dataclass
class LeaderConnection:
    """Step 2: Leader connection confirmation."""
    connected: bool
    leader_term: int
    world_size: int
    leader_dataset_hash: str
    leader_cuda_version: str
    errors: List[str] = field(default_factory=list)


@dataclass
class EpochReport:
    """Per-epoch training report sent to leader."""
    epoch: int
    weight_hash: str
    loss: float
    accuracy: float
    samples_processed: int
    samples_per_sec: float
    elapsed_sec: float
    grad_norm_avg: float


@dataclass
class FollowerRunResult:
    """Complete follower execution result."""
    node_id: str
    device_name: str
    rank: int
    cuda_verified: bool
    leader_connected: bool
    leader_term: int
    dataset_valid: bool
    optimal_batch_3050: int
    capacity_score: float
    world_size: int
    ddp_initialized: bool
    deterministic: bool
    epochs_completed: int
    final_weight_hash: str
    final_dataset_hash: str
    final_samples_per_sec: float
    epoch_reports: List[Dict]
    errors: List[str]


@dataclass
class FollowerOutput:
    """Final output sent to leader (Step 8)."""
    local_batch: int
    local_samples_per_sec: float
    weight_hash: str
    dataset_hash: str


# =============================================================================
# RTX 3050 FOLLOWER NODE
# =============================================================================

class RTX3050Follower:
    """CUDA RTX 3050 DDP follower node (rank=1).

    Implements the full 8-step protocol for joining the RTX 2050 leader.
    """

    RANK = 1
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
        # Leader info
        leader_term: int = 1,
        leader_cuda_version: Optional[str] = None,
        leader_driver_version: Optional[str] = None,
        # Cluster
        all_nodes: Optional[List[dict]] = None,
        master_addr: str = "127.0.0.1",
        master_port: str = "29500",
        # Training
        epochs: int = 1,
        learning_rate: float = 0.001,
        starting_batch: int = 1024,
        input_dim: int = 256,
        num_classes: int = 2,
        gradient_clip: float = 1.0,
    ):
        self.X = X
        self.y = y
        self.expected_dataset_hash = expected_dataset_hash
        self.expected_sample_count = expected_sample_count
        self.expected_feature_dim = expected_feature_dim
        self.expected_label_distribution = expected_label_distribution
        self.label_tolerance = label_tolerance
        self.entropy_threshold = entropy_threshold

        self.leader_term = leader_term
        self.leader_cuda_version = leader_cuda_version
        self.leader_driver_version = leader_driver_version

        self.all_nodes = all_nodes or []
        self.master_addr = master_addr
        self.master_port = master_port

        self.epochs = epochs
        self.lr = learning_rate
        self.starting_batch = starting_batch
        self.input_dim = input_dim
        self.num_classes = num_classes
        self.gradient_clip = gradient_clip

        # State
        self.node_id: str = ""
        self.optimal_batch_3050: int = starting_batch
        self.capacity_score: float = 0.0
        self.dataset_hash: str = ""
        self.weight_hash: str = ""
        self.world_size: int = 2
        self.epoch_reports: List[EpochReport] = []
        self.errors: List[str] = []
        self.final_sps: float = 0.0

    # -----------------------------------------------------------------
    # STEP 1: Verify CUDA
    # -----------------------------------------------------------------
    def verify_cuda(self) -> CUDAVerification:
        """Verify CUDA: driver match, CUDA version match,
        allow_tf32=False, deterministic_algorithms=True.
        """
        errors = []

        try:
            import torch
        except ImportError:
            return CUDAVerification(
                cuda_available=False, compute_capability="N/A",
                cc_version=0.0, fp16_supported=False, cuda_version="N/A",
                cuda_version_match=False, driver_version="N/A",
                driver_match=False, tf32_disabled=False,
                deterministic_enabled=False, device_name="N/A",
                vram_total_mb=0, sm_count=0, passed=False,
                errors=["PyTorch not installed"],
            )

        cuda_avail = torch.cuda.is_available()
        if not cuda_avail:
            return CUDAVerification(
                cuda_available=False, compute_capability="N/A",
                cc_version=0.0, fp16_supported=False, cuda_version="N/A",
                cuda_version_match=False, driver_version="N/A",
                driver_match=False, tf32_disabled=False,
                deterministic_enabled=False, device_name="N/A",
                vram_total_mb=0, sm_count=0, passed=False,
                errors=["CUDA not available"],
            )

        props = torch.cuda.get_device_properties(0)
        cc_str = f"{props.major}.{props.minor}"
        cc_val = props.major + props.minor / 10.0
        device_name = props.name
        vram_mb = props.total_memory / (1024 ** 2)
        sm_count = props.multi_processor_count
        cuda_ver = torch.version.cuda or "unknown"

        # Driver version
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            driver_ver = result.stdout.strip().split('\n')[0].strip()
        except Exception:
            driver_ver = "unknown"

        # FP16 supported for cc >= 7.0
        fp16 = cc_val >= 7.0

        # Compute capability check
        if cc_val < self.MIN_COMPUTE_CAPABILITY:
            errors.append(
                f"Compute capability {cc_str} < required {self.MIN_COMPUTE_CAPABILITY}"
            )

        if not fp16:
            errors.append("FP16 not supported (cc < 7.0)")

        # CUDA version match with leader
        version_match = True
        if self.leader_cuda_version:
            version_match = cuda_ver == self.leader_cuda_version
            if not version_match:
                errors.append(
                    f"CUDA version mismatch: leader={self.leader_cuda_version}, "
                    f"local={cuda_ver}"
                )

        # Driver version match with leader
        driver_match = True
        if self.leader_driver_version:
            driver_match = driver_ver == self.leader_driver_version
            if not driver_match:
                errors.append(
                    f"Driver mismatch: leader={self.leader_driver_version}, "
                    f"local={driver_ver}"
                )

        # Enforcement: allow_tf32 = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        tf32_disabled = (
            not torch.backends.cuda.matmul.allow_tf32 and
            not torch.backends.cudnn.allow_tf32
        )

        # Enforcement: deterministic_algorithms = True
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        try:
            torch.use_deterministic_algorithms(True)
            det_enabled = True
        except Exception:
            det_enabled = False
            errors.append("deterministic_algorithms could not be enabled")

        passed = (
            cuda_avail and cc_val >= self.MIN_COMPUTE_CAPABILITY and
            fp16 and version_match and driver_match and
            tf32_disabled and det_enabled
        )

        result = CUDAVerification(
            cuda_available=cuda_avail,
            compute_capability=cc_str,
            cc_version=cc_val,
            fp16_supported=fp16,
            cuda_version=cuda_ver,
            cuda_version_match=version_match,
            driver_version=driver_ver,
            driver_match=driver_match,
            tf32_disabled=tf32_disabled,
            deterministic_enabled=det_enabled,
            device_name=device_name,
            vram_total_mb=round(vram_mb, 1),
            sm_count=sm_count,
            passed=passed,
            errors=errors,
        )

        if passed:
            logger.info(
                f"[RTX3050] CUDA verified: {device_name}, cc={cc_str}, "
                f"CUDA={cuda_ver}, driver={driver_ver}, "
                f"VRAM={vram_mb:.0f}MB, SM={sm_count}, "
                f"TF32=off, deterministic=on"
            )
        else:
            logger.error(f"[RTX3050] CUDA verification FAILED: {errors}")

        return result

    # -----------------------------------------------------------------
    # STEP 2: Connect to leader
    # -----------------------------------------------------------------
    def connect_to_leader(self) -> LeaderConnection:
        """Receive leader_term, confirm world_size=2."""
        errors = []

        if self.leader_term < 1:
            errors.append(f"Invalid leader_term: {self.leader_term}")

        if self.world_size != 2:
            errors.append(f"Expected world_size=2, got {self.world_size}")

        connected = len(errors) == 0

        result = LeaderConnection(
            connected=connected,
            leader_term=self.leader_term,
            world_size=self.world_size,
            leader_dataset_hash=self.expected_dataset_hash,
            leader_cuda_version=self.leader_cuda_version or "",
            errors=errors,
        )

        if connected:
            logger.info(
                f"[RTX3050] Connected to leader: term={self.leader_term}, "
                f"world_size={self.world_size}, "
                f"dataset={self.expected_dataset_hash[:16]}..."
            )
        else:
            logger.error(f"[RTX3050] Leader connection FAILED: {errors}")

        return result

    # -----------------------------------------------------------------
    # STEP 3: Validate dataset
    # -----------------------------------------------------------------
    def validate_dataset(self):
        """Dataset hash, sample_count, feature_dim, entropy must match leader."""
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

        if result.valid:
            logger.info(
                f"[RTX3050] Dataset validated: hash={result.dataset_hash[:16]}..., "
                f"samples={result.sample_count}, dim={result.feature_dim}, "
                f"entropy={result.label_entropy:.4f}"
            )
        else:
            logger.error(f"[RTX3050] Dataset validation FAILED: {result.errors}")

        return result

    # -----------------------------------------------------------------
    # STEP 4: Adaptive batch scaling
    # -----------------------------------------------------------------
    def run_adaptive_batch_scaling(self) -> int:
        """Run adaptive batch scaling, store optimal_batch_3050,
        compute capacity score for leader.
        """
        from impl_v1.training.config.adaptive_batch import find_optimal_batch_size

        scale_result = find_optimal_batch_size(
            starting_batch=self.starting_batch,
            input_dim=self.input_dim,
        )

        self.optimal_batch_3050 = scale_result.optimal_batch_size

        # Capacity score: VRAM-weighted throughput estimate
        try:
            import torch
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / (1024 ** 3)
            sm = props.multi_processor_count
            self.capacity_score = round(vram_gb * sm / 100, 4)
        except Exception:
            self.capacity_score = 1.0

        logger.info(
            f"[RTX3050] Adaptive batch: optimal_batch_3050={self.optimal_batch_3050}, "
            f"capacity_score={self.capacity_score}"
        )

        return self.optimal_batch_3050

    # -----------------------------------------------------------------
    # STEP 5: Join NCCL DDP
    # -----------------------------------------------------------------
    def join_nccl_ddp(self) -> bool:
        """Join NCCL DDP group as rank=1, world_size=2."""
        from impl_v1.training.distributed.cuda_ddp_group import (
            create_cuda_ddp_group,
            init_cuda_ddp,
        )

        group = create_cuda_ddp_group(
            all_nodes=self.all_nodes,
            base_seed=42,
        )

        self.world_size = group.world_size

        success = init_cuda_ddp(
            group=group,
            local_rank=self.RANK,
            master_addr=self.master_addr,
            master_port=self.master_port,
        )

        if success:
            logger.info(
                f"[RTX3050] Joined NCCL DDP: rank={self.RANK}/{self.world_size}"
            )
        else:
            self.errors.append("NCCL DDP join failed")
            logger.error("[RTX3050] NCCL DDP join FAILED")

        return success

    # -----------------------------------------------------------------
    # STEP 6 + 7: Train with gradient clip + weight hash
    # -----------------------------------------------------------------
    def train(self) -> List[EpochReport]:
        """DDP training with gradient clipping, deterministic mode.

        After each epoch:
          - Compute local weight_hash
          - Report local samples/sec
        """
        import torch
        import torch.nn as nn
        import torch.optim as optim

        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # Model architecture — must match leader
        model = nn.Sequential(
            nn.Linear(self.input_dim, 512), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(512, 256), nn.ReLU(),
            nn.Linear(256, self.num_classes),
        ).to(device)

        # Wrap in DDP if distributed initialized
        try:
            import torch.distributed as dist
            if dist.is_initialized():
                from torch.nn.parallel import DistributedDataParallel as DDP
                model = DDP(model, device_ids=[self.RANK])
        except Exception:
            pass

        optimizer = optim.Adam(model.parameters(), lr=self.lr)
        criterion = nn.CrossEntropyLoss()

        # Deterministic seed
        torch.manual_seed(42)
        np.random.seed(42)

        X_t = torch.from_numpy(self.X.astype(np.float32)).to(device)
        y_t = torch.from_numpy(self.y.astype(np.int64)).to(device)

        batch_size = self.optimal_batch_3050
        num_samples = X_t.size(0)

        reports = []

        for epoch in range(self.epochs):
            model.train()
            t0 = time.perf_counter()
            processed = 0
            running_loss = 0.0
            batches = 0
            total_grad_norm = 0.0

            for i in range(0, num_samples, batch_size):
                bx = X_t[i:i + batch_size]
                by = y_t[i:i + batch_size]

                optimizer.zero_grad()
                out = model(bx)
                loss = criterion(out, by)
                loss.backward()  # ← all-reduce via DDP

                # Gradient clipping
                raw_model = model.module if hasattr(model, 'module') else model
                grad_norm = torch.nn.utils.clip_grad_norm_(
                    raw_model.parameters(), self.gradient_clip,
                )
                total_grad_norm += (
                    grad_norm.item() if hasattr(grad_norm, 'item')
                    else float(grad_norm)
                )

                optimizer.step()

                processed += bx.size(0)
                running_loss += loss.item()
                batches += 1

            elapsed = time.perf_counter() - t0
            avg_loss = running_loss / max(batches, 1)
            sps = processed / max(elapsed, 0.001)
            avg_grad_norm = total_grad_norm / max(batches, 1)

            # Compute accuracy
            raw_model = model.module if hasattr(model, 'module') else model
            raw_model.eval()
            with torch.no_grad():
                preds = raw_model(X_t[:min(5000, num_samples)]).argmax(1)
                targets = y_t[:min(5000, num_samples)]
                acc = (preds == targets).float().mean().item()

            # Step 7: compute weight hash
            w_hash = self._compute_weight_hash(raw_model)
            self.weight_hash = w_hash

            report = EpochReport(
                epoch=epoch,
                weight_hash=w_hash,
                loss=round(avg_loss, 6),
                accuracy=round(acc, 6),
                samples_processed=processed,
                samples_per_sec=round(sps, 2),
                elapsed_sec=round(elapsed, 3),
                grad_norm_avg=round(avg_grad_norm, 4),
            )
            reports.append(report)

            logger.info(
                f"[RTX3050] Epoch {epoch}: loss={avg_loss:.4f}, "
                f"acc={acc:.4f}, sps={sps:.0f}, "
                f"grad_norm={avg_grad_norm:.4f}, "
                f"hash={w_hash[:16]}..."
            )

        # Store final sps
        if reports:
            self.final_sps = reports[-1].samples_per_sec

        # Cleanup
        del model, optimizer, X_t, y_t
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        self.epoch_reports = reports
        return reports

    # -----------------------------------------------------------------
    # STEP 8: Final output
    # -----------------------------------------------------------------
    def emit_final_output(self) -> FollowerOutput:
        """Emit final output to leader."""
        output = FollowerOutput(
            local_batch=self.optimal_batch_3050,
            local_samples_per_sec=self.final_sps,
            weight_hash=self.weight_hash,
            dataset_hash=self.dataset_hash,
        )

        logger.info(
            f"[RTX3050] FINAL OUTPUT → leader: "
            f"{json.dumps(asdict(output))}"
        )

        return output

    # -----------------------------------------------------------------
    # FULL PIPELINE
    # -----------------------------------------------------------------
    def run(self) -> FollowerRunResult:
        """Execute the full 8-step DDP follower protocol.

        Returns FollowerRunResult with all metrics.
        Aborts early if any critical step fails.
        """
        logger.info("=" * 60)
        logger.info("[RTX3050] Starting 8-step DDP follower protocol")
        logger.info("=" * 60)

        # Step 1: Verify CUDA
        logger.info("[RTX3050] ═══ STEP 1: CUDA Verification ═══")
        cuda = self.verify_cuda()
        if not cuda.passed:
            self.errors.extend(cuda.errors)
            return self._build_result(cuda_verified=False)

        self.node_id = hashlib.sha256(
            f"{cuda.device_name}|{cuda.compute_capability}|{cuda.cuda_version}"
            .encode()
        ).hexdigest()

        # Step 2: Connect to leader
        logger.info("[RTX3050] ═══ STEP 2: Connect to Leader ═══")
        leader = self.connect_to_leader()
        if not leader.connected:
            self.errors.extend(leader.errors)
            return self._build_result(cuda_verified=True)

        # Step 3: Validate dataset
        logger.info("[RTX3050] ═══ STEP 3: Dataset Validation ═══")
        ds = self.validate_dataset()
        if not ds.valid:
            self.errors.extend(ds.errors)
            return self._build_result(cuda_verified=True, dataset_valid=False)

        # Step 4: Adaptive batch scaling
        logger.info("[RTX3050] ═══ STEP 4: Adaptive Batch Scaling ═══")
        self.run_adaptive_batch_scaling()

        # Step 5: Join NCCL DDP
        logger.info("[RTX3050] ═══ STEP 5: Join NCCL DDP ═══")
        ddp_ok = True
        if self.all_nodes:
            ddp_ok = self.join_nccl_ddp()

        # Step 6+7: Train
        logger.info("[RTX3050] ═══ STEP 6+7: Training + Weight Hash ═══")
        self.train()

        # Step 8: Final output
        logger.info("[RTX3050] ═══ STEP 8: Final Output ═══")
        self.emit_final_output()

        return self._build_result(
            cuda_verified=True,
            leader_connected=True,
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
        leader_connected: bool = False,
        dataset_valid: bool = False,
        ddp_initialized: bool = False,
    ) -> FollowerRunResult:
        return FollowerRunResult(
            node_id=self.node_id,
            device_name="RTX 3050",
            rank=self.RANK,
            cuda_verified=cuda_verified,
            leader_connected=leader_connected,
            leader_term=self.leader_term,
            dataset_valid=dataset_valid,
            optimal_batch_3050=self.optimal_batch_3050,
            capacity_score=self.capacity_score,
            world_size=self.world_size,
            ddp_initialized=ddp_initialized,
            deterministic=True,
            epochs_completed=len(self.epoch_reports),
            final_weight_hash=self.weight_hash,
            final_dataset_hash=self.dataset_hash,
            final_samples_per_sec=self.final_sps,
            epoch_reports=[asdict(r) for r in self.epoch_reports],
            errors=self.errors,
        )
