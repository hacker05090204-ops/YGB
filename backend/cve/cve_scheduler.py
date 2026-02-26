"""
CVE Ingest Scheduler — 5-Minute Polling with SLO Tracking

Runs every 5 minutes (configurable via CVE_INGEST_INTERVAL_SECONDS).
Per-source circuit breaker, retry with exponential backoff.
Idempotent ingestion with content-hash dedup.
SLO tracking: 99.5% ingest success, 99.9% job execution.
"""

import asyncio
import logging
import os
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("ygb.cve_scheduler")

_INGEST_INTERVAL = int(os.environ.get("CVE_INGEST_INTERVAL_SECONDS", "300"))
_MAX_RETRIES = 3
_BACKOFF_BASE = 30  # seconds


class CVEIngestScheduler:
    """Async scheduler for CVE feed ingestion every 5 minutes."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_run_at: Optional[str] = None
        self._consecutive_failures: int = 0
        self._total_runs: int = 0
        self._successful_runs: int = 0

    @property
    def interval_seconds(self) -> int:
        return _INGEST_INTERVAL

    @property
    def is_running(self) -> bool:
        return self._running

    def get_health(self) -> Dict[str, Any]:
        """Get scheduler health status."""
        return {
            "running": self._running,
            "interval_seconds": _INGEST_INTERVAL,
            "last_run_at": self._last_run_at,
            "total_runs": self._total_runs,
            "successful_runs": self._successful_runs,
            "consecutive_failures": self._consecutive_failures,
            "job_execution_rate": round(
                self._successful_runs / max(1, self._total_runs), 4
            ),
            "slo_target_job": 0.999,
            "slo_target_ingest": 0.995,
        }

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            logger.warning("[CVE_SCHEDULER] Already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"[CVE_SCHEDULER] Started (interval={_INGEST_INTERVAL}s)"
        )

    async def stop(self):
        """Stop the scheduler loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[CVE_SCHEDULER] Stopped")

    async def _run_loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                await self._execute_ingest_cycle()
            except Exception as e:
                logger.error(f"[CVE_SCHEDULER] Cycle error: {e}")
                self._consecutive_failures += 1

            try:
                await asyncio.sleep(_INGEST_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _execute_ingest_cycle(self):
        """Execute one full ingest cycle across all sources."""
        from backend.cve.cve_pipeline import get_pipeline, _SOURCE_CONFIGS

        pipeline = get_pipeline()
        self._total_runs += 1
        self._last_run_at = datetime.now(timezone.utc).isoformat()
        cycle_success = True

        logger.info(
            f"[CVE_SCHEDULER] Ingest cycle #{self._total_runs} starting"
        )

        for source_id in _SOURCE_CONFIGS:
            if not pipeline.can_fetch_source(source_id):
                logger.info(
                    f"[CVE_SCHEDULER] Skipping {source_id} "
                    f"(circuit breaker open)"
                )
                continue

            status = pipeline._source_status.get(source_id)
            from backend.cve.cve_pipeline import SourceStatus
            if status == SourceStatus.NOT_CONFIGURED:
                continue

            success = await self._fetch_source_with_retry(
                pipeline, source_id
            )
            if not success:
                cycle_success = False

        pipeline.record_job_execution(cycle_success)

        if cycle_success:
            self._successful_runs += 1
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

        logger.info(
            f"[CVE_SCHEDULER] Cycle #{self._total_runs} complete "
            f"(success={cycle_success})"
        )

    async def _fetch_source_with_retry(
        self, pipeline, source_id: str
    ) -> bool:
        """Fetch from a single source with retry/backoff."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = await self._fetch_source(pipeline, source_id)
                return result
            except Exception as e:
                backoff = _BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    f"[CVE_SCHEDULER] {source_id} attempt {attempt}/"
                    f"{_MAX_RETRIES} failed: {e}. "
                    f"Backoff {backoff}s"
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(backoff)

        pipeline.mark_source_error(
            source_id,
            f"All {_MAX_RETRIES} retries exhausted",
        )
        return False

    async def _fetch_source(self, pipeline, source_id: str) -> bool:
        """Fetch actual data from a source. Returns True on success."""
        try:
            import httpx
        except ImportError:
            pipeline.mark_source_error(
                source_id, "httpx not installed"
            )
            return False

        from backend.cve.cve_pipeline import _SOURCE_CONFIGS
        cfg = _SOURCE_CONFIGS[source_id]
        url = cfg["url"]

        # Build request headers with watermark
        headers = {"Accept": "application/json"}
        freshness = pipeline._freshness.get(source_id)
        if freshness:
            if freshness.last_etag:
                headers["If-None-Match"] = freshness.last_etag
            if freshness.last_modified_header:
                headers["If-Modified-Since"] = freshness.last_modified_header

        # Add API key if configured
        key_env = cfg.get("key_env", "")
        if key_env:
            key_val = os.environ.get(key_env, "")
            if key_val:
                headers["apiKey"] = key_val

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=headers)

                # 304 Not Modified → NO_DELTA
                if resp.status_code == 304:
                    pipeline.mark_source_no_delta(source_id)
                    logger.info(
                        f"[CVE_SCHEDULER] {source_id}: NO_DELTA (304)"
                    )
                    return True

                resp.raise_for_status()

                # Extract watermark headers
                etag = resp.headers.get("ETag", "")
                last_mod = resp.headers.get("Last-Modified", "")

                data = resp.json()
                records_ingested = self._parse_and_ingest(
                    pipeline, source_id, data
                )

                pipeline.mark_source_success(
                    source_id, records_ingested,
                    etag=etag,
                    last_modified_header=last_mod,
                )
                return True

        except httpx.HTTPStatusError as e:
            pipeline.mark_source_error(
                source_id, f"HTTP {e.response.status_code}"
            )
            return False
        except Exception as e:
            pipeline.mark_source_error(source_id, str(e))
            return False

    def _parse_and_ingest(
        self, pipeline, source_id: str, data: Any
    ) -> int:
        """Parse API response and ingest records. Returns count."""
        from backend.cve.cve_pipeline import IngestResult
        count = 0

        # Handle different source formats
        if source_id == "cisa_kev":
            vulns = data.get("vulnerabilities", [])
            for v in vulns:
                cve_id = v.get("cveID", "")
                if not cve_id:
                    continue
                record, result = pipeline.ingest_record(
                    cve_id=cve_id,
                    title=v.get("vulnerabilityName", ""),
                    description=v.get("shortDescription", ""),
                    severity="HIGH",
                    cvss_score=None,
                    affected_products=[
                        f"{v.get('vendorProject', '')}/"
                        f"{v.get('product', '')}"
                    ],
                    references=[],
                    is_exploited=True,
                    source_id=source_id,
                    raw_data=json.dumps(v),
                )
                if result != IngestResult.DUPLICATE:
                    count += 1

        elif source_id in ("nvd", "cve_services"):
            vulns = data.get("vulnerabilities", data.get("cveRecords", []))
            if isinstance(vulns, list):
                for item in vulns:
                    cve_data = item.get("cve", item)
                    cve_id = cve_data.get("id", cve_data.get("cveId", ""))
                    if not cve_id:
                        continue

                    # Extract CVSS
                    metrics = cve_data.get("metrics", {})
                    cvss3 = metrics.get("cvssMetricV31", [{}])
                    cvss_score = None
                    severity = "UNKNOWN"
                    if cvss3 and isinstance(cvss3, list) and len(cvss3) > 0:
                        cvss_data = cvss3[0].get("cvssData", {})
                        cvss_score = cvss_data.get("baseScore")
                        severity = cvss_data.get(
                            "baseSeverity", "UNKNOWN"
                        ).upper()

                    descs = cve_data.get("descriptions", [])
                    desc = ""
                    for d in descs:
                        if d.get("lang") == "en":
                            desc = d.get("value", "")
                            break

                    record, result = pipeline.ingest_record(
                        cve_id=cve_id,
                        title=cve_id,
                        description=desc,
                        severity=severity,
                        cvss_score=cvss_score,
                        affected_products=[],
                        references=[],
                        is_exploited=False,
                        source_id=source_id,
                        raw_data=json.dumps(item),
                        last_modified=cve_data.get("lastModified", ""),
                    )
                    if result != IngestResult.DUPLICATE:
                        count += 1

        else:
            # Generic: try to extract from list
            items = data if isinstance(data, list) else data.get(
                "results", data.get("data", [])
            )
            if isinstance(items, list):
                for item in items:
                    cve_id = (
                        item.get("cve_id") or item.get("id") or
                        item.get("cveId", "")
                    )
                    if not cve_id:
                        continue
                    record, result = pipeline.ingest_record(
                        cve_id=cve_id,
                        title=item.get("title", cve_id),
                        description=item.get(
                            "description", item.get("summary", "")
                        ),
                        severity=item.get("severity", "UNKNOWN").upper(),
                        cvss_score=item.get("cvss_score"),
                        affected_products=item.get(
                            "affected_products", []
                        ),
                        references=item.get("references", []),
                        is_exploited=item.get("is_exploited", False),
                        source_id=source_id,
                        raw_data=json.dumps(item),
                    )
                    if result != IngestResult.DUPLICATE:
                        count += 1

        return count


# =============================================================================
# SINGLETON
# =============================================================================

_scheduler: Optional[CVEIngestScheduler] = None


def get_scheduler() -> CVEIngestScheduler:
    """Get or create the scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = CVEIngestScheduler()
    return _scheduler
