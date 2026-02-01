"""
Phase-31 Observation Point Tests.

Tests all 5 observation points for evidence capture.
"""
import pytest

from HUMANOID_HUNTER.observation import (
    ObservationPoint,
    EvidenceType,
    ObservationContext,
    EvidenceChain,
    capture_evidence,
    attach_observer,
    create_empty_chain,
    validate_chain
)


class TestObservationPointsExist:
    """Test that all 5 observation points exist."""
    
    def test_pre_dispatch_exists(self) -> None:
        """PRE_DISPATCH observation point exists."""
        assert ObservationPoint.PRE_DISPATCH is not None
        assert ObservationPoint.PRE_DISPATCH.name == "PRE_DISPATCH"
    
    def test_post_dispatch_exists(self) -> None:
        """POST_DISPATCH observation point exists."""
        assert ObservationPoint.POST_DISPATCH is not None
        assert ObservationPoint.POST_DISPATCH.name == "POST_DISPATCH"
    
    def test_pre_evaluate_exists(self) -> None:
        """PRE_EVALUATE observation point exists."""
        assert ObservationPoint.PRE_EVALUATE is not None
        assert ObservationPoint.PRE_EVALUATE.name == "PRE_EVALUATE"
    
    def test_post_evaluate_exists(self) -> None:
        """POST_EVALUATE observation point exists."""
        assert ObservationPoint.POST_EVALUATE is not None
        assert ObservationPoint.POST_EVALUATE.name == "POST_EVALUATE"
    
    def test_halt_entry_exists(self) -> None:
        """HALT_ENTRY observation point exists."""
        assert ObservationPoint.HALT_ENTRY is not None
        assert ObservationPoint.HALT_ENTRY.name == "HALT_ENTRY"
    
    def test_exactly_five_observation_points(self) -> None:
        """Verify exactly 5 observation points (closed enum)."""
        assert len(ObservationPoint) == 5


class TestObservationPointCapture:
    """Test evidence capture at each observation point."""
    
    @pytest.fixture
    def valid_context(self) -> ObservationContext:
        """Create a valid observation context."""
        return attach_observer(
            loop_id="LOOP-test123",
            executor_id="EXEC-test456",
            envelope_hash="abc123hash",
            timestamp="2026-01-25T19:00:00-05:00"
        )
    
    @pytest.fixture
    def empty_chain(self) -> EvidenceChain:
        """Create an empty evidence chain."""
        return create_empty_chain("CHAIN-test")
    
    def test_capture_at_pre_dispatch(
        self, valid_context: ObservationContext, empty_chain: EvidenceChain
    ) -> None:
        """Capture evidence at PRE_DISPATCH point."""
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"init_to_dispatched",
            timestamp="2026-01-25T19:01:00-05:00",
            prior_chain=empty_chain
        )
        
        assert chain.length == 1
        assert chain.records[0].observation_point == ObservationPoint.PRE_DISPATCH
        assert validate_chain(chain)
    
    def test_capture_at_post_dispatch(
        self, valid_context: ObservationContext, empty_chain: EvidenceChain
    ) -> None:
        """Capture evidence at POST_DISPATCH point."""
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.POST_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"dispatched_to_awaiting",
            timestamp="2026-01-25T19:02:00-05:00",
            prior_chain=empty_chain
        )
        
        assert chain.length == 1
        assert chain.records[0].observation_point == ObservationPoint.POST_DISPATCH
        assert validate_chain(chain)
    
    def test_capture_at_pre_evaluate(
        self, valid_context: ObservationContext, empty_chain: EvidenceChain
    ) -> None:
        """Capture evidence at PRE_EVALUATE point."""
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.PRE_EVALUATE,
            evidence_type=EvidenceType.EXECUTOR_OUTPUT,
            raw_data=b"raw_executor_output",
            timestamp="2026-01-25T19:03:00-05:00",
            prior_chain=empty_chain
        )
        
        assert chain.length == 1
        assert chain.records[0].observation_point == ObservationPoint.PRE_EVALUATE
        assert validate_chain(chain)
    
    def test_capture_at_post_evaluate(
        self, valid_context: ObservationContext, empty_chain: EvidenceChain
    ) -> None:
        """Capture evidence at POST_EVALUATE point."""
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.POST_EVALUATE,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"evaluated_to_next",
            timestamp="2026-01-25T19:04:00-05:00",
            prior_chain=empty_chain
        )
        
        assert chain.length == 1
        assert chain.records[0].observation_point == ObservationPoint.POST_EVALUATE
        assert validate_chain(chain)
    
    def test_capture_at_halt_entry(
        self, valid_context: ObservationContext, empty_chain: EvidenceChain
    ) -> None:
        """Capture evidence at HALT_ENTRY point."""
        chain = capture_evidence(
            context=valid_context,
            observation_point=ObservationPoint.HALT_ENTRY,
            evidence_type=EvidenceType.STOP_CONDITION,
            raw_data=b"halt_triggered",
            timestamp="2026-01-25T19:05:00-05:00",
            prior_chain=empty_chain
        )
        
        assert chain.length == 1
        assert chain.records[0].observation_point == ObservationPoint.HALT_ENTRY
        assert validate_chain(chain)
