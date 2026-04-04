import os

import pytest

from impl_v1.training.distributed.distributed_training_orchestrator import (
    DistributedTrainingOrchestrator,
    NodeResource,
    TrainingSnapshot,
    ValidationSnapshot,
)


def _make_training(
    *,
    epoch: int = 1,
    step: int = 1000,
    loss: float = 0.80,
    val_loss: float = 0.78,
    accuracy: float = 0.60,
    benchmark_score: float = 0.58,
    dataset_size: int = 10_000_000,
    elapsed_sec: float = 1800.0,
    config_hash: str = "cfg",
    plateau_count: int = 0,
):
    return TrainingSnapshot(
        epoch=epoch,
        step=step,
        loss=loss,
        val_loss=val_loss,
        accuracy=accuracy,
        benchmark_score=benchmark_score,
        dataset_size=dataset_size,
        elapsed_sec=elapsed_sec,
        config_hash=config_hash,
        plateau_count=plateau_count,
    )


def _make_validation(
    *,
    loss: float = 0.78,
    accuracy: float = 0.60,
    benchmark_score: float = 0.58,
    overfit_gap: float = 0.02,
    regression_detected: bool = False,
):
    return ValidationSnapshot(
        loss=loss,
        accuracy=accuracy,
        benchmark_score=benchmark_score,
        overfit_gap=overfit_gap,
        regression_detected=regression_detected,
    )


class TestDistributedTrainingOrchestrator:
    def test_bootstrap_initializes_23_agents_at_3b(self, tmp_path):
        orch = DistributedTrainingOrchestrator(
            state_path=str(tmp_path / "orch_state.json"),
            checkpoint_dir=str(tmp_path / "checkpoints"),
        )

        agents = orch.get_agent_registry()
        assert orch.current_stage.version_tag == "v1_base_3B"
        assert len(agents) == 23
        assert agents[0].parameter_count == pytest.approx(3_000_000_000 / 23, rel=0.01)

    def test_checkpoint_policy_tracks_latest_and_best_pointers(self, tmp_path):
        orch = DistributedTrainingOrchestrator(
            state_path=str(tmp_path / "orch_state.json"),
            checkpoint_dir=str(tmp_path / "checkpoints"),
        )

        training_a = _make_training()
        validation_a = _make_validation()
        ckpt_a = orch.record_checkpoint(training_a, validation_a, now=1800.0)
        assert ckpt_a is not None
        assert ckpt_a.checkpoint_kind == "full"
        assert orch.latest_checkpoint_id == ckpt_a.checkpoint_id
        assert orch.best_checkpoint_id == ckpt_a.checkpoint_id
        assert os.path.exists(ckpt_a.manifest_path)

        training_b = _make_training(step=1500, loss=0.795, accuracy=0.601)
        validation_b = _make_validation(loss=0.779, accuracy=0.601)
        decision_b = orch.evaluate_checkpoint_need(training_b, validation_b, now=1900.0)
        assert decision_b.should_checkpoint is False

        training_c = _make_training(step=2500, loss=0.79, accuracy=0.605)
        validation_c = _make_validation(loss=0.775, accuracy=0.605)
        ckpt_c = orch.record_checkpoint(training_c, validation_c, now=2100.0)
        assert ckpt_c is not None
        assert ckpt_c.checkpoint_kind == "delta"
        assert orch.latest_checkpoint_id == ckpt_c.checkpoint_id
        assert orch.best_checkpoint_id == ckpt_c.checkpoint_id

    def test_scaling_decision_and_apply_scale(self, tmp_path):
        orch = DistributedTrainingOrchestrator(
            state_path=str(tmp_path / "orch_state.json"),
            checkpoint_dir=str(tmp_path / "checkpoints"),
        )
        orch.register_node(
            NodeResource(
                node_id="node-a",
                gpu_count=4,
                total_vram_gb=96,
                available_vram_gb=64,
                gpu_utilization=0.82,
                disk_io_mb_s=1200,
                network_gbps=100,
                supports_bf16=True,
            )
        )
        orch.register_node(
            NodeResource(
                node_id="node-b",
                gpu_count=4,
                total_vram_gb=96,
                available_vram_gb=64,
                gpu_utilization=0.79,
                disk_io_mb_s=1180,
                network_gbps=100,
                supports_bf16=True,
            )
        )

        base_training = _make_training(step=1000, loss=0.70, accuracy=0.88)
        base_validation = _make_validation(loss=0.69, accuracy=0.88, benchmark_score=0.87)
        orch.record_checkpoint(base_training, base_validation, now=1800.0)

        scale_training = _make_training(
            epoch=4,
            step=4000,
            loss=0.68,
            accuracy=0.92,
            benchmark_score=0.91,
            dataset_size=400_000_000,
            plateau_count=4,
        )
        scale_validation = _make_validation(loss=0.67, accuracy=0.92, benchmark_score=0.91)
        decision = orch.evaluate_scaling(scale_training, scale_validation)

        assert decision.should_scale is True
        assert decision.target_version == "v2_scaled_30B"
        assert "compute_available" in decision.reasons
        assert "loss_plateau" in decision.reasons

        orch.apply_scale(decision)
        assert orch.current_stage.version_tag == "v2_scaled_30B"
        assert len(orch.get_agent_registry()) == 48
        assert orch.get_agent_registry()[0].precision == "bf16"

    def test_validation_degradation_rolls_back_to_best_checkpoint(self, tmp_path):
        orch = DistributedTrainingOrchestrator(
            state_path=str(tmp_path / "orch_state.json"),
            checkpoint_dir=str(tmp_path / "checkpoints"),
        )
        orch.register_node(
            NodeResource(
                node_id="node-a",
                gpu_count=2,
                total_vram_gb=48,
                available_vram_gb=32,
                gpu_utilization=0.75,
                disk_io_mb_s=900,
                network_gbps=40,
                supports_bf16=True,
            )
        )

        best_training = _make_training(loss=0.55, accuracy=0.91, benchmark_score=0.90)
        best_validation = _make_validation(loss=0.54, accuracy=0.91, benchmark_score=0.90)
        best_ckpt = orch.record_checkpoint(best_training, best_validation, now=1800.0)
        assert best_ckpt is not None

        degraded_training = _make_training(step=2000, loss=0.72, accuracy=0.82)
        degraded_validation = _make_validation(
            loss=0.70,
            accuracy=0.82,
            benchmark_score=0.79,
            overfit_gap=0.15,
            regression_detected=True,
        )
        action = orch.register_validation(degraded_training, degraded_validation)

        assert action is not None
        assert action.action == "rollback_to_best"
        assert action.checkpoint_id == best_ckpt.checkpoint_id

    def test_node_failure_rebalances_and_keeps_knowledge_sync_plan(self, tmp_path):
        orch = DistributedTrainingOrchestrator(
            state_path=str(tmp_path / "orch_state.json"),
            checkpoint_dir=str(tmp_path / "checkpoints"),
        )
        orch.register_node(
            NodeResource(
                node_id="node-a",
                gpu_count=4,
                total_vram_gb=96,
                available_vram_gb=80,
                gpu_utilization=0.70,
                disk_io_mb_s=1000,
                network_gbps=80,
                supports_bf16=True,
            )
        )
        orch.register_node(
            NodeResource(
                node_id="node-b",
                gpu_count=4,
                total_vram_gb=96,
                available_vram_gb=72,
                gpu_utilization=0.74,
                disk_io_mb_s=980,
                network_gbps=80,
                supports_bf16=True,
            )
        )

        for index, agent in enumerate(orch.get_agent_registry()):
            orch.update_agent_metrics(
                agent.agent_id,
                task_success_rate=max(0.1, 0.95 - (index * 0.02)),
                benchmark_score=max(0.1, 0.93 - (index * 0.015)),
                validation_gain=max(0.0, 0.10 - (index * 0.005)),
                last_loss=0.20 + (index * 0.01),
                last_sync_step=100 * (index + 1),
            )

        plan = orch.build_knowledge_sharing_plan()
        assert plan.distillation_pairs
        assert len(plan.averaging_group) == 4

        training = _make_training(loss=0.60, accuracy=0.87, benchmark_score=0.85)
        validation = _make_validation(loss=0.59, accuracy=0.87, benchmark_score=0.85)
        orch.record_checkpoint(training, validation, now=1800.0)

        action = orch.handle_node_failure("node-b")
        assert action.action == "resume_from_latest"
        assert "node-a" in action.redistributed_nodes
        assert "node-b" not in action.redistributed_nodes
        assert action.parallelism is not None
        assert action.parallelism["healthy_gpus"] == 4
