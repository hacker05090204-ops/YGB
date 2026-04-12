from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.ingestion.normalizer import QualityRejectionLog, SampleQualityScorer
from backend.ingestion.scrapers.exploitdb_scraper import ExploitDBScraper
from backend.ingestion.scrapers.msrc_scraper import MSRCScraper
from backend.ingestion.scrapers.redhat_scraper import RedHatAdvisoryScraper
from backend.ingestion.scrapers.snyk_scraper import SnykScraper
from backend.ingestion.scrapers.vulnrichment_scraper import VulnrichmentScraper


FIXTURES = Path("backend/tests/fixtures/ingestion")


def _payload_from_scraped_sample(sample) -> dict[str, object]:
    rendered_text = sample.render_text()
    return {
        "source": sample.source,
        "description": rendered_text,
        "raw_text": rendered_text,
        "url": sample.url,
        "cve_id": sample.cve_id,
        "severity": sample.severity,
        "tags": list(sample.tags),
        "token_count": len(rendered_text.split()),
        "lang": "en",
        "sha256_hash": "",
        "is_exploited": sample.is_exploited,
    }


def main() -> None:
    scorer = SampleQualityScorer(rejection_log=QualityRejectionLog(max_entries=100))
    scraped_samples: list[tuple[str, object]] = []

    redhat = RedHatAdvisoryScraper()
    try:
        sample = redhat.parse_detail(json.loads((FIXTURES / "redhat_cve_detail.json").read_text(encoding="utf-8")))
        scraped_samples.append(("redhat", sample))
    finally:
        redhat.close()

    msrc = MSRCScraper()
    try:
        samples = msrc.parse_document(
            json.loads((FIXTURES / "msrc_document.json").read_text(encoding="utf-8")),
            max_items=10,
        )
        scraped_samples.append(("msrc", samples[0]))
    finally:
        msrc.close()

    snyk = SnykScraper()
    try:
        sample = snyk.parse_detail_html(
            "SNYK-JS-LODASH-567746",
            (FIXTURES / "snyk_detail.html").read_text(encoding="utf-8"),
            ecosystem="npm",
        )
        scraped_samples.append(("snyk", sample))
    finally:
        snyk.close()

    vulnrichment = VulnrichmentScraper()
    try:
        samples = vulnrichment.parse_feed(
            json.loads((FIXTURES / "vulnrichment_list.json").read_text(encoding="utf-8")),
            max_items=10,
        )
        scraped_samples.append(("vulnrichment", samples[0]))
    finally:
        vulnrichment.close()

    exploitdb = ExploitDBScraper()
    try:
        samples = exploitdb.parse_csv(
            (FIXTURES / "exploitdb_recent.csv").read_text(encoding="utf-8"),
            max_items=10,
        )
        scraped_samples.append(("exploitdb", samples[0]))
    finally:
        exploitdb.close()

    details: list[dict[str, object]] = []
    accepted_samples = 0
    for source, sample in scraped_samples:
        payload = _payload_from_scraped_sample(sample)
        accepted, reason, score = scorer.evaluate(payload, ignore_duplicates=True)
        if accepted:
            accepted_samples += 1
        details.append(
            {
                "source": source,
                "cve_id": sample.cve_id,
                "severity": sample.severity,
                "accepted": accepted,
                "reason": reason,
                "score": round(float(score), 6),
            }
        )

    result = {
        "total_samples": len(details),
        "accepted_samples": accepted_samples,
        "acceptance_rate": accepted_samples / len(details) if details else 0.0,
        "details": details,
        "quality_stats": scorer.get_quality_stats(),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
