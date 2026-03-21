from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable


def _pick_description(descriptions: Iterable[Dict[str, Any]]) -> str:
    for item in descriptions:
        if item.get("lang") == "en" and item.get("value"):
            return str(item["value"])
    for item in descriptions:
        if item.get("value"):
            return str(item["value"])
    return ""


class NvdConnector:
    """Canonicalizes an NVD record into the shared ingest schema."""

    source_name = "nvd"
    source_type = "nvd"

    def normalize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cve = payload.get("cve", payload)
        cve_id = cve.get("id") or cve.get("CVE_data_meta", {}).get("ID") or ""
        descriptions = cve.get("descriptions", cve.get("description", {}).get("description_data", []))
        summary = _pick_description(descriptions)
        source_url = payload.get("source_url") or f"https://nvd.nist.gov/vuln/detail/{cve_id}"
        content_sha256 = hashlib.sha256(summary.encode("utf-8")).hexdigest()
        return {
            "source_id": cve_id,
            "source_url": source_url,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "title": cve_id,
            "summary": summary,
            "content": summary,
            "content_sha256": content_sha256,
            "provenance": {
                "connector": self.source_name,
                "publisher": str(payload.get("sourceIdentifier", "nvd")),
                "retrieved_at": str(payload.get("retrieved_at", "")),
            },
            "tags": list(payload.get("tags", []) or []),
        }
