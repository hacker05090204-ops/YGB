# G05: Assistant Mode
"""
Explain-only intelligence layer.

Shows:
- Selected method and why
- Rejected methods and why
- AMSE proposed methods

Human approval MANDATORY for:
- Execution
- Mode switch
- Headless browser
"""

from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
import logging
from typing import Callable, Deque, Dict, List, Optional, Tuple, Union
import uuid


LOGGER = logging.getLogger(__name__)
_QUERY_LOG_LIMIT = 120
_MAX_SESSION_LOG_SIZE = 1000


class AssistantMode(Enum):
    """Closed assistant interaction modes."""
    PASSIVE = "PASSIVE"
    INTERACTIVE = "INTERACTIVE"


class MethodDecision(Enum):
    """CLOSED ENUM - 3 decisions"""
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    PROPOSED = "PROPOSED"  # From AMSE


@dataclass(frozen=True)
class MethodExplanation:
    """Explanation for a method decision."""
    method_id: str
    method_name: str
    decision: MethodDecision
    reason: str
    confidence: float  # 0.0 - 1.0
    alternatives: tuple  # Tuple of method IDs


@dataclass(frozen=True)
class AssistantExplanation:
    """Full assistant explanation output."""
    explanation_id: str
    mode: AssistantMode
    selected_method: Optional[MethodExplanation]
    rejected_methods: tuple  # Tuple[MethodExplanation, ...]
    amse_proposals: tuple    # Tuple[MethodExplanation, ...]
    summary: str
    requires_approval: bool
    approval_reason: str
    timestamp: str


@dataclass(frozen=True)
class AssistantSession:
    """Assistant session bound to real system state queries."""
    session_id: str
    mode: AssistantMode
    started_at: str
    turn_count: int
    last_query: Optional[str]


class SessionLog:
    """Append-only bounded session log."""

    def __init__(self, max_sessions: int = _MAX_SESSION_LOG_SIZE):
        self._sessions: Deque[AssistantSession] = deque(maxlen=max_sessions)

    def append(self, session: AssistantSession) -> None:
        self._sessions.append(session)

    def entries(self) -> Tuple[AssistantSession, ...]:
        return tuple(self._sessions)

    def __len__(self) -> int:
        return len(self._sessions)


RealStateProvider = Callable[[str], Union[str, Tuple[bool, str], None]]


class AssistantController:
    """Controller that answers only from real system state providers."""

    def __init__(
        self,
        state_provider: Optional[RealStateProvider] = None,
        session_log: Optional[SessionLog] = None,
    ):
        self._state_provider = state_provider
        self._sessions: Dict[str, AssistantSession] = {}
        self._session_log = session_log or SessionLog()

    @property
    def session_log(self) -> SessionLog:
        return self._session_log

    def start_session(self, mode: Union[AssistantMode, str]) -> AssistantSession:
        resolved_mode = self._resolve_mode(mode)
        session = AssistantSession(
            session_id=f"AST-{uuid.uuid4().hex[:16].upper()}",
            mode=resolved_mode,
            started_at=datetime.now(UTC).isoformat(),
            turn_count=0,
            last_query=None,
        )
        self._sessions[session.session_id] = session
        self._session_log.append(session)
        LOGGER.info(
            "Assistant session started session_id=%s mode=%s",
            session.session_id,
            session.mode.value,
        )
        return session

    def handle_query(self, session_id: str, query: str) -> str:
        if session_id not in self._sessions:
            raise KeyError(f"Unknown assistant session: {session_id}")

        LOGGER.info(
            "Assistant query session_id=%s query=%s",
            session_id,
            _truncate_for_log(query),
        )

        session = self._sessions[session_id]
        self._sessions[session_id] = replace(
            session,
            turn_count=session.turn_count + 1,
            last_query=query,
        )

        unavailable_reason = self._get_unavailable_reason(query)
        if unavailable_reason is not None:
            return f"Data unavailable: {unavailable_reason}"

        return self._get_real_state_response(query)

    def get_session(self, session_id: str) -> AssistantSession:
        return self._sessions[session_id]

    def _resolve_mode(self, mode: Union[AssistantMode, str]) -> AssistantMode:
        if isinstance(mode, AssistantMode):
            return mode

        normalized_mode = str(mode).strip().upper()
        if normalized_mode == "AUTONOMOUS":
            raise ValueError("AUTONOMOUS mode is not allowed")

        try:
            return AssistantMode[normalized_mode]
        except KeyError as exc:
            raise ValueError(f"Unsupported assistant mode: {mode}") from exc

    def _get_unavailable_reason(self, query: str) -> Optional[str]:
        if self._state_provider is None:
            return "no real system state provider configured"

        provider_result = self._state_provider(query)
        if isinstance(provider_result, tuple):
            available, payload = provider_result
            if not available:
                return str(payload)
            return None

        if provider_result is None:
            return "no matching real system data"

        return None

    def _get_real_state_response(self, query: str) -> str:
        if self._state_provider is None:
            return "Data unavailable: no real system state provider configured"

        provider_result = self._state_provider(query)
        if isinstance(provider_result, tuple):
            available, payload = provider_result
            if not available:
                return f"Data unavailable: {payload}"
            return str(payload)

        if provider_result is None:
            return "Data unavailable: no matching real system data"

        return provider_result


class AssistantContext:
    """Context for assistant explanations."""
    
    def __init__(self, mode: AssistantMode = AssistantMode.PASSIVE):
        self._mode = mode
        self._explanations: List[AssistantExplanation] = []
    
    @property
    def mode(self) -> AssistantMode:
        return self._mode
    
    def get_explanations(self) -> List[AssistantExplanation]:
        return list(self._explanations)
    
    def explain_selection(
        self,
        selected: MethodExplanation,
        rejected: List[MethodExplanation],
        amse_proposals: List[MethodExplanation],
        requires_approval: bool = False,
        approval_reason: str = "",
    ) -> AssistantExplanation:
        """Create an explanation for method selection."""
        
        summary_parts = [f"Selected: {selected.method_name}"]
        if rejected:
            summary_parts.append(f"Rejected {len(rejected)} alternative(s)")
        if amse_proposals:
            summary_parts.append(f"AMSE proposed {len(amse_proposals)} new method(s)")
        
        explanation = AssistantExplanation(
            explanation_id=f"EXP-{uuid.uuid4().hex[:16].upper()}",
            mode=self._mode,
            selected_method=selected,
            rejected_methods=tuple(rejected),
            amse_proposals=tuple(amse_proposals),
            summary=". ".join(summary_parts),
            requires_approval=requires_approval,
            approval_reason=approval_reason,
            timestamp=datetime.now(UTC).isoformat(),
        )
        
        self._explanations.append(explanation)
        return explanation


def create_method_explanation(
    method_id: str,
    method_name: str,
    decision: MethodDecision,
    reason: str,
    confidence: float = 0.5,
    alternatives: Optional[List[str]] = None,
) -> MethodExplanation:
    """Create a method explanation."""
    return MethodExplanation(
        method_id=method_id,
        method_name=method_name,
        decision=decision,
        reason=reason,
        confidence=max(0.0, min(1.0, confidence)),
        alternatives=tuple(alternatives or []),
    )


def requires_human_approval(explanation: AssistantExplanation) -> Tuple[bool, str]:
    """Check if explanation requires human approval."""
    if explanation.requires_approval:
        return True, explanation.approval_reason
    
    # Low confidence always requires approval
    if explanation.selected_method and explanation.selected_method.confidence < 0.5:
        return True, "Low confidence selection"
    
    # Multiple AMSE proposals require review
    if len(explanation.amse_proposals) > 2:
        return True, "Multiple AMSE proposals require review"
    
    return False, ""


def _truncate_for_log(query: str, limit: int = _QUERY_LOG_LIMIT) -> str:
    """Truncate query text for logging without exceeding the limit."""
    return query[:limit]
