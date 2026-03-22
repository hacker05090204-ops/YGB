"""Public exports for async ingestion."""

import logging

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.async_ingestor import AsyncIngestor, IngestCycleResult, run_ingestion_cycle
from backend.ingestion.models import IngestedSample

logger = logging.getLogger("ygb.ingestion")

__all__ = [
    "AsyncIngestor",
    "IngestCycleResult",
    "IngestedSample",
    "run_ingestion_cycle",
]

MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
