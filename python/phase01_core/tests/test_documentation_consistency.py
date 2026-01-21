"""
Test Documentation Consistency - Phase-01 Core
REIMPLEMENTED-2026 (HARDENING)

Tests to verify README matches constants/invariants.
Part of 100% coverage hardening.
"""

import pytest
from pathlib import Path


PHASE01_PATH = Path(__file__).parent.parent
README_PATH = PHASE01_PATH / 'README.md'


class TestDocumentationConsistency:
    """Tests to verify documentation matches implementation."""

    def test_readme_exists(self):
        """Verify README.md exists in phase01_core."""
        assert README_PATH.exists(), "README.md must exist"

    def test_readme_mentions_human_authority(self):
        """Verify README documents human authority principle."""
        content = README_PATH.read_text()
        assert 'human authority' in content.lower() or 'HUMAN' in content

    def test_readme_mentions_no_autonomous(self):
        """Verify README documents no autonomous execution."""
        content = README_PATH.read_text()
        assert 'autonomous' in content.lower() or 'No autonomous' in content

    def test_readme_mentions_no_background(self):
        """Verify README documents no background actions."""
        content = README_PATH.read_text()
        assert 'background' in content.lower()

    def test_readme_mentions_auditable(self):
        """Verify README documents auditability."""
        content = README_PATH.read_text()
        assert 'audit' in content.lower()

    def test_readme_mentions_explicit(self):
        """Verify README documents explicit principle."""
        content = README_PATH.read_text()
        assert 'explicit' in content.lower()

    def test_readme_lists_all_modules(self):
        """Verify README lists all implementation modules."""
        content = README_PATH.read_text()
        
        required_modules = ['constants.py', 'invariants.py', 'identities.py', 'errors.py']
        
        for module in required_modules:
            assert module in content, f"README must document {module}"

    def test_readme_mentions_reimplemented_2026(self):
        """Verify README mentions REIMPLEMENTED-2026 status."""
        content = README_PATH.read_text()
        assert 'REIMPLEMENTED-2026' in content or 'reimplemented' in content.lower()

    def test_readme_documents_frozen_status(self):
        """Verify README documents frozen status."""
        content = README_PATH.read_text()
        assert 'frozen' in content.lower()


class TestConstantsDocumentationMatch:
    """Verify constants match their documented purpose."""

    def test_human_authority_constant_matches_docs(self):
        """Verify HUMAN_AUTHORITY_ABSOLUTE value matches documented behavior."""
        from python.phase01_core.constants import HUMAN_AUTHORITY_ABSOLUTE
        
        # Documentation says human authority is absolute
        # Constant must be True
        assert HUMAN_AUTHORITY_ABSOLUTE is True

    def test_autonomous_forbidden_constant_matches_docs(self):
        """Verify AUTONOMOUS_EXECUTION_ALLOWED matches docs (must be False)."""
        from python.phase01_core.constants import AUTONOMOUS_EXECUTION_ALLOWED
        
        # Documentation says no autonomous execution
        # Constant must be False
        assert AUTONOMOUS_EXECUTION_ALLOWED is False

    def test_background_forbidden_constant_matches_docs(self):
        """Verify BACKGROUND_EXECUTION_ALLOWED matches docs (must be False)."""
        from python.phase01_core.constants import BACKGROUND_EXECUTION_ALLOWED
        
        # Documentation says no background actions
        # Constant must be False
        assert BACKGROUND_EXECUTION_ALLOWED is False

    def test_mutation_confirmation_constant_matches_docs(self):
        """Verify MUTATION_REQUIRES_HUMAN_CONFIRMATION matches docs."""
        from python.phase01_core.constants import MUTATION_REQUIRES_HUMAN_CONFIRMATION
        
        # Documentation says mutations require human confirmation
        # Constant must be True
        assert MUTATION_REQUIRES_HUMAN_CONFIRMATION is True

    def test_audit_required_constant_matches_docs(self):
        """Verify AUDIT_REQUIRED matches docs (must be True)."""
        from python.phase01_core.constants import AUDIT_REQUIRED
        
        # Documentation says everything is auditable
        # Constant must be True
        assert AUDIT_REQUIRED is True


class TestInvariantsDocumentationMatch:
    """Verify invariants match their documented purpose."""

    def test_all_invariants_match_no_disable_principle(self):
        """Verify no invariant can be disabled (matches docs)."""
        from python.phase01_core.invariants import get_all_invariants
        
        all_inv = get_all_invariants()
        
        # Documentation says invariants cannot be disabled
        # All values must be True
        for name, value in all_inv.items():
            assert value is True, f"{name} must be True (cannot be disabled)"

    def test_invariant_count_matches_docs(self):
        """Verify number of invariants matches documentation."""
        from python.phase01_core.invariants import get_all_invariants
        
        # Phase-01 documentation specifies 7 core invariants
        all_inv = get_all_invariants()
        assert len(all_inv) == 7, f"Expected 7 invariants, got {len(all_inv)}"


class TestIdentitiesDocumentationMatch:
    """Verify identities match their documented purpose."""

    def test_human_identity_matches_docs(self):
        """Verify HUMAN identity matches documented behavior."""
        from python.phase01_core.identities import HUMAN
        
        # Documentation says HUMAN is authoritative
        assert HUMAN.is_authoritative is True
        assert HUMAN.can_initiate is True
        assert HUMAN.can_confirm is True
        assert HUMAN.can_be_overridden is False

    def test_system_identity_matches_docs(self):
        """Verify SYSTEM identity matches documented behavior."""
        from python.phase01_core.identities import SYSTEM
        
        # Documentation says SYSTEM is non-authoritative
        assert SYSTEM.is_authoritative is False
        assert SYSTEM.can_initiate is False
        assert SYSTEM.can_confirm is False
        assert SYSTEM.can_be_overridden is True

    def test_identity_count_matches_docs(self):
        """Verify number of identities matches documentation."""
        from python.phase01_core.identities import get_all_identities
        
        # Documentation specifies exactly 2 identities: HUMAN and SYSTEM
        all_ids = get_all_identities()
        assert len(all_ids) == 2
        assert 'HUMAN' in all_ids
        assert 'SYSTEM' in all_ids
