import numpy as np


def test_post_epoch_audit_writes_truth_ledger(monkeypatch):
    from impl_v1.training.data.governance_pipeline import post_epoch_audit

    captured = {}

    def _fake_append(entry):
        captured["entry"] = entry
        return "hash-ok"

    monkeypatch.setattr(
        "impl_v1.training.data.training_truth_ledger.append_truth_entry",
        _fake_append,
    )

    result = post_epoch_audit(
        epoch=3,
        accuracy=0.91,
        holdout_accuracy=0.91,
        loss=0.12,
        train_accuracy=0.93,
        total_samples=128,
        dataset_hash="abc123",
        features=np.ones((8, 256), dtype=np.float32),
        labels=np.asarray([0, 1, 0, 1, 0, 1, 0, 1], dtype=np.int64),
    )

    assert result.truth_logged is True
    entry = captured["entry"]
    assert entry.dataset_hash == "abc123"
    assert entry.sample_count == 128
    assert entry.strict_real_mode is True
    assert entry.synthetic_blocked is True
    assert entry.verdict == "APPROVED"
