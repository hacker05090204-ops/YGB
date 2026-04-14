"""Phase 6 tests for the static vulnerability field registry."""

import importlib.util
import os
import sys

import pytest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODULE_PATH = os.path.join(PROJECT_ROOT, "backend", "testing", "field_registry.py")

_spec = importlib.util.spec_from_file_location("field_registry", MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


def test_registry_contains_at_least_80_fields():
    assert _mod.TOTAL_FIELDS >= 80
    assert len(_mod.FIELD_REGISTRY) == _mod.TOTAL_FIELDS


def test_every_expert_is_represented_in_registry():
    summary = _mod.build_summary()
    assert summary["experts_total"] == 23
    assert summary["experts_covered"] == summary["experts_total"]


def test_each_field_has_required_phase6_metadata():
    for field in _mod.FIELD_REGISTRY:
        assert isinstance(field["id"], int)
        assert field["slug"]
        assert field["category"]
        assert field["description"]
        assert field["severity"] in {"critical", "high", "medium", "low"}
        assert isinstance(field["expert_id"], int)
        assert field["expert_name"] in _mod.EXPERT_INDEX
        assert field["test_patterns"]


def test_lookup_by_id_and_slug_return_same_field():
    by_id = _mod.get_field_by_id(0)
    by_slug = _mod.get_field_by_slug("dom_xss_reflected")
    assert by_id["slug"] == "dom_xss_reflected"
    assert by_id == by_slug


def test_fields_for_expert_support_name_and_numeric_lookup():
    by_name = _mod.get_fields_for_expert("xss")
    by_numeric = _mod.get_fields_for_expert(_mod.EXPERT_INDEX["xss"])
    assert by_name
    assert by_name == by_numeric
    assert all(field["expert_name"] == "xss" for field in by_name)


def test_unknown_lookup_paths_raise_explicit_errors():
    with pytest.raises(KeyError):
        _mod.get_field_by_id(9999)
    with pytest.raises(KeyError):
        _mod.get_fields_for_expert("unknown_expert")


def test_report_includes_total_fields_and_category_distribution():
    report = _mod.render_report()
    summary = _mod.build_summary()
    assert f"Total fields: {summary['total_fields']}" in report
    assert "Category distribution:" in report
    assert "Client Side: 7" in report


def test_category_distribution_totals_match_registry_size():
    distribution = _mod.get_category_distribution()
    assert sum(distribution.values()) == _mod.TOTAL_FIELDS
    assert distribution["client_side"] == 7
    assert distribution["api_business_logic"] == 7
