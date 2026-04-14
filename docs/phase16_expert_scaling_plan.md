# Phase 16 Expert Scaling Plan

## Tier schedule

| Day window | Target scale |
| --- | --- |
| Day 1-30 | 130M per expert |
| Day 31-90 | 512M per expert |
| Day 91-180 | 1B per expert |
| Day 181+ | 3B per expert |

## Repository-compatible depth mapping

The current repository expert checkpoints are classifier-path [`MoEClassifier`](impl_v1/phase49/moe/__init__.py:83) checkpoints, not language-model checkpoints with a literal `n_layers` field.

Phase 16 therefore defines expert depth using [`SingleExpert`](impl_v1/phase49/moe/expert.py:31):

- depth `1` = legacy `fc1 -> GELU -> Dropout -> fc2`
- depth `N > 1` = the legacy block plus `N - 1` residual [`depth_layers`](impl_v1/phase49/moe/expert.py:44)

## Scaling operation

[`scripts/scale_expert.py`](scripts/scale_expert.py) performs one forward scaling step by doubling `expert_depth`:

- `1 -> 2`
- `2 -> 4`
- `4 -> 8`
- additional invocations continue doubling as required by the operational plan

Existing weights are preserved and newly appended residual layers are zero-initialized so the scaled checkpoint stays function-preserving while exposing additional repository-compatible capacity.

## Checkpoint integrity requirements

Phase 16 scaling does not bypass checkpoint hardening:

- source checkpoints must pass SHA-256 verification via a `.sha256` sidecar
- scaled checkpoints are written with SafeTensors `tensor_hash` metadata
- scaled checkpoints emit a fresh `.sha256` sidecar after save

This keeps Phase 16 aligned with [`HardenedCheckpointManager`](impl_v1/training/checkpoints/checkpoint_hardening.py:68).
