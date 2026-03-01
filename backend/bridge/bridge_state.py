"""
Bridge State Persistence — Cross-Process Authoritative Counter Store.

Solves the core problem: C++ ingestion_engine uses process-local static
globals, so bridge counters are lost when the ingest script exits.

This module provides a JSON-backed persistent state file that is:
  - Atomically written (write to .tmp, then os.replace)
  - Readable by any process
  - The AUTHORITATIVE source for bridge_count / bridge_verified_count

State file: secure_data/bridge_state.json
Sample store: secure_data/bridge_samples.jsonl.gz

Usage:
    from backend.bridge.bridge_state import get_bridge_state

    state = get_bridge_state()
    state.record_ingest(count=1, verified=1, sample_data={...})
    counts = state.get_counts()  # cross-process safe
"""

import gzip
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ygb.bridge_state")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SECURE_DATA = _PROJECT_ROOT / "secure_data"
_STATE_PATH = _SECURE_DATA / "bridge_state.json"
_SAMPLES_PATH = _SECURE_DATA / "bridge_samples.jsonl.gz"

# Threshold constant (must match YGB_MIN_REAL_SAMPLES)
BRIDGE_THRESHOLD = int(os.environ.get("YGB_MIN_REAL_SAMPLES", "125000"))


class BridgeState:
    """Persistent, cross-process bridge counter state.

    All counter reads go through this class, not the DLL directly.
    All counter writes atomically persist to disk.
    """

    def __init__(self, state_path: Path = None, samples_path: Path = None):
        self._state_path = state_path or _STATE_PATH
        self._samples_path = samples_path or _SAMPLES_PATH
        self._state: Dict[str, Any] = self._default_state()
        self._sample_buffer: List[Dict[str, str]] = []
        self._buffer_flush_threshold = 500  # flush every N samples
        self.load()

    @staticmethod
    def _default_state() -> Dict[str, Any]:
        return {
            "bridge_count": 0,
            "bridge_verified_count": 0,
            "total_ingested": 0,
            "total_dropped": 0,
            "total_deduped": 0,
            "last_ingest_at": None,
            "ingest_hash": None,
            "samples_path": None,
            "samples_written": 0,
            "updated_at": None,
        }

    # =========================================================================
    # LOAD / SAVE
    # =========================================================================

    def load(self) -> Dict[str, Any]:
        """Load persisted state from disk. Safe if file missing."""
        if self._state_path.exists():
            try:
                with open(self._state_path, "r") as f:
                    data = json.load(f)
                # Merge with defaults to handle schema evolution
                merged = self._default_state()
                merged.update(data)
                self._state = merged
                logger.info(
                    f"[BRIDGE_STATE] Loaded: count={self._state['bridge_count']}, "
                    f"verified={self._state['bridge_verified_count']}"
                )
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"[BRIDGE_STATE] Load failed: {e}, using defaults")
                self._state = self._default_state()
        else:
            logger.info("[BRIDGE_STATE] No persisted state, starting fresh")
            self._state = self._default_state()
        return self._state

    def save(self):
        """Atomically persist current state to disk."""
        self._state["updated_at"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S%z", time.localtime()
        )
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._state_path.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w") as f:
                json.dump(self._state, f, indent=2)
            os.replace(str(tmp_path), str(self._state_path))
        except Exception as e:
            logger.error(f"[BRIDGE_STATE] Save failed: {e}")
            # Clean up tmp if rename failed
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    # =========================================================================
    # COUNTER OPERATIONS
    # =========================================================================

    def get_counts(self) -> Dict[str, Any]:
        """Get authoritative bridge counters (from persisted state)."""
        return {
            "bridge_count": self._state["bridge_count"],
            "bridge_verified_count": self._state["bridge_verified_count"],
            "total_ingested": self._state["total_ingested"],
            "total_dropped": self._state["total_dropped"],
            "total_deduped": self._state["total_deduped"],
            "last_ingest_at": self._state["last_ingest_at"],
            "threshold": BRIDGE_THRESHOLD,
            "deficit": max(
                0, BRIDGE_THRESHOLD - self._state["bridge_verified_count"]
            ),
            "go_no_go": (
                "GO"
                if self._state["bridge_verified_count"] >= BRIDGE_THRESHOLD
                else "NO_GO"
            ),
            "authoritative_source": "bridge_state.json",
        }

    def set_counts(
        self,
        bridge_count: int,
        bridge_verified_count: int,
        total_ingested: int = 0,
        total_dropped: int = 0,
        total_deduped: int = 0,
    ):
        """Set counters and persist. Used after bulk ingest."""
        self._state["bridge_count"] = bridge_count
        self._state["bridge_verified_count"] = bridge_verified_count
        self._state["total_ingested"] = total_ingested
        self._state["total_dropped"] = total_dropped
        self._state["total_deduped"] = total_deduped
        self._state["last_ingest_at"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )
        # Compute integrity hash
        self._state["ingest_hash"] = hashlib.sha256(
            json.dumps(
                {
                    "count": bridge_count,
                    "verified": bridge_verified_count,
                    "ingested": total_ingested,
                }
            ).encode()
        ).hexdigest()[:16]
        self.save()
        logger.info(
            f"[BRIDGE_STATE] Persisted: count={bridge_count}, "
            f"verified={bridge_verified_count}"
        )

    def record_ingest_batch(self, new_ingested: int, new_verified: int):
        """Increment counters by batch amounts and persist."""
        self._state["bridge_count"] += new_ingested
        self._state["bridge_verified_count"] += new_verified
        self._state["total_ingested"] += new_ingested
        self._state["last_ingest_at"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )
        self.save()

    def record_drop(self, count: int = 1):
        """Record dropped samples."""
        self._state["total_dropped"] += count

    def record_dedup(self, count: int = 1):
        """Record deduplicated samples."""
        self._state["total_deduped"] += count

    # =========================================================================
    # SAMPLE STORE (disk-backed)
    # =========================================================================

    def append_sample(self, sample: Dict[str, str]):
        """Buffer a sample for bulk write."""
        self._sample_buffer.append(sample)
        if len(self._sample_buffer) >= self._buffer_flush_threshold:
            self.flush_samples()

    def flush_samples(self):
        """Flush buffered samples to gzip JSONL file."""
        if not self._sample_buffer:
            return
        self._samples_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            mode = "ab" if self._samples_path.exists() else "wb"
            with gzip.open(str(self._samples_path), mode) as f:
                for sample in self._sample_buffer:
                    line = json.dumps(sample, separators=(",", ":")) + "\n"
                    f.write(line.encode("utf-8"))
            written = len(self._sample_buffer)
            self._state["samples_written"] = (
                self._state.get("samples_written", 0) + written
            )
            self._state["samples_path"] = str(self._samples_path)
            self._sample_buffer.clear()
            logger.debug(f"[BRIDGE_STATE] Flushed {written} samples to disk")
        except Exception as e:
            logger.error(f"[BRIDGE_STATE] Sample flush failed: {e}")

    def write_all_samples(self, samples: List[Dict[str, str]]):
        """Write all samples at once (overwrite mode)."""
        self._samples_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with gzip.open(str(self._samples_path), "wb") as f:
                for sample in samples:
                    line = json.dumps(sample, separators=(",", ":")) + "\n"
                    f.write(line.encode("utf-8"))
            self._state["samples_written"] = len(samples)
            self._state["samples_path"] = str(self._samples_path)
            self.save()
            logger.info(
                f"[BRIDGE_STATE] Wrote {len(samples)} samples to {self._samples_path}"
            )
        except Exception as e:
            logger.error(f"[BRIDGE_STATE] Sample write failed: {e}")

    def read_samples(self, max_samples: int = 0) -> List[Dict[str, str]]:
        """Read persisted samples from gzip JSONL file."""
        if not self._samples_path.exists():
            return []
        samples = []
        try:
            with gzip.open(str(self._samples_path), "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    samples.append(json.loads(line))
                    if max_samples and len(samples) >= max_samples:
                        break
        except Exception as e:
            logger.error(f"[BRIDGE_STATE] Sample read failed: {e}")
        return samples

    def get_sample_count(self) -> int:
        """Get number of persisted samples without loading them all."""
        return self._state.get("samples_written", 0)

    # =========================================================================
    # CONSISTENCY CHECKS
    # =========================================================================

    def check_manifest_consistency(self) -> Dict[str, Any]:
        """Compare persisted bridge state against dataset_manifest.json."""
        manifest_path = _SECURE_DATA / "dataset_manifest.json"
        result = {
            "bridge_verified_count": self._state["bridge_verified_count"],
            "manifest_verified_count": 0,
            "manifest_exists": False,
            "consistency_ok": False,
            "mismatch_reason": None,
        }

        if not manifest_path.exists():
            result["mismatch_reason"] = "manifest_not_found"
            return result

        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            result["manifest_exists"] = True
            # Support both legacy and current manifest schemas.
            # Current ingestion manifests expose accepted/sample_count.
            result["manifest_verified_count"] = int(
                manifest.get(
                    "verified_count",
                    manifest.get(
                        "verified_samples",
                        manifest.get("accepted", manifest.get("sample_count", 0)),
                    ),
                )
            )

            bridge_v = self._state["bridge_verified_count"]
            manifest_v = result["manifest_verified_count"]

            # Allow small discrepancies (< 1%) for timing differences
            if bridge_v == 0 and manifest_v > 0:
                result["mismatch_reason"] = (
                    f"bridge=0 but manifest={manifest_v} — "
                    "bridge state not persisted or reset"
                )
            elif manifest_v == 0 and bridge_v > 0:
                result["mismatch_reason"] = (
                    f"manifest=0 but bridge={bridge_v} — "
                    "manifest not updated after ingest"
                )
            elif abs(bridge_v - manifest_v) > max(1, int(bridge_v * 0.01)):
                result["mismatch_reason"] = (
                    f"bridge={bridge_v} vs manifest={manifest_v} — "
                    f"delta={abs(bridge_v - manifest_v)}"
                )
            else:
                result["consistency_ok"] = True
        except Exception as e:
            result["mismatch_reason"] = f"manifest_read_error: {e}"

        return result

    def get_readiness(self) -> Dict[str, Any]:
        """Get authoritative readiness status with consistency check."""
        counts = self.get_counts()
        consistency = self.check_manifest_consistency()

        # Readiness: must have verified >= threshold AND consistency
        verified = counts["bridge_verified_count"]
        threshold = BRIDGE_THRESHOLD

        if verified >= threshold and consistency["consistency_ok"]:
            status = "GO"
            reason = (
                f"{verified} verified samples >= {threshold} threshold, "
                "bridge/manifest consistent"
            )
        elif verified >= threshold and not consistency["consistency_ok"]:
            status = "GO_WITH_WARNING"
            reason = (
                f"{verified} verified samples >= {threshold}, but: "
                f"{consistency['mismatch_reason']}"
            )
        else:
            status = "NO_GO"
            deficit = threshold - verified
            reason = (
                f"Insufficient: {verified}/{threshold} verified "
                f"(deficit: {deficit})"
            )

        return {
            **counts,
            "status": status,
            "reason": reason,
            "consistency": consistency,
        }


# =============================================================================
# SINGLETON
# =============================================================================

_bridge_state: Optional[BridgeState] = None


def get_bridge_state(state_path: Path = None) -> BridgeState:
    """Get or create the bridge state singleton."""
    global _bridge_state
    if _bridge_state is None:
        _bridge_state = BridgeState(state_path=state_path)
    return _bridge_state


def reset_bridge_state():
    """Reset the singleton (for testing)."""
    global _bridge_state
    _bridge_state = None
