"""
CVE Ingest Scheduler — 5-Minute Polling with SLO Tracking

Runs every 5 minutes (configurable via CVE_INGEST_INTERVAL_SECONDS).
Per-source circuit breaker, retry with exponential backoff.
Idempotent ingestion with content-hash dedup.
SLO tracking: 99.5% ingest success, 99.9% job execution.
"""

import asyncio
from dataclasses import asdict, dataclass, field, replace
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


@dataclass(frozen=True)
class SourceCycleStats:
    """Per-source scheduler stats for a single cycle."""

    source_id: str
    success: bool
    no_delta: bool = False
    records_seen: int = 0
    records_ingested: int = 0
    duplicates: int = 0
    rejected: int = 0
    attempts: int = 1
    error: str = ""
    rejection_reasons: Dict[str, int] = field(default_factory=dict)


class CVEIngestScheduler:
    """Async scheduler for CVE feed ingestion every 5 minutes."""

    # Health state constants
    STATE_BOOTING = "BOOTING"
    STATE_RUNNING = "RUNNING"
    STATE_DEGRADED = "DEGRADED"
    STATE_BLOCKED = "BLOCKED"
    STATE_STOPPED = "STOPPED"

    _DEGRADED_THRESHOLD = 3  # consecutive failures before DEGRADED

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_run_at: Optional[str] = None
        self._consecutive_failures: int = 0
        self._total_runs: int = 0
        self._successful_runs: int = 0
        self._health_state: str = self.STATE_BOOTING
        self._scheduler_stats: Dict[str, Any] = {
            "cycles_completed": 0,
            "sources_processed": 0,
            "sources_succeeded": 0,
            "sources_failed": 0,
            "sources_no_delta": 0,
            "records_seen": 0,
            "records_ingested": 0,
            "duplicates": 0,
            "rejected": 0,
        }
        self._last_cycle_stats: Optional[Dict[str, Any]] = None

    @property
    def interval_seconds(self) -> int:
        return _INGEST_INTERVAL

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def health_state(self) -> str:
        """Current health state: BOOTING, RUNNING, DEGRADED, BLOCKED, STOPPED."""
        if not self._running:
            return self.STATE_STOPPED if self._total_runs > 0 else self.STATE_BOOTING
        if self._consecutive_failures >= self._DEGRADED_THRESHOLD:
            return self.STATE_DEGRADED
        if self._total_runs > 0:
            return self.STATE_RUNNING
        return self.STATE_BOOTING

    def get_health(self) -> Dict[str, Any]:
        """Get scheduler health status."""
        return {
            "running": self._running,
            "health_state": self.health_state,
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
            "scheduler_stats": {
                **self._scheduler_stats,
                "last_cycle": self._last_cycle_stats,
            },
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
        # Defer first ingest cycle so API startup stays responsive.
        # Without this delay, first-cycle ingest/parsing can monopolize
        # the event loop on boot for large feeds.
        try:
            await asyncio.sleep(_INGEST_INTERVAL)
        except asyncio.CancelledError:
            return

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
        cycle_started = time.monotonic()
        cycle_stats: Dict[str, Any] = {
            "cycle": self._total_runs,
            "started_at": self._last_run_at,
            "finished_at": None,
            "duration_ms": 0.0,
            "sources_attempted": 0,
            "sources_skipped_circuit": 0,
            "sources_not_configured": 0,
            "sources_succeeded": 0,
            "sources_failed": 0,
            "sources_no_delta": 0,
            "records_seen": 0,
            "records_ingested": 0,
            "duplicates": 0,
            "rejected": 0,
            "per_source": [],
        }

        logger.info(
            f"[CVE_SCHEDULER] Ingest cycle #{self._total_runs} starting"
        )

        for source_id in _SOURCE_CONFIGS:
            if not pipeline.can_fetch_source(source_id):
                logger.info(
                    f"[CVE_SCHEDULER] Skipping {source_id} "
                    f"(circuit breaker open)"
                )
                cycle_stats["sources_skipped_circuit"] += 1
                continue

            status = pipeline._source_status.get(source_id)
            from backend.cve.cve_pipeline import SourceStatus
            if status == SourceStatus.NOT_CONFIGURED:
                cycle_stats["sources_not_configured"] += 1
                continue

            cycle_stats["sources_attempted"] += 1
            source_stats = await self._fetch_source_with_retry(
                pipeline, source_id
            )
            cycle_stats["per_source"].append(asdict(source_stats))
            cycle_stats["records_seen"] += source_stats.records_seen
            cycle_stats["records_ingested"] += source_stats.records_ingested
            cycle_stats["duplicates"] += source_stats.duplicates
            cycle_stats["rejected"] += source_stats.rejected
            if source_stats.no_delta:
                cycle_stats["sources_no_delta"] += 1
            if source_stats.success or source_stats.no_delta:
                cycle_stats["sources_succeeded"] += 1
            else:
                cycle_stats["sources_failed"] += 1
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

        cycle_stats["finished_at"] = datetime.now(timezone.utc).isoformat()
        cycle_stats["duration_ms"] = round(
            (time.monotonic() - cycle_started) * 1000, 2
        )
        self._last_cycle_stats = cycle_stats
        self._scheduler_stats["cycles_completed"] += 1
        self._scheduler_stats["sources_processed"] += cycle_stats["sources_attempted"]
        self._scheduler_stats["sources_succeeded"] += cycle_stats["sources_succeeded"]
        self._scheduler_stats["sources_failed"] += cycle_stats["sources_failed"]
        self._scheduler_stats["sources_no_delta"] += cycle_stats["sources_no_delta"]
        self._scheduler_stats["records_seen"] += cycle_stats["records_seen"]
        self._scheduler_stats["records_ingested"] += cycle_stats["records_ingested"]
        self._scheduler_stats["duplicates"] += cycle_stats["duplicates"]
        self._scheduler_stats["rejected"] += cycle_stats["rejected"]

        # Stream new records to training bridge
        try:
            from backend.cve.bridge_ingestion_worker import get_bridge_worker
            worker = get_bridge_worker()
            bridge_count = worker.stream_ingest_new(pipeline)
            if bridge_count > 0:
                logger.info(
                    f"[CVE_SCHEDULER] Bridge ingested {bridge_count} new samples"
                )
                worker.update_manifest()
        except Exception as e:
            logger.warning(f"[CVE_SCHEDULER] Bridge ingest skipped: {e}")

    async def _fetch_source_with_retry(
        self, pipeline, source_id: str
    ) -> SourceCycleStats:
        """Fetch from a single source with retry/backoff."""
        last_result = SourceCycleStats(
            source_id=source_id,
            success=False,
            error="fetch_not_attempted",
        )
        for attempt in range(1, _MAX_RETRIES + 1):
            result = replace(
                await self._fetch_source(pipeline, source_id),
                attempts=attempt,
            )
            if result.success or result.no_delta:
                return result

            last_result = result
            if attempt < _MAX_RETRIES:
                backoff = _BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    f"[CVE_SCHEDULER] {source_id} attempt {attempt}/"
                    f"{_MAX_RETRIES} failed: {result.error}. "
                    f"Backoff {backoff}s"
                )
                await asyncio.sleep(backoff)

        failure_message = last_result.error or f"All {_MAX_RETRIES} retries exhausted"
        pipeline.mark_source_error(source_id, failure_message)
        pipeline.record_stage_result(
            source_id,
            "FETCH",
            "ERROR",
            message=failure_message,
        )
        return last_result

    async def _fetch_source(self, pipeline, source_id: str) -> bool:
        """Fetch actual data from a source. Returns True on success."""
        try:
            import httpx
        except ImportError:
            return SourceCycleStats(
                source_id=source_id,
                success=False,
                error="httpx not installed",
            )

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
                    pipeline.record_stage_result(
                        source_id,
                        "FETCH",
                        "NO_DELTA",
                        message="HTTP 304",
                    )
                    logger.info(
                        f"[CVE_SCHEDULER] {source_id}: NO_DELTA (304)"
                    )
                    return SourceCycleStats(
                        source_id=source_id,
                        success=True,
                        no_delta=True,
                    )

                resp.raise_for_status()

                # Extract watermark headers
                etag = resp.headers.get("ETag", "")
                last_mod = resp.headers.get("Last-Modified", "")

                data = resp.json()
                ingest_stats = self._parse_and_ingest(
                    pipeline, source_id, data
                )

                pipeline.mark_source_success(
                    source_id, ingest_stats["records_ingested"],
                    etag=etag,
                    last_modified_header=last_mod,
                )
                pipeline.record_stage_result(
                    source_id,
                    "FETCH",
                    "SUCCESS",
                    records_seen=ingest_stats["records_seen"],
                    records_ingested=ingest_stats["records_ingested"],
                    duplicates=ingest_stats["duplicates"],
                    rejected=ingest_stats["rejected"],
                    rejection_reasons=ingest_stats["rejection_reasons"],
                    message=f"HTTP {resp.status_code}",
                )
                return SourceCycleStats(
                    source_id=source_id,
                    success=True,
                    records_seen=ingest_stats["records_seen"],
                    records_ingested=ingest_stats["records_ingested"],
                    duplicates=ingest_stats["duplicates"],
                    rejected=ingest_stats["rejected"],
                    rejection_reasons=ingest_stats["rejection_reasons"],
                )

        except httpx.HTTPStatusError as e:
            return SourceCycleStats(
                source_id=source_id,
                success=False,
                error=f"HTTP {e.response.status_code}",
            )
        except Exception as e:
            logger.error("[CVE_SCHEDULER] %s fetch error: %s", source_id, e)
            return SourceCycleStats(
                source_id=source_id,
                success=False,
                error=f"Fetch failed: {type(e).__name__}",
            )

    def _parse_and_ingest(
        self, pipeline, source_id: str, data: Any
    ) -> Dict[str, Any]:
        """Parse API response and ingest records. Returns stage stats."""
        from backend.cve.cve_pipeline import IngestResult
        stats: Dict[str, Any] = {
            "records_seen": 0,
            "records_ingested": 0,
            "duplicates": 0,
            "rejected": 0,
            "rejection_reasons": {},
        }

        def reject(reason: str, payload: Any):
            stats["rejected"] += 1
            stats["rejection_reasons"][reason] = (
                stats["rejection_reasons"].get(reason, 0) + 1
            )
            pipeline.record_rejection(source_id, reason, payload)

        def count_result(result: IngestResult):
            if result == IngestResult.DUPLICATE:
                stats["duplicates"] += 1
            elif result in (IngestResult.NEW, IngestResult.UPDATED):
                stats["records_ingested"] += 1

        # Handle different source formats
        if source_id == "cisa_kev":
            vulns = data.get("vulnerabilities", [])
            for v in vulns:
                stats["records_seen"] += 1
                cve_id = v.get("cveID", "")
                if not cve_id:
                    reject("missing_cve_id", v)
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
                count_result(result)

        elif source_id in ("nvd", "cve_services"):
            vulns = data.get("vulnerabilities", data.get("cveRecords", []))
            if isinstance(vulns, list):
                for item in vulns:
                    stats["records_seen"] += 1
                    cve_data = item.get("cve", item)
                    cve_id = cve_data.get("id", cve_data.get("cveId", ""))
                    if not cve_id:
                        reject("missing_cve_id", item)
                        continue

                    vuln_status = str(
                        cve_data.get("vulnStatus") or cve_data.get("state") or ""
                    ).upper()
                    if "REJECT" in vuln_status:
                        reject(
                            "rejected_status",
                            {"cve_id": cve_id, "status": vuln_status},
                        )
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
                    count_result(result)

        else:
            # Generic: try to extract from list
            items = data if isinstance(data, list) else data.get(
                "results", data.get("data", [])
            )
            if isinstance(items, list):
                for item in items:
                    stats["records_seen"] += 1
                    cve_id = (
                        item.get("cve_id") or item.get("id") or
                        item.get("cveId", "")
                    )
                    if not cve_id:
                        reject("missing_cve_id", item)
                        continue

                    item_status = str(
                        item.get("status") or item.get("vulnStatus") or ""
                    ).upper()
                    if "REJECT" in item_status:
                        reject(
                            "rejected_status",
                            {"cve_id": cve_id, "status": item_status},
                        )
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
                    count_result(result)

        pipeline.record_stage_result(
            source_id,
            "PARSE_INGEST",
            "SUCCESS" if stats["records_seen"] or stats["rejected"] else "EMPTY",
            records_seen=stats["records_seen"],
            records_ingested=stats["records_ingested"],
            duplicates=stats["duplicates"],
            rejected=stats["rejected"],
            rejection_reasons=stats["rejection_reasons"],
        )
        return stats


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
