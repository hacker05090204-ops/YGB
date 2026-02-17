"""
Browser API Endpoints — Daily Summary, CVE List, Representation Impact.

Serves real data from daily curriculum runs (NO mock data).

GET /browser/daily-summary   — new CVEs, domains visited, dedup skipped
GET /browser/new-cves        — list of new CVEs ingested today
GET /browser/representation-impact — diversity score delta

GOVERNANCE: Read-only endpoints. No mutation. No authority.
"""
import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# =========================================================================
# DATA PATH
# =========================================================================

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..'))
REPORT_DIR = os.path.join(PROJECT_ROOT, 'reports', 'g38_training')
SUMMARY_PATH = os.path.join(REPORT_DIR, 'daily_curriculum_summary.json')
HASH_INDEX_PATH = os.path.join(REPORT_DIR, 'content_hash_index.json')


# =========================================================================
# HELPERS
# =========================================================================

def _load_summary() -> Optional[dict]:
    """Load latest daily summary."""
    if not os.path.exists(SUMMARY_PATH):
        return None
    try:
        with open(SUMMARY_PATH) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load summary: {e}")
        return None


def _load_hash_index() -> Optional[dict]:
    """Load content hash index."""
    if not os.path.exists(HASH_INDEX_PATH):
        return None
    try:
        with open(HASH_INDEX_PATH) as f:
            return json.load(f)
    except Exception:
        return None


# =========================================================================
# ENDPOINT HANDLERS
# =========================================================================

def get_daily_summary() -> dict:
    """
    GET /browser/daily-summary

    Returns:
        - new_cves_count: int
        - domains_visited: List[str]
        - dedup_skipped: int
        - total_blocked: int
        - total_expanded: int
        - date: str
    """
    summary = _load_summary()
    if summary is None:
        return {
            "status": "no_data",
            "message": "No daily curriculum run found. Run daily_curriculum.py first.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "status": "ok",
        "date": summary.get("date", ""),
        "new_cves_count": len(summary.get("cves_processed", [])),
        "domains_visited": summary.get("domains_visited", []),
        "dedup_skipped": summary.get("total_dedup_skipped", 0),
        "total_blocked": summary.get("total_blocked", 0),
        "total_expanded": summary.get("total_expanded", 0),
        "total_fetched": summary.get("total_fetched", 0),
        "errors": summary.get("errors", []),
        "timestamp": summary.get("timestamp", ""),
    }


def get_new_cves() -> dict:
    """
    GET /browser/new-cves

    Returns list of CVEs ingested today.
    """
    summary = _load_summary()
    if summary is None:
        return {
            "status": "no_data",
            "cves": [],
            "count": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    cves = summary.get("cves_processed", [])
    return {
        "status": "ok",
        "cves": [
            {
                "cve_id": c.get("cve_id", ""),
                "title": c.get("title", ""),
                "summary": c.get("summary", "")[:200],
                "cvss_score": c.get("cvss_score", 0.0),
                "cwe_id": c.get("cwe_id", ""),
                "source_url": c.get("source_url", ""),
            }
            for c in cves
        ],
        "count": len(cves),
        "date": summary.get("date", ""),
        "timestamp": summary.get("timestamp", ""),
    }


def get_representation_impact() -> dict:
    """
    GET /browser/representation-impact

    Returns representation diversity score delta.
    """
    summary = _load_summary()
    hash_index = _load_hash_index()

    if summary is None:
        return {
            "status": "no_data",
            "diversity_delta": 0.0,
            "total_indexed": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    total_indexed = 0
    if hash_index:
        total_indexed = len(hash_index.get("url_hashes", {}))

    return {
        "status": "ok",
        "diversity_delta": summary.get("representation_diversity_delta", 0.0),
        "total_expanded_today": summary.get("total_expanded", 0),
        "total_indexed": total_indexed,
        "axes": [
            "protocol_variation",
            "dom_structure",
            "api_schema",
            "auth_flow",
        ],
        "date": summary.get("date", ""),
        "timestamp": summary.get("timestamp", ""),
    }


# =========================================================================
# FLASK/FASTAPI REGISTRATION (if used as module)
# =========================================================================

def register_routes(app):
    """Register browser endpoints with Flask/FastAPI app."""
    try:
        # Try Flask
        @app.route("/browser/daily-summary", methods=["GET"])
        def daily_summary_route():
            from flask import jsonify
            return jsonify(get_daily_summary())

        @app.route("/browser/new-cves", methods=["GET"])
        def new_cves_route():
            from flask import jsonify
            return jsonify(get_new_cves())

        @app.route("/browser/representation-impact", methods=["GET"])
        def representation_impact_route():
            from flask import jsonify
            return jsonify(get_representation_impact())

        logger.info("Browser endpoints registered (Flask)")
    except Exception:
        logger.info("Flask registration skipped, endpoints available as functions")


if __name__ == "__main__":
    # Quick test — print endpoint outputs
    import sys
    logging.basicConfig(level=logging.INFO)
    print("=== Daily Summary ===")
    print(json.dumps(get_daily_summary(), indent=2))
    print("\n=== New CVEs ===")
    print(json.dumps(get_new_cves(), indent=2))
    print("\n=== Representation Impact ===")
    print(json.dumps(get_representation_impact(), indent=2))
