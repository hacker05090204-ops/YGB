"""
Explanation Composer - Phase-08 Evidence Orchestration.
REIMPLEMENTED-2026

Pure functions for composing evidence narratives.
No execution logic - narrative composition only.
"""

from typing import Tuple, Dict

from python.phase06_decision.decision_types import FinalDecision
from python.phase07_knowledge.bug_types import BugType
from python.phase07_knowledge.explanations import BugExplanation
from python.phase08_evidence.evidence_steps import EvidenceStep
from python.phase08_evidence.narrative import EvidenceNarrative


# Decision-specific title templates
_TITLE_TEMPLATES: Dict[FinalDecision, Tuple[str, str]] = {
    FinalDecision.ALLOW: (
        "Allowed: {bug_title}",
        "अनुमति: {bug_title}"
    ),
    FinalDecision.DENY: (
        "Denied: {bug_title}",
        "अस्वीकृत: {bug_title}"
    ),
    FinalDecision.ESCALATE: (
        "Escalate for Review: {bug_title}",
        "समीक्षा के लिए बढ़ाएं: {bug_title}"
    ),
}

# Decision-specific recommendation templates
_RECOMMENDATION_TEMPLATES: Dict[FinalDecision, Tuple[str, str]] = {
    FinalDecision.ALLOW: (
        "This action has been approved. Proceed with appropriate caution and follow security best practices.",
        "इस कार्रवाई को मंजूरी दी गई है। उचित सावधानी के साथ आगे बढ़ें और सुरक्षा सर्वोत्तम प्रथाओं का पालन करें।"
    ),
    FinalDecision.DENY: (
        "This action has been denied due to security concerns. Address the identified vulnerability before proceeding.",
        "सुरक्षा चिंताओं के कारण इस कार्रवाई को अस्वीकार कर दिया गया है। आगे बढ़ने से पहले पहचानी गई कमजोरी को दूर करें।"
    ),
    FinalDecision.ESCALATE: (
        "This action requires human review. Please consult with a security expert before proceeding.",
        "इस कार्रवाई के लिए मानव समीक्षा की आवश्यकता है। आगे बढ़ने से पहले किसी सुरक्षा विशेषज्ञ से परामर्श करें।"
    ),
}


def get_recommendation(
    decision: FinalDecision,
    bug_type: BugType
) -> Tuple[str, str]:
    """
    Get recommendation text in (English, Hindi).
    
    Returns explicit recommendations based on decision.
    This function is PURE - no side effects.
    
    Args:
        decision: The FinalDecision from Phase-06
        bug_type: The BugType from Phase-07
        
    Returns:
        Tuple of (English recommendation, Hindi recommendation)
    """
    return _RECOMMENDATION_TEMPLATES.get(
        decision,
        _RECOMMENDATION_TEMPLATES[FinalDecision.DENY]
    )


def compose_narrative(
    decision: FinalDecision,
    bug_explanation: BugExplanation
) -> EvidenceNarrative:
    """
    Compose a narrative from decision and knowledge.
    
    This function is PURE:
    - No side effects
    - No guessing
    - Deterministic
    - No network calls
    - No file access
    
    Args:
        decision: The FinalDecision from Phase-06
        bug_explanation: The BugExplanation from Phase-07
        
    Returns:
        EvidenceNarrative combining decision and knowledge
    """
    bug_type = bug_explanation.bug_type
    
    # Get templates
    title_en_template, title_hi_template = _TITLE_TEMPLATES.get(
        decision,
        _TITLE_TEMPLATES[FinalDecision.DENY]
    )
    
    # Format titles with bug title
    title_en = title_en_template.format(bug_title=bug_explanation.title_en)
    title_hi = title_hi_template.format(bug_title=bug_explanation.title_hi)
    
    # Get recommendations
    rec_en, rec_hi = get_recommendation(decision, bug_type)
    
    # Create narrative
    return EvidenceNarrative(
        step=EvidenceStep.EXPLANATION,
        decision=decision,
        bug_type=bug_type,
        title_en=title_en,
        title_hi=title_hi,
        summary_en=bug_explanation.description_en,
        summary_hi=bug_explanation.description_hi,
        recommendation_en=rec_en,
        recommendation_hi=rec_hi
    )
