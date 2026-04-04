# Distributed Training Foundation

This pass hardens the repo's checkpoint foundation without redesigning the training stack.

## Implemented

- `impl_v1/training/checkpoints/checkpoint_hardening.py`
  - Atomic sharded checkpoint layout under `checkpoint_root/global_step_<N>/`
  - SafeTensors model shards plus optimizer, RNG, scaler, and training-state artifacts
  - Async checkpoint writes
  - Latest and best checkpoint pointers
  - Validation and auto-resume from the latest valid checkpoint
  - Partial checkpoint recovery by skipping incomplete pointer targets

- `impl_v1/training/voice/stt_trainer.py`
  - Uses the hardened checkpoint manager for save/resume
  - Persists full training state instead of model-only snapshots
  - Waits for pending async writes before exit/resume

- `impl_v1/training/voice/stt_model.py`
  - Loads hardened checkpoints first
  - Falls back to legacy `.pt` checkpoints when needed

- `backend/training/stt_dataset_collector.py`
  - Reports latest/best checkpoint state from the hardened checkpoint store

## Not Yet Retrofitted

- `run_real_training.py`
  - Still needs checkpoint-manager integration and step-level resume coverage

- DeepSpeed / ZeRO / tensor parallel / pipeline parallel runtime
  - The checkpoint manager is ready to back those phases, but the execution engine has not been switched yet

## Recommended Next Steps

1. Wire `run_real_training.py` to `HardenedCheckpointManager` with step-aware `global_step` persistence.
2. Add a distributed engine adapter that maps topology detection into DeepSpeed ZeRO, tensor parallel, and pipeline parallel settings.
3. Extend checkpoint sync to local-NVMe plus background object-store replication.
4. Add node-failure recovery tests that rehydrate optimizer, scheduler, RNG, and scaler state after simulated worker loss.
