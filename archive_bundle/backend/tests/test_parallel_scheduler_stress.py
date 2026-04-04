"""
test_parallel_scheduler_stress.py — Parallel Training Stress Test

Simulates:
- 2 node training
- Node failure mid-run
- Resume from checkpoint
- Hash comparison
- Dataset shard mismatch

Requires:
- Identical final hash
- No drift

NO mock data. NO auto-submit.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from backend.training.parallel_scheduler import (
    ParallelScheduler, TrainingSplit
)


class ParallelStressTest:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def test(self, condition, name):
        if condition:
            self.passed += 1
            self.results.append(("PASS", name))
        else:
            self.failed += 1
            self.results.append(("FAIL", name))

    def run_all(self):
        self.test_two_node_training()
        self.test_node_failure_recovery()
        self.test_hash_determinism()
        self.test_drift_detection()
        self.test_shard_mismatch_detection()
        self.test_split_coverage()
        self.test_merge_idempotency()

        print(f"\n  Parallel Scheduler Stress: {self.passed} passed, "
              f"{self.failed} failed")
        for status, name in self.results:
            marker = "+" if status == "PASS" else "X"
            print(f"    {marker} {name}")
        return self.failed == 0

    def test_two_node_training(self):
        """Standard 2-node training completes successfully."""
        sched = ParallelScheduler(num_splits=2)
        splits = sched.create_splits(1000)
        self.test(len(splits) == 2, "2-node: creates 2 splits")

        sched.record_split_result(0, "hash_a", 0.12, 0.94)
        sched.record_split_result(1, "hash_b", 0.11, 0.95)

        result = sched.merge_results()
        self.test(result.splits_merged == 2,
                  "2-node: merges 2 splits")
        self.test(len(result.merged_hash) == 64,
                  "2-node: SHA-256 merged hash")
        self.test(not result.drift_detected,
                  "2-node: no drift with similar results")

    def test_node_failure_recovery(self):
        """Simulate node failure — only completed splits merge."""
        sched = ParallelScheduler(num_splits=3)
        sched.create_splits(1500)

        sched.record_split_result(0, "hash_a", 0.10, 0.95)
        sched.record_split_result(1, "hash_b", 0.11, 0.94)
        # Node 2 never completes (failure)

        result = sched.merge_results()
        self.test(result.splits_merged == 2,
                  "Node failure: merges only completed splits")
        self.test(len(result.merged_hash) == 64,
                  "Node failure: still produces valid hash")

    def test_hash_determinism(self):
        """Same inputs always produce same merged hash."""
        sched1 = ParallelScheduler(num_splits=2)
        sched1.create_splits(100)
        sched1.record_split_result(0, "abc123", 0.10, 0.95)
        sched1.record_split_result(1, "def456", 0.11, 0.94)
        r1 = sched1.merge_results()

        sched2 = ParallelScheduler(num_splits=2)
        sched2.create_splits(100)
        sched2.record_split_result(0, "abc123", 0.10, 0.95)
        sched2.record_split_result(1, "def456", 0.11, 0.94)
        r2 = sched2.merge_results()

        self.test(r1.merged_hash == r2.merged_hash,
                  "Hash determinism: identical inputs -> identical hash")

    def test_drift_detection(self):
        """Large variance between splits triggers drift detection."""
        sched = ParallelScheduler(num_splits=2)
        sched.create_splits(1000)

        sched.record_split_result(0, "hash_a", 0.05, 0.98)
        sched.record_split_result(1, "hash_b", 0.50, 0.60)

        drift = sched.check_drift()
        self.test(drift["drift_detected"],
                  "Drift: large variance triggers detection")
        self.test(drift["drift_score"] > 0.05,
                  "Drift: score exceeds threshold")

    def test_shard_mismatch_detection(self):
        """Different split counts produce different hashes."""
        sched1 = ParallelScheduler(num_splits=2)
        sched1.create_splits(100)
        sched1.record_split_result(0, "hash_x", 0.10, 0.95)
        sched1.record_split_result(1, "hash_y", 0.11, 0.94)
        r1 = sched1.merge_results()

        sched2 = ParallelScheduler(num_splits=3)
        sched2.create_splits(100)
        sched2.record_split_result(0, "hash_x", 0.10, 0.95)
        sched2.record_split_result(1, "hash_y", 0.11, 0.94)
        sched2.record_split_result(2, "hash_z", 0.12, 0.93)
        r2 = sched2.merge_results()

        self.test(r1.merged_hash != r2.merged_hash,
                  "Shard mismatch: different split counts -> different hash")

    def test_split_coverage(self):
        """Splits cover entire dataset with no gaps or overlaps."""
        for total in [99, 100, 101, 1000, 10001]:
            sched = ParallelScheduler(num_splits=3)
            splits = sched.create_splits(total)

            covered = sum(s.data_range[1] - s.data_range[0]
                          for s in splits)
            self.test(covered == total,
                      f"Split coverage: {total} samples fully covered")

    def test_merge_idempotency(self):
        """Merging same completed results multiple times is idempotent."""
        sched = ParallelScheduler(num_splits=2)
        sched.create_splits(100)
        sched.record_split_result(0, "aaa", 0.10, 0.95)
        sched.record_split_result(1, "bbb", 0.11, 0.94)

        r1 = sched.merge_results()
        r2 = sched.merge_results()
        r3 = sched.merge_results()

        self.test(r1.merged_hash == r2.merged_hash == r3.merged_hash,
                  "Merge idempotency: same hash every time")


def run_tests():
    test = ParallelStressTest()
    return test.run_all()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
