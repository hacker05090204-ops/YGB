# CVE pipeline module
from backend.cve.cve_pipeline import get_pipeline, CVEPipeline
from backend.cve.cve_scheduler import get_scheduler, CVEIngestScheduler
from backend.cve.promotion_policy import get_promotion_policy
from backend.cve.dedup_drift import get_dedup_drift_engine
from backend.cve.anti_hallucination import get_anti_hallucination_validator
from backend.cve.headless_research import get_research_engine
