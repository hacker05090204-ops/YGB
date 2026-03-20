from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DeepSpeedRuntimeConfig:
    enabled: bool = False
    zero_stage: int = 2
    bf16: bool = True
    gradient_accumulation_steps: int = 1
    gradient_clipping: float = 1.0
    offload_optimizer_device: str = "none"
    offload_param_device: str = "none"
    logging_steps: int = 10


class CompatEngine:
    """Controller-compatible fallback when DeepSpeed is unavailable."""

    def __init__(self, model: Any, optimizer: Any, scheduler: Any = None):
        self.module = model
        self.optimizer = optimizer
        self.lr_scheduler = scheduler

    def train(self) -> None:
        self.module.train()

    def eval(self) -> None:
        self.module.eval()

    def zero_grad(self) -> None:
        self.optimizer.zero_grad(set_to_none=True)

    def backward(self, loss: Any) -> None:
        loss.backward()

    def step(self) -> None:
        self.optimizer.step()


class DeepSpeedRuntime:
    def __init__(self, config: DeepSpeedRuntimeConfig):
        self.config = config
        self.available = False
        self._deepspeed = None
        if config.enabled:
            try:
                import deepspeed  # type: ignore

                self.available = True
                self._deepspeed = deepspeed
            except Exception as exc:  # pragma: no cover
                logger.warning("[DEEPSPEED] unavailable, falling back to native optimizer: %s", exc)

    def build_config(self, train_batch_size: int) -> Dict[str, Any]:
        zero_stage = 3 if int(self.config.zero_stage) >= 3 else 2
        return {
            "train_batch_size": train_batch_size,
            "gradient_accumulation_steps": max(1, int(self.config.gradient_accumulation_steps)),
            "gradient_clipping": float(self.config.gradient_clipping),
            "bf16": {"enabled": bool(self.config.bf16)},
            "fp16": {"enabled": False},
            "zero_optimization": {
                "stage": zero_stage,
                "contiguous_gradients": True,
                "overlap_comm": True,
                "reduce_scatter": True,
                "allgather_partitions": True,
                "offload_optimizer": {"device": self.config.offload_optimizer_device},
                "offload_param": {"device": self.config.offload_param_device},
            },
            "steps_per_print": max(1, int(self.config.logging_steps)),
        }

    def initialize(
        self,
        *,
        model: Any,
        optimizer: Any,
        scheduler: Any,
        model_parameters: Any,
        train_batch_size: int,
    ) -> Tuple[Any, Any, Any, Optional[Any]]:
        if not self.available or not self.config.enabled:
            return CompatEngine(model, optimizer, scheduler), optimizer, None, scheduler

        engine, optimizer, _, scheduler = self._deepspeed.initialize(
            model=model,
            optimizer=optimizer,
            lr_scheduler=scheduler,
            model_parameters=model_parameters,
            config=self.build_config(train_batch_size=train_batch_size),
        )
        logger.info("[DEEPSPEED] initialized ZeRO stage %s", self.build_config(train_batch_size)["zero_optimization"]["stage"])
        return engine, optimizer, None, scheduler
