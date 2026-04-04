import hashlib
import json

from backend.ingest.connectors.nvd import NvdConnector
from backend.ingest.connectors.storage import FileStorageConnector
from backend.ingest.dedup.fingerprint import (
    canonical_fingerprint,
    compute_sha256,
    near_duplicate_score,
)
from backend.ingest.normalize.canonicalize import canonicalize_record
from backend.ingest.router.router import route_record


def test_compute_sha256_accepts_text_and_bytes():
    assert compute_sha256("abc") == compute_sha256(b"abc")


def test_canonical_fingerprint_is_key_order_independent():
    assert canonical_fingerprint({"b": 2, "a": 1}) == canonical_fingerprint(
        {"a": 1, "b": 2}
    )


def test_near_duplicate_score_uses_jaccard_overlap():
    assert near_duplicate_score("api auth bypass", "api auth bypass login") == 0.75
    assert near_duplicate_score("", "api auth bypass") == 0.0


def test_near_duplicate_score_keeps_numeric_and_boolean_scalars():
    assert near_duplicate_score(0, "0") == 1.0
    assert near_duplicate_score(False, "false") == 1.0


def test_nvd_connector_prefers_english_description_and_defaults_url():
    payload = {
        "cve": {
            "id": "CVE-2026-0001",
            "descriptions": [
                {"lang": "fr", "value": "Resume francais"},
                {"lang": "en", "value": "English summary"},
            ],
        },
        "sourceIdentifier": "nvd-api",
        "retrieved_at": "2026-03-21T00:00:00Z",
        "tags": ["critical"],
    }

    normalized = NvdConnector().normalize(payload)

    assert normalized["source_id"] == "CVE-2026-0001"
    assert normalized["source_url"] == "https://nvd.nist.gov/vuln/detail/CVE-2026-0001"
    assert normalized["summary"] == "English summary"
    assert normalized["content_sha256"] == hashlib.sha256(
        b"English summary"
    ).hexdigest()
    assert normalized["provenance"] == {
        "connector": "nvd",
        "publisher": "nvd-api",
        "retrieved_at": "2026-03-21T00:00:00Z",
    }
    assert normalized["tags"] == ["critical"]


def test_nvd_connector_falls_back_to_first_available_description():
    payload = {
        "cve": {
            "CVE_data_meta": {"ID": "CVE-2026-0002"},
            "description": {
                "description_data": [
                    {"lang": "es", "value": "Resumen"},
                ]
            },
        }
    }

    normalized = NvdConnector().normalize(payload)

    assert normalized["source_id"] == "CVE-2026-0002"
    assert normalized["summary"] == "Resumen"
    assert normalized["provenance"]["publisher"] == "nvd"


def test_file_storage_connector_loads_json_and_applies_defaults(tmp_path):
    path = tmp_path / "record.json"
    path.write_text(
        json.dumps({"content": "json content", "source_id": "manual-id"}),
        encoding="utf-8",
    )

    record = FileStorageConnector().load_record(str(path))

    assert record["source_id"] == "manual-id"
    assert record["source_url"] == path.resolve().as_uri()
    assert record["source_name"] == "storage"
    assert record["source_type"] == "storage"
    assert record["content"] == "json content"
    assert record["content_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert record["provenance"] == {
        "connector": "storage",
        "path": str(path.resolve()),
    }


def test_file_storage_connector_wraps_plain_text_when_json_is_invalid(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("plain text record", encoding="utf-8")

    record = FileStorageConnector().load_record(str(path))

    assert record["source_id"] == "note.txt"
    assert record["content"] == "plain text record"
    assert record["provenance"]["path"] == str(path.resolve())


def test_file_storage_connector_replaces_invalid_utf8_bytes(tmp_path):
    path = tmp_path / "binary.txt"
    path.write_bytes(b"bad\xfftext")

    record = FileStorageConnector().load_record(str(path))

    assert record["content"] == "bad\ufffdtext"
    assert record["content_sha256"] == hashlib.sha256(b"bad\xfftext").hexdigest()


def test_route_record_selects_mobile_expert_from_keywords():
    record = canonicalize_record(
        {
            "source_id": "sample-1",
            "source_url": "https://example.com/report/1",
            "content": "Android mobile APK deep link issue",
            "tags": ["ios"],
        },
        source_name="storage",
        source_type="storage",
    )

    decision = route_record(record)

    assert decision.expert_name == "mobile_apk"
    assert set(decision.reasons) >= {"mobile", "android", "apk", "ios"}


def test_route_record_defaults_to_web_vulns_when_no_keywords_match():
    record = canonicalize_record(
        {
            "source_id": "sample-2",
            "source_url": "https://example.com/report/2",
            "content": "novel category without any mapped keyword",
        },
        source_name="storage",
        source_type="storage",
    )

    decision = route_record(record)

    assert decision.expert_name == "web_vulns"
    assert decision.reasons == ["default_web_routing"]


def test_route_record_matches_tag_only_graphql_records():
    record = canonicalize_record(
        {
            "source_id": "sample-3",
            "source_url": "https://example.com/report/3",
            "content": "schema issue without explicit route words",
            "tags": ["graphql"],
        },
        source_name="storage",
        source_type="storage",
    )

    decision = route_record(record)

    assert decision.expert_name == "graphql_abuse"
    assert decision.reasons == ["graphql"]


def test_route_record_keeps_web_vulns_on_shared_http_tie():
    record = canonicalize_record(
        {
            "source_id": "sample-4",
            "source_url": "https://example.com/report/4",
            "content": "http traffic anomaly",
        },
        source_name="storage",
        source_type="storage",
    )

    decision = route_record(record)

    assert decision.expert_name == "web_vulns"
    assert decision.reasons == ["http"]
