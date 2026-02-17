"""
Daily Browser Curriculum — Safe Knowledge Expansion Orchestrator.

Pipeline:
  1. Fetch new CVE/security feeds from whitelisted sources
  2. Parse structured data (CVE ID, summary, CVSS, CWE)
  3. Hash content (SHA-256 URL + body)
  4. Check semantic deduplication (TF-IDF, skip if similarity > 0.85)
  5. Pass through representation_guard.py
  6. Expand MODE-A representation

NO login automation. NO form submission. NO exploit testing.

GOVERNANCE: MODE-A only. Zero decision authority.
"""
import os
import sys
import re
import json
import hashlib
import logging
import time
import math
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.browser.browser_isolation import (
    safe_fetch, check_isolation, EdgeLaunchConfig, ALLOWED_DOMAINS,
)

logger = logging.getLogger(__name__)

# =========================================================================
# CVE FEED URLS (NVD + RSS)
# =========================================================================

CVE_FEED_URLS = [
    "https://services.nvd.nist.gov/rest/json/cves/2.0?resultsPerPage=20",
    "https://cve.org/api",
    "https://www.cvedetails.com/vulnerability-feed.php?vendor_id=0&product_id=0&version_id=0&orderby=1&cvssscoremin=7",
]

OWASP_URLS = [
    "https://owasp.org/Top10/",
    "https://cheatsheetseries.owasp.org/IndexTopTen.html",
]

MITRE_URLS = [
    "https://cwe.mitre.org/data/definitions/699.html",
]

# =========================================================================
# BLOCKED CONTENT
# =========================================================================

BLOCKED_PATTERNS = [
    r'shellcode|payload|exploit\s+code|proof.of.concept',
    r'reverse\s+shell|bind\s+shell|meterpreter',
    r'cobalt\s+strike|metasploit',
    r'eval\(|exec\(|system\(|os\.popen',
    r'<script|javascript:|data:text/html',
]


# =========================================================================
# DATA TYPES
# =========================================================================

@dataclass
class CveEntry:
    cve_id: str = ""
    title: str = ""
    summary: str = ""
    affected_component: str = ""
    cvss_vector: str = ""
    cvss_score: float = 0.0
    cwe_id: str = ""
    published_date: str = ""
    source_url: str = ""
    content_hash: str = ""


@dataclass
class DailySummary:
    date: str = ""
    total_fetched: int = 0
    total_parsed: int = 0
    total_dedup_skipped: int = 0
    total_blocked: int = 0
    total_expanded: int = 0
    domains_visited: List[str] = field(default_factory=list)
    cves_processed: List[dict] = field(default_factory=list)
    representation_diversity_delta: float = 0.0
    errors: List[str] = field(default_factory=list)
    timestamp: str = ""


# =========================================================================
# CONTENT HASH INDEX (Python mirror of C++ engine)
# =========================================================================

class ContentHashIndex:
    def __init__(self, index_path: str = ""):
        self._url_hashes: Dict[str, str] = {}
        self._content_hashes: Dict[str, str] = {}
        self._index_path = index_path
        if index_path and os.path.exists(index_path):
            self._load()

    def has_url(self, url: str) -> bool:
        h = hashlib.sha256(url.encode()).hexdigest()
        return h in self._url_hashes

    def has_content(self, content: str) -> bool:
        h = hashlib.sha256(content.encode('utf-8', errors='ignore')).hexdigest()
        return h in self._content_hashes

    def is_duplicate(self, url: str, content: str) -> bool:
        return self.has_url(url) or self.has_content(content)

    def add(self, url: str, content: str):
        url_h = hashlib.sha256(url.encode()).hexdigest()
        content_h = hashlib.sha256(
            content.encode('utf-8', errors='ignore')).hexdigest()
        ts = datetime.now(timezone.utc).isoformat()
        self._url_hashes[url_h] = ts
        self._content_hashes[content_h] = ts

    def size(self) -> int:
        return len(self._url_hashes)

    def save(self):
        if self._index_path:
            data = {
                "url_hashes": self._url_hashes,
                "content_hashes": self._content_hashes,
            }
            os.makedirs(os.path.dirname(self._index_path), exist_ok=True)
            with open(self._index_path, 'w') as f:
                json.dump(data, f, indent=2)

    def _load(self):
        try:
            with open(self._index_path) as f:
                data = json.load(f)
            self._url_hashes = data.get("url_hashes", {})
            self._content_hashes = data.get("content_hashes", {})
        except Exception:
            pass


# =========================================================================
# SEMANTIC DEDUPLICATOR (Python mirror of C++ engine)
# =========================================================================

STOP_WORDS = frozenset([
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "and", "or", "but", "nor", "not", "so", "yet", "for", "of",
    "in", "to", "with", "at", "by", "from", "on", "as", "if",
    "that", "this", "it", "its", "he", "she", "they", "we", "you",
])

SIMILARITY_THRESHOLD = 0.85


def tokenize(text: str) -> List[str]:
    return [w for w in re.findall(r'[a-z]{3,}', text.lower())
            if w not in STOP_WORDS]


def tfidf_similarity(text_a: str, text_b: str) -> float:
    """Compute TF-IDF cosine similarity between two texts."""
    tokens_a = tokenize(text_a)
    tokens_b = tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0

    # Term frequencies
    tf_a: Dict[str, int] = {}
    for t in tokens_a:
        tf_a[t] = tf_a.get(t, 0) + 1
    tf_b: Dict[str, int] = {}
    for t in tokens_b:
        tf_b[t] = tf_b.get(t, 0) + 1

    # Unique terms
    all_terms = set(tf_a.keys()) | set(tf_b.keys())

    # Dot product and magnitudes
    dot = 0.0
    mag_a = 0.0
    mag_b = 0.0
    for term in all_terms:
        a = tf_a.get(term, 0) / max(len(tokens_a), 1)
        b = tf_b.get(term, 0) / max(len(tokens_b), 1)
        dot += a * b
        mag_a += a * a
        mag_b += b * b

    mag_a = math.sqrt(mag_a)
    mag_b = math.sqrt(mag_b)
    if mag_a < 1e-10 or mag_b < 1e-10:
        return 0.0

    return dot / (mag_a * mag_b)


# =========================================================================
# CVE PARSING (mirrors C++ cve_feed_parser.cpp)
# =========================================================================

def is_blocked_content(text: str) -> bool:
    text_lower = text.lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def parse_cve_from_html(html: str, source_url: str) -> List[CveEntry]:
    """Extract CVE entries from fetched HTML content."""
    entries = []

    # Find CVE IDs in content
    cve_ids = re.findall(r'CVE-\d{4}-\d{4,}', html)
    cve_ids = list(dict.fromkeys(cve_ids))[:50]  # Dedup, limit 50

    for cve_id in cve_ids:
        # Find surrounding context (±500 chars)
        pos = html.find(cve_id)
        if pos == -1:
            continue
        start = max(0, pos - 200)
        end = min(len(html), pos + 500)
        context = html[start:end]

        # Strip HTML tags
        context = re.sub(r'<[^>]+>', ' ', context)
        context = re.sub(r'\s+', ' ', context).strip()

        # Block exploit content
        if is_blocked_content(context):
            continue

        entry = CveEntry(
            cve_id=cve_id,
            title=f"{cve_id}: {context[:80]}",
            summary=context[:500],
            source_url=source_url,
            content_hash=hashlib.sha256(
                context.encode('utf-8', errors='ignore')).hexdigest()[:32],
        )

        # Try to find CVSS
        cvss_match = re.search(r'CVSS[:\s]*(\d+\.?\d*)', context)
        if cvss_match:
            entry.cvss_score = float(cvss_match.group(1))

        # Try to find CWE
        cwe_match = re.search(r'CWE-(\d+)', context)
        if cwe_match:
            entry.cwe_id = f"CWE-{cwe_match.group(1)}"

        entries.append(entry)

    return entries


# =========================================================================
# DAILY CURRICULUM RUN
# =========================================================================

def run_daily_curriculum(test_mode: bool = False) -> DailySummary:
    """Run the daily browser curriculum pipeline."""
    logger.info("=" * 60)
    logger.info("DAILY BROWSER CURRICULUM")
    logger.info("=" * 60)

    summary = DailySummary(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Hash index
    project_root = os.path.join(os.path.dirname(__file__), '..', '..')
    index_path = os.path.join(project_root, 'reports', 'g38_training',
                              'content_hash_index.json')
    hash_index = ContentHashIndex(index_path)

    # Existing summaries for dedup
    existing_summaries: List[str] = []

    # Config
    config = EdgeLaunchConfig()

    # Import governance guard
    try:
        from backend.governance.representation_guard import RepresentationGuard
        guard = RepresentationGuard()
        has_guard = True
    except ImportError:
        has_guard = False
        logger.warning("RepresentationGuard not available, using passthrough")

    # Combine all source URLs
    all_urls = CVE_FEED_URLS + OWASP_URLS + MITRE_URLS

    if test_mode:
        # In test mode, simulate without actual browser
        logger.info("TEST MODE — simulating feed processing")
        summary.total_fetched = len(all_urls)
        summary.domains_visited = list(set(
            url.split("://")[1].split("/")[0] for url in all_urls
            if "://" in url
        ))

        # Simulate 5 CVE entries
        for i in range(5):
            entry = CveEntry(
                cve_id=f"CVE-2024-{10000+i}",
                title=f"CVE-2024-{10000+i}: Test vulnerability in web component",
                summary=f"A vulnerability in HTTP request handling allows unauthorized access via crafted headers. Affects web servers using default configuration.",
                affected_component="web-server",
                cvss_score=7.5,
                cwe_id="CWE-79",
                source_url="https://nvd.nist.gov/vuln/detail/CVE-2024-10000",
                content_hash=hashlib.sha256(
                    f"test_content_{i}".encode()).hexdigest()[:32],
            )

            # Dedup check
            if hash_index.is_duplicate(entry.source_url, entry.summary):
                summary.total_dedup_skipped += 1
                continue

            # Semantic dedup
            max_sim = 0.0
            for existing in existing_summaries:
                sim = tfidf_similarity(entry.summary, existing)
                max_sim = max(max_sim, sim)
            if max_sim > SIMILARITY_THRESHOLD:
                summary.total_dedup_skipped += 1
                continue

            # Governance check
            if has_guard:
                _, verdict = guard.check_and_sanitize({"summary": entry.summary})
                if not verdict.allowed:
                    summary.total_blocked += 1
                    continue

            # Accept
            hash_index.add(entry.source_url, entry.summary)
            existing_summaries.append(entry.summary)
            summary.cves_processed.append(asdict(entry))
            summary.total_expanded += 1

        summary.total_parsed = 5
        summary.representation_diversity_delta = round(
            math.log(1 + summary.total_expanded) / math.log(10), 4)

    else:
        # Production mode — actual browser fetch
        for url in all_urls:
            # Isolation check
            iso = check_isolation(url, config)
            if not iso.all_passed:
                logger.warning(f"Skipped {url}: {iso.rejection_reason}")
                summary.errors.append(f"Blocked: {url} — {iso.rejection_reason}")
                continue

            domain = url.split("://")[1].split("/")[0] if "://" in url else ""
            if domain and domain not in summary.domains_visited:
                summary.domains_visited.append(domain)

            # Fetch
            fetch_result = safe_fetch(url, config)
            summary.total_fetched += 1

            if not fetch_result.success:
                summary.errors.append(f"Fetch failed: {url} — {fetch_result.error}")
                continue

            # Hash dedup
            if hash_index.is_duplicate(url, fetch_result.content):
                summary.total_dedup_skipped += 1
                continue

            # Parse CVEs
            cves = parse_cve_from_html(fetch_result.content, url)
            summary.total_parsed += len(cves)

            for entry in cves:
                # Semantic dedup
                max_sim = 0.0
                for existing in existing_summaries:
                    max_sim = max(max_sim,
                                 tfidf_similarity(entry.summary, existing))
                if max_sim > SIMILARITY_THRESHOLD:
                    summary.total_dedup_skipped += 1
                    continue

                # Governance check
                if has_guard:
                    _, verdict = guard.check_and_sanitize({"summary": entry.summary})
                    if not verdict.allowed:
                        summary.total_blocked += 1
                        continue

                # Accept
                hash_index.add(entry.source_url, entry.summary)
                existing_summaries.append(entry.summary)
                summary.cves_processed.append(asdict(entry))
                summary.total_expanded += 1

            hash_index.add(url, fetch_result.content)

        summary.representation_diversity_delta = round(
            math.log(1 + summary.total_expanded) / math.log(10), 4)

    # Save index
    hash_index.save()

    # Save summary
    report_dir = os.path.join(project_root, 'reports', 'g38_training')
    os.makedirs(report_dir, exist_ok=True)
    summary_path = os.path.join(report_dir, 'daily_curriculum_summary.json')
    with open(summary_path, 'w') as f:
        json.dump(asdict(summary), f, indent=2)

    logger.info(f"\n--- Summary ---")
    logger.info(f"  Fetched:      {summary.total_fetched}")
    logger.info(f"  Parsed:       {summary.total_parsed}")
    logger.info(f"  Dedup skip:   {summary.total_dedup_skipped}")
    logger.info(f"  Blocked:      {summary.total_blocked}")
    logger.info(f"  Expanded:     {summary.total_expanded}")
    logger.info(f"  Diversity Δ:  {summary.representation_diversity_delta}")
    logger.info(f"  Domains:      {summary.domains_visited}")
    logger.info(f"Report saved: {summary_path}")

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [CURRICULUM] %(message)s')
    test_mode = "--test" in sys.argv
    summary = run_daily_curriculum(test_mode=test_mode)
    print(f"\nResult: {summary.total_expanded} CVEs expanded, "
          f"{summary.total_dedup_skipped} deduped")
