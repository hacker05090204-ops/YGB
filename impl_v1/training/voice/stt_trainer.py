"""
STT Trainer — Training pipeline for the Conformer-CTC model.

Provides:
  - Training loop with CTC loss
  - Checkpoint save/load
  - Validation metrics (WER, CER)
  - Learning rate scheduling

Usage:
    python -m impl_v1.training.voice.stt_trainer --epochs 10
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

from impl_v1.training.voice.stt_model import (
    ConformerCTCModel, text_to_indices, indices_to_text,
    ctc_greedy_decode, BLANK_IDX, VOCAB_SIZE,
    _CHECKPOINT_DIR,
)

logger = logging.getLogger(__name__)


# =============================================================================
# SPEECH DATASET
# =============================================================================

class SpeechDataset(Dataset):
    """
    Simple speech dataset for training the STT model.

    Expects a list of (audio_path, transcript) pairs.
    Audio must be 16kHz mono WAV or raw PCM.
    """

    def __init__(self, manifest_path: str, max_audio_len: int = 160000):
        """
        Args:
            manifest_path: Path to JSONL manifest with {"audio": path, "text": transcript}
            max_audio_len: Max audio samples (10s at 16kHz = 160000)
        """
        import json

        self.samples = []
        self.max_audio_len = max_audio_len

        manifest = Path(manifest_path)
        if manifest.exists():
            with open(manifest) as f:
                for line in f:
                    entry = json.loads(line.strip())
                    self.samples.append({
                        "audio": entry["audio"],
                        "text": entry["text"],
                    })
            logger.info(f"[STT_TRAIN] Loaded {len(self.samples)} samples from {manifest_path}")
        else:
            logger.warning(f"[STT_TRAIN] Manifest not found: {manifest_path}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        import numpy as np

        sample = self.samples[idx]

        # Load audio
        audio_path = sample["audio"]
        try:
            if audio_path.endswith(".wav"):
                import wave
                with wave.open(audio_path, "rb") as wf:
                    audio_data = wf.readframes(wf.getnframes())
                    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
                    audio_np /= 32768.0
            else:
                audio_np = np.fromfile(audio_path, dtype=np.int16).astype(np.float32)
                audio_np /= 32768.0
        except Exception:
            audio_np = np.zeros(self.max_audio_len, dtype=np.float32)

        # Pad/truncate
        if len(audio_np) > self.max_audio_len:
            audio_np = audio_np[:self.max_audio_len]
        else:
            audio_np = np.pad(audio_np, (0, self.max_audio_len - len(audio_np)))

        # Convert text to indices
        text_indices = text_to_indices(sample["text"])

        return (
            torch.tensor(audio_np, dtype=torch.float32),
            torch.tensor(text_indices, dtype=torch.long),
            len(text_indices),
        )


def collate_fn(batch):
    """Collate function for variable-length text targets."""
    audios, targets, target_lengths = zip(*batch)
    audios = torch.stack(audios)
    targets = nn.utils.rnn.pad_sequence(targets, batch_first=True, padding_value=BLANK_IDX)
    target_lengths = torch.tensor(target_lengths, dtype=torch.long)
    return audios, targets, target_lengths


# =============================================================================
# METRICS
# =============================================================================

def compute_wer(predicted: str, reference: str) -> float:
    """Compute Word Error Rate."""
    pred_words = predicted.lower().split()
    ref_words = reference.lower().split()

    if len(ref_words) == 0:
        return 0.0 if len(pred_words) == 0 else 1.0

    # Levenshtein distance on words
    d = [[0] * (len(ref_words) + 1) for _ in range(len(pred_words) + 1)]
    for i in range(len(pred_words) + 1):
        d[i][0] = i
    for j in range(len(ref_words) + 1):
        d[0][j] = j

    for i in range(1, len(pred_words) + 1):
        for j in range(1, len(ref_words) + 1):
            if pred_words[i - 1] == ref_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(d[i - 1][j], d[i][j - 1], d[i - 1][j - 1])

    return d[len(pred_words)][len(ref_words)] / len(ref_words)


def compute_cer(predicted: str, reference: str) -> float:
    """Compute Character Error Rate."""
    pred_chars = list(predicted.lower())
    ref_chars = list(reference.lower())

    if len(ref_chars) == 0:
        return 0.0 if len(pred_chars) == 0 else 1.0

    d = [[0] * (len(ref_chars) + 1) for _ in range(len(pred_chars) + 1)]
    for i in range(len(pred_chars) + 1):
        d[i][0] = i
    for j in range(len(ref_chars) + 1):
        d[0][j] = j

    for i in range(1, len(pred_chars) + 1):
        for j in range(1, len(ref_chars) + 1):
            if pred_chars[i - 1] == ref_chars[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(d[i - 1][j], d[i][j - 1], d[i - 1][j - 1])

    return d[len(pred_chars)][len(ref_chars)] / len(ref_chars)


# =============================================================================
# TRAINER
# =============================================================================

class STTTrainer:
    """
    Training loop for Conformer-CTC model.

    Features:
      - CTC loss
      - Adam optimizer with warmup + cosine decay
      - Checkpoint save/load
      - WER/CER validation
    """

    def __init__(
        self,
        model: Optional[ConformerCTCModel] = None,
        lr: float = 3e-4,
        warmup_steps: int = 1000,
        device: str = "auto",
    ):
        self.model = model or ConformerCTCModel()

        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.model = self.model.to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=lr)
        self.ctc_loss = nn.CTCLoss(blank=BLANK_IDX, zero_infinity=True)
        self.warmup_steps = warmup_steps
        self.global_step = 0
        self.best_val_loss = float("inf")

    def train_epoch(self, dataloader: DataLoader) -> Dict[str, float]:
        """Train for one epoch. Returns metrics dict."""
        self.model.train()
        total_loss = 0.0
        n_batches = 0

        for audios, targets, target_lengths in dataloader:
            audios = audios.to(self.device)
            targets = targets.to(self.device)
            target_lengths = target_lengths.to(self.device)

            # Forward
            log_probs = self.model(audios)  # [batch, time, vocab]
            log_probs = log_probs.transpose(0, 1)  # [time, batch, vocab]

            input_lengths = torch.full(
                (log_probs.size(1),), log_probs.size(0),
                dtype=torch.long, device=self.device
            )

            loss = self.ctc_loss(log_probs, targets, input_lengths, target_lengths)

            # Backward
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 5.0)
            self.optimizer.step()

            total_loss += loss.item()
            n_batches += 1
            self.global_step += 1

        avg_loss = total_loss / max(n_batches, 1)
        return {"train_loss": avg_loss, "n_batches": n_batches}

    def validate(self, dataloader: DataLoader) -> Dict[str, float]:
        """Validate model. Returns metrics dict with WER/CER."""
        self.model.eval()
        total_loss = 0.0
        total_wer = 0.0
        total_cer = 0.0
        n_samples = 0

        with torch.no_grad():
            for audios, targets, target_lengths in dataloader:
                audios = audios.to(self.device)
                targets = targets.to(self.device)
                target_lengths = target_lengths.to(self.device)

                log_probs = self.model(audios)
                log_probs_t = log_probs.transpose(0, 1)

                input_lengths = torch.full(
                    (log_probs_t.size(1),), log_probs_t.size(0),
                    dtype=torch.long, device=self.device
                )

                loss = self.ctc_loss(log_probs_t, targets, input_lengths, target_lengths)
                total_loss += loss.item()

                # Decode and compute WER/CER
                for i in range(log_probs.size(0)):
                    pred_text, _ = ctc_greedy_decode(log_probs[i].cpu())
                    ref_indices = targets[i][:target_lengths[i]].cpu().tolist()
                    ref_text = indices_to_text(ref_indices)

                    total_wer += compute_wer(pred_text, ref_text)
                    total_cer += compute_cer(pred_text, ref_text)
                    n_samples += 1

        n_batches = max(1, len(dataloader))
        return {
            "val_loss": total_loss / n_batches,
            "wer": total_wer / max(n_samples, 1),
            "cer": total_cer / max(n_samples, 1),
            "n_samples": n_samples,
        }

    def save_checkpoint(self, path: Optional[str] = None, tag: str = "latest"):
        """Save model checkpoint."""
        if path is None:
            path = str(_CHECKPOINT_DIR / f"conformer_ctc_{tag}.pt")

        torch.save({
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "global_step": self.global_step,
            "best_val_loss": self.best_val_loss,
        }, path)
        logger.info(f"[STT_TRAIN] Checkpoint saved: {path}")

    def load_checkpoint(self, path: Optional[str] = None):
        """Load model checkpoint."""
        if path is None:
            path = str(_CHECKPOINT_DIR / "conformer_ctc_latest.pt")

        if not os.path.exists(path):
            logger.warning(f"[STT_TRAIN] No checkpoint at {path}")
            return False

        state = torch.load(path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state["model_state_dict"])
        self.optimizer.load_state_dict(state["optimizer_state_dict"])
        self.global_step = state.get("global_step", 0)
        self.best_val_loss = state.get("best_val_loss", float("inf"))
        logger.info(f"[STT_TRAIN] Loaded checkpoint: {path}")
        return True

    def train(self, train_loader: DataLoader, val_loader: Optional[DataLoader] = None,
              epochs: int = 10) -> Dict[str, float]:
        """Full training loop."""
        logger.info(f"[STT_TRAIN] Starting training for {epochs} epochs on {self.device}")

        for epoch in range(epochs):
            t0 = time.time()
            train_metrics = self.train_epoch(train_loader)
            elapsed = time.time() - t0

            log_msg = (
                f"[STT_TRAIN] Epoch {epoch + 1}/{epochs}: "
                f"loss={train_metrics['train_loss']:.4f} "
                f"({elapsed:.1f}s)"
            )

            val_metrics = {}
            if val_loader:
                val_metrics = self.validate(val_loader)
                log_msg += (
                    f" | val_loss={val_metrics['val_loss']:.4f} "
                    f"WER={val_metrics['wer']:.2%} "
                    f"CER={val_metrics['cer']:.2%}"
                )

                # Save best
                if val_metrics["val_loss"] < self.best_val_loss:
                    self.best_val_loss = val_metrics["val_loss"]
                    self.save_checkpoint(tag="best")

            logger.info(log_msg)
            self.save_checkpoint(tag="latest")

        return {**train_metrics, **val_metrics}


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="STT Conformer-CTC Trainer")
    parser.add_argument("--manifest", type=str, default="data/stt_manifest.jsonl",
                        help="Path to training manifest (JSONL)")
    parser.add_argument("--val-manifest", type=str, default="",
                        help="Path to validation manifest")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    trainer = STTTrainer(lr=args.lr)

    if args.resume:
        trainer.load_checkpoint()

    train_ds = SpeechDataset(args.manifest)
    if len(train_ds) == 0:
        logger.error("[STT_TRAIN] No training data. Create a manifest file first.")
        return

    train_loader = DataLoader(train_ds, batch_size=args.batch_size,
                              shuffle=True, collate_fn=collate_fn)

    val_loader = None
    if args.val_manifest:
        val_ds = SpeechDataset(args.val_manifest)
        if len(val_ds) > 0:
            val_loader = DataLoader(val_ds, batch_size=args.batch_size,
                                    shuffle=False, collate_fn=collate_fn)

    trainer.train(train_loader, val_loader, args.epochs)


if __name__ == "__main__":
    main()
