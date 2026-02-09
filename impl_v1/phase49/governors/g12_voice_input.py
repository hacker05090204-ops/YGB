# G12: Voice Command Input
"""
Voice → Text → Intent extraction.

VOICE CAN:
- Say target
- Say scope
- Ask status/progress
- Ask to find targets

VOICE CANNOT:
- Approve execution
- Trigger browser
- Change system state

FLOW: Voice → Intent Object → Dashboard Router
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
import uuid
from datetime import datetime, UTC
import re


class VoiceIntentType(Enum):
    """CLOSED ENUM - 10 intent types (added GPU and training)"""
    SET_TARGET = "SET_TARGET"
    SET_SCOPE = "SET_SCOPE"
    QUERY_STATUS = "QUERY_STATUS"
    QUERY_PROGRESS = "QUERY_PROGRESS"
    QUERY_GPU = "QUERY_GPU"  # NEW: GPU status
    QUERY_TRAINING = "QUERY_TRAINING"  # NEW: Training metrics
    FIND_TARGETS = "FIND_TARGETS"
    SCREEN_TAKEOVER = "SCREEN_TAKEOVER"  # READ-ONLY inspection
    REPORT_HELP = "REPORT_HELP"  # High impact tips
    UNKNOWN = "UNKNOWN"


class VoiceInputStatus(Enum):
    """CLOSED ENUM - 4 statuses"""
    PARSED = "PARSED"
    INVALID = "INVALID"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class VoiceIntent:
    """Extracted intent from voice input."""
    intent_id: str
    intent_type: VoiceIntentType
    raw_text: str
    extracted_value: Optional[str]
    confidence: float  # 0.0-1.0
    status: VoiceInputStatus
    block_reason: Optional[str]
    timestamp: str


# Forbidden patterns that would trigger execution
FORBIDDEN_PATTERNS = [
    r'\b(execute|run|start|launch|attack|exploit|hack)\b',
    r'\b(approve|confirm|yes\s+do\s+it)\b',
    r'\b(submit|send|post)\b',
]

# Intent patterns (English)
INTENT_PATTERNS = {
    VoiceIntentType.SET_TARGET: [
        r'(?:set\s+)?target\s+(?:is\s+|to\s+)?(.+)',
        r'(?:scan|check|analyze)\s+(.+)',
        r'(?:look\s+at)\s+(.+)',
    ],
    VoiceIntentType.SET_SCOPE: [
        r'(?:set\s+)?scope\s+(?:is\s+|to\s+)?(.+)',
        r'(?:scope|limit)\s+to\s+(.+)',
        r'(?:only|just)\s+(.+)',
    ],
    VoiceIntentType.QUERY_STATUS: [
        r'(?:what\s+is\s+the\s+)?status',
        r'(?:current\s+)?state',
        r'(?:how\s+are\s+we|where\s+are\s+we)',
    ],
    VoiceIntentType.QUERY_PROGRESS: [
        r'(?:what\s+is\s+the\s+)?progress',
        r'(?:how\s+far|how\s+long)',
        r'(?:percentage|completion)',
    ],
    VoiceIntentType.FIND_TARGETS: [
        r'(?:find|discover|search\s+for)\s+targets?',
        r'(?:show\s+me|list)\s+(?:bug\s+)?bounty',
        r'(?:suggest|recommend)\s+targets?',
    ],
    VoiceIntentType.SCREEN_TAKEOVER: [
        r'takeover\s+(?:the\s+)?screen',
        r'screen\s+takeover',
        r'show\s+(?:me\s+)?(?:the\s+)?screen',
        r'inspect\s+screen',
    ],
    VoiceIntentType.REPORT_HELP: [
        r'(?:is\s+)?report\s+(?:me|mein)\s+(?:aur\s+)?kya\s+add',
        r'high\s+impact\s+(?:tips?|suggestions?)',
        r'(?:how\s+to\s+)?increase\s+payout',
        r'improve\s+(?:the\s+)?report',
    ],
    # NEW: GPU status queries
    VoiceIntentType.QUERY_GPU: [
        r'(?:show|check|what\s+is)\s+(?:the\s+)?gpu',
        r'gpu\s+(?:status|usage|utilization)',
        r'(?:is\s+)?gpu\s+(?:working|active)',
        r'(?:how\s+is\s+)?(?:the\s+)?graphics\s+card',
    ],
    # NEW: Training metrics queries
    VoiceIntentType.QUERY_TRAINING: [
        r'(?:show|check)\s+(?:the\s+)?training',
        r'training\s+(?:status|progress|metrics)',
        r'(?:what\s+is\s+)?(?:the\s+)?(?:current\s+)?epoch',
        r'(?:how\s+is\s+)?(?:the\s+)?model\s+(?:doing|training)',
        r'(?:show\s+)?loss\s+(?:value|graph)?',
        r'(?:what\s+is\s+)?(?:the\s+)?accuracy',
    ],
}

# Hindi intent patterns (merged with English)
HINDI_PATTERNS = {
    VoiceIntentType.SET_TARGET: [
        r'(?:ye\s+)?mera\s+target\s+(?:hai\s+)?(.+)',
        r'target\s+set\s+karo\s+(.+)',
        r'target\s+ye\s+hai\s+(.+)',
    ],
    VoiceIntentType.SET_SCOPE: [
        r'scope\s+ye\s+hai\s+(.+)',
        r'scope\s+set\s+karo\s+(.+)',
        r'sirf\s+(.+)',
    ],
    VoiceIntentType.QUERY_STATUS: [
        r'status\s+batao',
        r'kya\s+(?:hal|haal)\s+hai',
        r'kahan\s+tak\s+hua',
    ],
    VoiceIntentType.QUERY_PROGRESS: [
        r'progress\s+kitna\s+hua',
        r'kitna\s+complete\s+hua',
        r'kab\s+tak\s+hoga',
    ],
    VoiceIntentType.FIND_TARGETS: [
        r'program\s+start\s+karo\s+(?:aur\s+)?(?:accha\s+)?target\s+dhundo',
        r'targets?\s+dhundo',
        r'(?:accha|acha)\s+target\s+(?:batao|dhundo)',
    ],
    VoiceIntentType.SCREEN_TAKEOVER: [
        r'screen\s+(?:dekho|dikhao)',
        r'screen\s+takeover\s+karo',
    ],
    VoiceIntentType.REPORT_HELP: [
        r'(?:is\s+)?report\s+(?:me|mein)\s+(?:aur\s+)?kya\s+add\s+(?:kar\s+)?sakte\s+(?:hain|hai)',
        r'payout\s+(?:kaise\s+)?(?:badhao|increase\s+karo)',
        r'high\s+impact\s+ke\s+liye',
    ],
}


def is_forbidden_command(text: str) -> tuple:
    """Check if voice command tries to trigger execution. Returns (forbidden, reason)."""
    text_lower = text.lower()
    
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True, f"Forbidden pattern detected: {pattern}"
    
    return False, ""


def extract_intent(raw_text: str) -> VoiceIntent:
    """Extract intent from voice command text (English and Hindi)."""
    text = raw_text.strip()
    
    # Check for forbidden commands
    forbidden, reason = is_forbidden_command(text)
    if forbidden:
        return VoiceIntent(
            intent_id=f"VOC-{uuid.uuid4().hex[:16].upper()}",
            intent_type=VoiceIntentType.UNKNOWN,
            raw_text=raw_text,
            extracted_value=None,
            confidence=0.0,
            status=VoiceInputStatus.BLOCKED,
            block_reason=reason,
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    # Try to match intent patterns
    text_lower = text.lower()
    
    # Check English patterns first
    for intent_type, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                # Extract value if capture group exists
                extracted = match.group(1) if match.lastindex else None
                
                return VoiceIntent(
                    intent_id=f"VOC-{uuid.uuid4().hex[:16].upper()}",
                    intent_type=intent_type,
                    raw_text=raw_text,
                    extracted_value=extracted,
                    confidence=0.8,
                    status=VoiceInputStatus.PARSED,
                    block_reason=None,
                    timestamp=datetime.now(UTC).isoformat(),
                )
    
    # Check Hindi patterns
    for intent_type, patterns in HINDI_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                extracted = match.group(1) if match.lastindex else None
                
                return VoiceIntent(
                    intent_id=f"VOC-{uuid.uuid4().hex[:16].upper()}",
                    intent_type=intent_type,
                    raw_text=raw_text,
                    extracted_value=extracted,
                    confidence=0.75,  # Slightly lower for Hindi parsing
                    status=VoiceInputStatus.PARSED,
                    block_reason=None,
                    timestamp=datetime.now(UTC).isoformat(),
                )
    
    # Unknown intent
    return VoiceIntent(
        intent_id=f"VOC-{uuid.uuid4().hex[:16].upper()}",
        intent_type=VoiceIntentType.UNKNOWN,
        raw_text=raw_text,
        extracted_value=None,
        confidence=0.0,
        status=VoiceInputStatus.INVALID,
        block_reason="Could not parse intent",
        timestamp=datetime.now(UTC).isoformat(),
    )


def can_voice_trigger_execution(intent: VoiceIntent) -> tuple:
    """Check if voice intent can trigger execution. Returns (can_trigger, reason)."""
    # Voice can NEVER trigger execution
    return False, "Voice commands cannot trigger execution - dashboard approval required"


def validate_voice_input(text: str) -> VoiceIntent:
    """Validate and parse voice input. Main entry point."""
    if not text or not text.strip():
        return VoiceIntent(
            intent_id=f"VOC-{uuid.uuid4().hex[:16].upper()}",
            intent_type=VoiceIntentType.UNKNOWN,
            raw_text=text or "",
            extracted_value=None,
            confidence=0.0,
            status=VoiceInputStatus.INVALID,
            block_reason="Empty voice input",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    return extract_intent(text)
