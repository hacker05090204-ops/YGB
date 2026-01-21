"""
Test Input Sources - Phase-03 Trust
REIMPLEMENTED-2026

Tests for InputSource definitions.
These tests MUST fail initially until implementation is complete.
"""

import pytest


class TestInputSourceEnum:
    """Tests for InputSource enum."""

    def test_input_source_enum_exists(self):
        """Verify InputSource enum exists."""
        from python.phase03_trust.input_sources import InputSource
        assert InputSource is not None

    def test_input_source_has_human_input(self):
        """Verify InputSource has HUMAN_INPUT."""
        from python.phase03_trust.input_sources import InputSource
        assert InputSource.HUMAN_INPUT is not None

    def test_input_source_has_system_generated(self):
        """Verify InputSource has SYSTEM_GENERATED."""
        from python.phase03_trust.input_sources import InputSource
        assert InputSource.SYSTEM_GENERATED is not None

    def test_input_source_has_governance_defined(self):
        """Verify InputSource has GOVERNANCE_DEFINED."""
        from python.phase03_trust.input_sources import InputSource
        assert InputSource.GOVERNANCE_DEFINED is not None

    def test_input_source_has_external_untrusted(self):
        """Verify InputSource has EXTERNAL_UNTRUSTED."""
        from python.phase03_trust.input_sources import InputSource
        assert InputSource.EXTERNAL_UNTRUSTED is not None

    def test_input_source_is_closed(self):
        """Verify InputSource has exactly 4 sources (closed enum)."""
        from python.phase03_trust.input_sources import InputSource
        assert len(InputSource) == 4


class TestInputSourceTrustMapping:
    """Tests for mapping input sources to trust zones."""

    def test_human_input_maps_to_human_zone(self):
        """Verify HUMAN_INPUT maps to HUMAN trust zone."""
        from python.phase03_trust.input_sources import InputSource, get_source_trust_zone
        from python.phase03_trust.trust_zones import TrustZone
        assert get_source_trust_zone(InputSource.HUMAN_INPUT) == TrustZone.HUMAN

    def test_governance_defined_maps_to_governance_zone(self):
        """Verify GOVERNANCE_DEFINED maps to GOVERNANCE trust zone."""
        from python.phase03_trust.input_sources import InputSource, get_source_trust_zone
        from python.phase03_trust.trust_zones import TrustZone
        assert get_source_trust_zone(InputSource.GOVERNANCE_DEFINED) == TrustZone.GOVERNANCE

    def test_system_generated_maps_to_system_zone(self):
        """Verify SYSTEM_GENERATED maps to SYSTEM trust zone."""
        from python.phase03_trust.input_sources import InputSource, get_source_trust_zone
        from python.phase03_trust.trust_zones import TrustZone
        assert get_source_trust_zone(InputSource.SYSTEM_GENERATED) == TrustZone.SYSTEM

    def test_external_untrusted_maps_to_external_zone(self):
        """Verify EXTERNAL_UNTRUSTED maps to EXTERNAL trust zone."""
        from python.phase03_trust.input_sources import InputSource, get_source_trust_zone
        from python.phase03_trust.trust_zones import TrustZone
        assert get_source_trust_zone(InputSource.EXTERNAL_UNTRUSTED) == TrustZone.EXTERNAL


class TestInputSourceImmutability:
    """Tests for input source immutability."""

    def test_input_sources_are_enum(self):
        """Verify InputSource is an enum (inherently immutable)."""
        from enum import Enum
        from python.phase03_trust.input_sources import InputSource
        assert issubclass(InputSource, Enum)

    def test_cannot_add_new_source(self):
        """Verify cannot add new sources to enum (enum is closed)."""
        from python.phase03_trust.input_sources import InputSource
        # Python enums are inherently closed - verify count stays at 4
        initial_count = len(InputSource)
        # Attempt to set attribute (silently ignored by enums)
        try:
            InputSource.NEW_SOURCE = "new"
        except (AttributeError, TypeError):
            pass  # Some Python versions may raise
        # Enum member count unchanged
        assert len(InputSource) == initial_count == 4


class TestInputSourceHelpers:
    """Tests for input source helper functions."""

    def test_get_all_input_sources_exists(self):
        """Verify get_all_input_sources function exists."""
        from python.phase03_trust.input_sources import get_all_input_sources
        assert get_all_input_sources is not None

    def test_get_all_input_sources_returns_dict(self):
        """Verify get_all_input_sources returns dict."""
        from python.phase03_trust.input_sources import get_all_input_sources
        result = get_all_input_sources()
        assert isinstance(result, dict)

    def test_get_all_input_sources_has_all_sources(self):
        """Verify get_all_input_sources includes all sources."""
        from python.phase03_trust.input_sources import get_all_input_sources, InputSource
        result = get_all_input_sources()
        assert len(result) == len(InputSource)


class TestNoForbiddenSources:
    """Tests to verify no forbidden input sources exist."""

    def test_no_auto_source(self):
        """Verify no AUTO_ source exists."""
        from python.phase03_trust.input_sources import InputSource
        source_names = [s.name for s in InputSource]
        assert not any('AUTO' in name for name in source_names)

    def test_no_background_source(self):
        """Verify no BACKGROUND source exists."""
        from python.phase03_trust.input_sources import InputSource
        source_names = [s.name for s in InputSource]
        assert not any('BACKGROUND' in name for name in source_names)
