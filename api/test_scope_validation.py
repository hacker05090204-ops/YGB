"""
Tests for scope validation endpoint (POST /scope/validate).
Verifies that the scope validation logic correctly rejects:
- Empty targets
- Wildcard TLD abuse (*.com, *.io)
- Internal/localhost targets
- Invalid domain patterns
And accepts valid scope definitions.
"""

import sys
import os

# Add project root and api dir to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "api"))

from fastapi.testclient import TestClient
from api.server import app

client = TestClient(app)


def test_valid_scope():
    """Valid domain should pass validation."""
    res = client.post("/scope/validate", json={
        "target_url": "*.example.com",
        "scope_definition": {"include": ["*.example.com"]}
    })
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert len(data["violations"]) == 0


def test_empty_target_rejected():
    """Empty target URL should be rejected."""
    res = client.post("/scope/validate", json={
        "target_url": "",
        "scope_definition": {}
    })
    data = res.json()
    assert data["valid"] is False
    rules = [v["rule"] for v in data["violations"]]
    assert "EMPTY_TARGET" in rules


def test_wildcard_tld_rejected():
    """Wildcard at TLD level (*.com) should be rejected."""
    res = client.post("/scope/validate", json={
        "target_url": "*.com",
        "scope_definition": {}
    })
    data = res.json()
    assert data["valid"] is False
    rules = [v["rule"] for v in data["violations"]]
    assert "WILDCARD_TLD" in rules


def test_localhost_rejected():
    """Localhost targets should be rejected."""
    res = client.post("/scope/validate", json={
        "target_url": "http://localhost:8080",
        "scope_definition": {}
    })
    data = res.json()
    assert data["valid"] is False
    rules = [v["rule"] for v in data["violations"]]
    assert "INTERNAL_TARGET" in rules


def test_internal_ip_rejected():
    """Private IP ranges should be rejected."""
    res = client.post("/scope/validate", json={
        "target_url": "http://192.168.1.1",
        "scope_definition": {}
    })
    data = res.json()
    assert data["valid"] is False
    rules = [v["rule"] for v in data["violations"]]
    assert "INTERNAL_TARGET" in rules


def test_invalid_domain_rejected():
    """Strings without valid domains should be rejected."""
    res = client.post("/scope/validate", json={
        "target_url": "not-a-domain",
        "scope_definition": {}
    })
    data = res.json()
    assert data["valid"] is False
    rules = [v["rule"] for v in data["violations"]]
    assert "INVALID_DOMAIN" in rules


def test_valid_subdomain():
    """Specific subdomain should pass validation."""
    res = client.post("/scope/validate", json={
        "target_url": "api.example.com",
        "scope_definition": {}
    })
    data = res.json()
    assert data["valid"] is True
    assert len(data["violations"]) == 0
