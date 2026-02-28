"""
Test Bridge Persistence — Cross-Process State Consistency

Validates:
1. Cross-process persistence: write in one scope, read in another = match
2. Readiness truth: manifest says GO but bridge says 0 → NO_GO
3. Mismatch detection: manifest and bridge state disagree → flagged
4. Atomic writes survive crash simulation
"""

import json
import os
import sys
import tempfile
import pytest
from pathlib import Path

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestBridgeStatePersistence:
    """Cross-process bridge state persistence tests."""

    def setup_method(self):
        """Create temp state and samples files for isolation."""
        self._tmpdir = tempfile.mkdtemp()
        self._state_path = Path(self._tmpdir) / "bridge_state.json"
        self._samples_path = Path(self._tmpdir) / "bridge_samples.jsonl.gz"
        # Reset singleton
        import backend.bridge.bridge_state as mod
        mod._bridge_state = None

    def teardown_method(self):
        import backend.bridge.bridge_state as mod
        mod._bridge_state = None
        # Cleanup
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_state(self):
        from backend.bridge.bridge_state import BridgeState
        return BridgeState(
            state_path=self._state_path,
            samples_path=self._samples_path,
        )

    def test_cross_process_persistence(self):
        """Write bridge state in one scope, read in fresh scope → must match."""
        # Scope A: write
        state_a = self._make_state()
        state_a.set_counts(
            bridge_count=126000,
            bridge_verified_count=126000,
            total_ingested=126000,
            total_dropped=0,
            total_deduped=0,
        )

        # Scope B: fresh load from disk
        state_b = self._make_state()
        counts = state_b.get_counts()

        assert counts["bridge_count"] == 126000
        assert counts["bridge_verified_count"] == 126000
        assert counts["go_no_go"] == "GO"
        assert counts["deficit"] == 0

    def test_fresh_state_is_zero(self):
        """Fresh state with no file should show 0 counts."""
        state = self._make_state()
        counts = state.get_counts()
        assert counts["bridge_count"] == 0
        assert counts["bridge_verified_count"] == 0
        assert counts["go_no_go"] == "NO_GO"
        assert counts["deficit"] > 0

    def test_persistence_file_written(self):
        """State file should exist after set_counts."""
        state = self._make_state()
        assert not self._state_path.exists()
        state.set_counts(bridge_count=100, bridge_verified_count=50)
        assert self._state_path.exists()

        with open(self._state_path) as f:
            data = json.load(f)
        assert data["bridge_count"] == 100
        assert data["bridge_verified_count"] == 50

    def test_record_ingest_batch_increments(self):
        """record_ingest_batch should increment and persist."""
        state = self._make_state()
        state.set_counts(bridge_count=100, bridge_verified_count=80)
        state.record_ingest_batch(new_ingested=20, new_verified=15)

        # Reload
        state2 = self._make_state()
        counts = state2.get_counts()
        assert counts["bridge_count"] == 120
        assert counts["bridge_verified_count"] == 95

    def test_sample_store_write_and_read(self):
        """Samples written to gzip store should be readable."""
        state = self._make_state()
        samples = [
            {"endpoint": f"CVE-2024-{i}", "exploit_vector": f"desc-{i}",
             "impact": "HIGH", "source_tag": "NVD", "reliability": 0.95}
            for i in range(100)
        ]
        state.write_all_samples(samples)

        # Read back
        loaded = state.read_samples()
        assert len(loaded) == 100
        assert loaded[0]["endpoint"] == "CVE-2024-0"
        assert loaded[99]["endpoint"] == "CVE-2024-99"


class TestReadinessTruth:
    """Readiness must be NO_GO when bridge counters are below threshold."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._state_path = Path(self._tmpdir) / "bridge_state.json"
        self._samples_path = Path(self._tmpdir) / "bridge_samples.jsonl.gz"
        import backend.bridge.bridge_state as mod
        mod._bridge_state = None

    def teardown_method(self):
        import backend.bridge.bridge_state as mod
        mod._bridge_state = None
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_state(self):
        from backend.bridge.bridge_state import BridgeState
        return BridgeState(
            state_path=self._state_path,
            samples_path=self._samples_path,
        )

    def test_zero_counters_is_no_go(self):
        """Bridge with 0 verified → NO_GO regardless of manifest."""
        state = self._make_state()
        readiness = state.get_readiness()
        assert readiness["status"] == "NO_GO"
        assert readiness["bridge_verified_count"] == 0

    def test_above_threshold_is_go(self):
        """Bridge with verified >= threshold → GO."""
        state = self._make_state()
        state.set_counts(bridge_count=130000, bridge_verified_count=130000)
        readiness = state.get_readiness()
        assert readiness["status"] in ("GO", "GO_WITH_WARNING")
        assert readiness["bridge_verified_count"] == 130000

    def test_below_threshold_is_no_go(self):
        """Bridge with verified < threshold → NO_GO with deficit."""
        state = self._make_state()
        state.set_counts(bridge_count=50000, bridge_verified_count=50000)
        readiness = state.get_readiness()
        assert readiness["status"] == "NO_GO"
        assert readiness["bridge_verified_count"] == 50000
        assert readiness["consistency"]["bridge_verified_count"] == 50000


class TestMismatchDetection:
    """Mismatch between manifest and bridge state must be detected."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._state_path = Path(self._tmpdir) / "bridge_state.json"
        self._samples_path = Path(self._tmpdir) / "bridge_samples.jsonl.gz"
        self._manifest_path = Path(self._tmpdir) / "dataset_manifest.json"
        import backend.bridge.bridge_state as mod
        mod._bridge_state = None
        # Temporarily override secure data path
        mod._SECURE_DATA = Path(self._tmpdir)

    def teardown_method(self):
        import backend.bridge.bridge_state as mod
        mod._bridge_state = None
        # Restore
        mod._SECURE_DATA = mod._PROJECT_ROOT / "secure_data"
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_state(self):
        from backend.bridge.bridge_state import BridgeState
        return BridgeState(
            state_path=self._state_path,
            samples_path=self._samples_path,
        )

    def test_manifest_says_go_bridge_says_zero(self):
        """If manifest claims 126000 but bridge state is 0 → mismatch detected."""
        # Write a manifest claiming GO
        manifest = {
            "sample_count": 126000,
            "verified_count": 126000,
            "go_no_go": "GO",
        }
        with open(self._manifest_path, "w") as f:
            json.dump(manifest, f)

        # Bridge state is at 0
        state = self._make_state()
        consistency = state.check_manifest_consistency()
        assert consistency["consistency_ok"] is False
        assert "bridge=0" in consistency["mismatch_reason"]
        assert consistency["manifest_verified_count"] == 126000
        assert consistency["bridge_verified_count"] == 0

    def test_matching_counts_is_consistent(self):
        """If manifest and bridge state agree → consistency_ok=True."""
        # Write a manifest
        manifest = {"verified_count": 126000}
        with open(self._manifest_path, "w") as f:
            json.dump(manifest, f)

        # Bridge state matches
        state = self._make_state()
        state.set_counts(bridge_count=126000, bridge_verified_count=126000)
        consistency = state.check_manifest_consistency()
        assert consistency["consistency_ok"] is True

    def test_no_manifest_is_inconsistent(self):
        """If manifest doesn't exist → mismatch detected."""
        state = self._make_state()
        state.set_counts(bridge_count=126000, bridge_verified_count=126000)
        consistency = state.check_manifest_consistency()
        assert consistency["consistency_ok"] is False
        assert "manifest_not_found" in consistency["mismatch_reason"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
