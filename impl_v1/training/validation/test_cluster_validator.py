import json

from impl_v1.training.validation import cluster_validator


def test_validate_overfit_uses_real_training_report(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    report_path = reports_dir / "training_session_result.json"
    report_path.write_text(
        json.dumps(
            {
                "epoch_reports": [
                    {"epoch": 1, "train_acc": 0.70, "test_acc": 0.68},
                    {"epoch": 2, "train_acc": 0.78, "test_acc": 0.75},
                    {"epoch": 3, "train_acc": 0.83, "test_acc": 0.80},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cluster_validator, "PROJECT_ROOT", tmp_path)

    result = cluster_validator._validate_overfit()

    assert result.passed is True
    assert "training_session_result.json" in result.details
    assert "recent_max_gap=0.0300" in result.details


def test_validate_overfit_fails_closed_without_real_report(tmp_path, monkeypatch):
    monkeypatch.setattr(cluster_validator, "PROJECT_ROOT", tmp_path)

    result = cluster_validator._validate_overfit()

    assert result.passed is False
    assert "No real training generalization report available" in result.details
