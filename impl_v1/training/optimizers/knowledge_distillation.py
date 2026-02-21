"""
knowledge_distillation.py — Knowledge Distillation (Teacher → Student)

1. Train large teacher model once
2. Train smaller student to mimic teacher logits
3. KL divergence loss between teacher/student outputs

Goal: Maintain accuracy with 50% smaller model.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DistillationConfig:
    """Knowledge distillation configuration."""
    temperature: float = 4.0      # Softmax temperature
    alpha: float = 0.7            # Weight for distillation loss (vs hard label)
    student_hidden: int = 128     # Student hidden dim (smaller than teacher)
    teacher_hidden: int = 512     # Teacher hidden dim


def create_student_model(input_dim: int, num_classes: int = 2, hidden: int = 128):
    """Create a smaller student model.

    Student is ~50% the size of the teacher.

    Args:
        input_dim: Input feature dimension.
        num_classes: Number of output classes.
        hidden: Hidden layer dimension.

    Returns:
        Student model (nn.Module).
    """
    import torch.nn as nn

    model = nn.Sequential(
        nn.Linear(input_dim, hidden),
        nn.ReLU(),
        nn.Dropout(0.2),
        nn.Linear(hidden, hidden // 2),
        nn.ReLU(),
        nn.Linear(hidden // 2, num_classes),
    )

    params = sum(p.numel() for p in model.parameters())
    logger.info(f"[DISTILL] Student created: {params:,} params, hidden={hidden}")
    return model


def create_teacher_model(input_dim: int, num_classes: int = 2, hidden: int = 512):
    """Create a larger teacher model.

    Args:
        input_dim: Input feature dimension.
        num_classes: Number of output classes.
        hidden: Hidden layer dimension.

    Returns:
        Teacher model (nn.Module).
    """
    import torch.nn as nn

    model = nn.Sequential(
        nn.Linear(input_dim, hidden),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(hidden, hidden // 2),
        nn.ReLU(),
        nn.Dropout(0.2),
        nn.Linear(hidden // 2, hidden // 4),
        nn.ReLU(),
        nn.Linear(hidden // 4, num_classes),
    )

    params = sum(p.numel() for p in model.parameters())
    logger.info(f"[DISTILL] Teacher created: {params:,} params, hidden={hidden}")
    return model


def distillation_loss(
    student_logits,
    teacher_logits,
    labels,
    temperature: float = 4.0,
    alpha: float = 0.7,
):
    """Compute knowledge distillation loss.

    Loss = alpha * KL_div(student_soft, teacher_soft) + (1-alpha) * CE(student, labels)

    Args:
        student_logits: Student model output (before softmax).
        teacher_logits: Teacher model output (before softmax).
        labels: Ground truth labels.
        temperature: Softmax temperature (higher = softer).
        alpha: Weight for distillation loss.

    Returns:
        Combined loss tensor.
    """
    import torch
    import torch.nn.functional as F

    # Soft targets from teacher
    soft_teacher = F.softmax(teacher_logits / temperature, dim=1)
    soft_student = F.log_softmax(student_logits / temperature, dim=1)

    # KL divergence (scaled by T^2 as per Hinton et al.)
    kl_loss = F.kl_div(
        soft_student, soft_teacher,
        reduction='batchmean',
    ) * (temperature ** 2)

    # Hard label cross-entropy
    ce_loss = F.cross_entropy(student_logits, labels)

    # Combined loss
    total = alpha * kl_loss + (1.0 - alpha) * ce_loss

    return total


def train_student(
    teacher,
    student,
    train_loader,
    device,
    epochs: int = 10,
    lr: float = 0.001,
    temperature: float = 4.0,
    alpha: float = 0.7,
) -> dict:
    """Train student via knowledge distillation.

    Args:
        teacher: Trained teacher model (frozen).
        student: Student model to train.
        train_loader: Training data.
        device: torch.device.
        epochs: Training epochs.
        lr: Learning rate.
        temperature: Distillation temperature.
        alpha: Distillation loss weight.

    Returns:
        Training metrics dict.
    """
    import torch
    import torch.optim as optim
    import time

    teacher.eval()
    student.train()

    optimizer = optim.Adam(student.parameters(), lr=lr)
    best_acc = 0.0

    t0 = time.perf_counter()
    for epoch in range(epochs):
        total_loss = 0.0
        correct = 0
        total = 0

        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device, non_blocking=True)
            batch_y = batch_y.to(device, non_blocking=True)

            # Teacher forward (no grad)
            with torch.no_grad():
                teacher_out = teacher(batch_x)

            # Student forward
            student_out = student(batch_x)

            # Distillation loss
            loss = distillation_loss(
                student_out, teacher_out, batch_y,
                temperature=temperature, alpha=alpha,
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item() * batch_y.size(0)
            _, preds = torch.max(student_out.data, 1)
            correct += (preds == batch_y).sum().item()
            total += batch_y.size(0)

        acc = correct / max(total, 1)
        avg_loss = total_loss / max(total, 1)
        best_acc = max(best_acc, acc)

        logger.info(
            f"[DISTILL] Epoch {epoch+1}: loss={avg_loss:.4f}, "
            f"acc={acc:.4f}"
        )

    elapsed = time.perf_counter() - t0
    teacher_params = sum(p.numel() for p in teacher.parameters())
    student_params = sum(p.numel() for p in student.parameters())

    result = {
        'teacher_params': teacher_params,
        'student_params': student_params,
        'compression_ratio': round(teacher_params / max(student_params, 1), 2),
        'best_accuracy': best_acc,
        'final_loss': avg_loss,
        'training_time_sec': round(elapsed, 2),
        'epochs': epochs,
    }

    logger.info(
        f"[DISTILL] Complete: {result['compression_ratio']}x compression, "
        f"acc={best_acc:.4f}"
    )

    return result
