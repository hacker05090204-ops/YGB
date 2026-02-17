"""
Query Router — Dual-Mode Voice Classifier

Routes voice queries to either SECURITY or RESEARCH mode.

RULES:
  - Security Mode = existing intent parser (targets, scans, vulns)
  - Research Mode = isolated Edge search pipeline (knowledge queries)
  - Ambiguous queries default to SECURITY (safer)
  - No research query can trigger execution
  - No research query can access training/governance
"""

import re
import subprocess
import html
import os
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# =========================================================================
# TYPES
# =========================================================================

class VoiceMode(Enum):
    """CLOSED ENUM - 3 modes only."""
    SECURITY = "SECURITY"
    RESEARCH = "RESEARCH"
    CLARIFICATION = "CLARIFICATION"


class ResearchStatus(Enum):
    """CLOSED ENUM - Research query result status."""
    SUCCESS = "SUCCESS"
    NO_RESULTS = "NO_RESULTS"
    BLOCKED = "BLOCKED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RouteDecision:
    """Result of query routing classification."""
    mode: VoiceMode
    confidence: float        # 0.0 - 1.0
    reason: str
    matched_keywords: tuple  # Tuple[str, ...]
    timestamp: str


@dataclass(frozen=True)
class ResearchResult:
    """Result of a research query."""
    query: str
    status: ResearchStatus
    title: str
    summary: str
    source: str
    key_terms: tuple         # Tuple[str, ...]
    word_count: int
    elapsed_ms: float
    mode: VoiceMode          # Always RESEARCH
    timestamp: str


# =========================================================================
# KEYWORD WEIGHTS — used for weighted scoring classification
# =========================================================================

CONFIDENCE_THRESHOLD = 0.75  # Above this → route to winning mode
LOW_CONFIDENCE_THRESHOLD = 0.6  # Below this → RESEARCH or CLARIFICATION

# Security keywords with per-keyword weights
SECURITY_KEYWORD_WEIGHTS: Dict[str, float] = {
    # Vulnerability types — high weight
    "vulnerability": 2.0, "vuln": 2.0, "cve": 2.5, "exploit": 2.0,
    "cvss": 2.0, "injection": 1.5, "xss": 2.5, "sqli": 2.5,
    "idor": 2.5, "rce": 2.5, "ssrf": 2.5, "csrf": 2.5,
    "lfi": 2.5, "rfi": 2.5, "xxe": 2.5,
    # Operations — medium weight
    "target": 1.5, "scan": 1.5, "recon": 1.5, "reconnaissance": 1.5,
    "scope": 1.5, "bounty": 1.5, "severity": 1.5, "payload": 2.0,
    "vector": 1.5, "attack": 2.0, "pentest": 2.0, "penetration": 2.0,
    "poc": 2.0, "proof": 1.0,
    # Security tools — medium weight
    "burp": 1.5, "nmap": 1.5, "gobuster": 1.5, "nuclei": 1.5,
    "subfinder": 1.5, "amass": 1.5, "dirsearch": 1.5, "nikto": 1.5,
    "sqlmap": 1.5,
    # Bug bounty — medium weight
    "hackerone": 1.5, "bugcrowd": 1.5, "synack": 1.5, "intigriti": 1.5,
    "payout": 1.0, "report": 1.0, "triage": 1.5, "duplicate": 1.0,
    # System queries — low weight
    "gpu": 1.0, "training": 1.0, "epoch": 1.0, "loss": 1.0,
    "accuracy": 1.0, "model": 1.0, "status": 0.5, "progress": 0.5,
    # Hunting system — medium weight (routes through security pipeline)
    "find target": 2.0, "find good target": 2.0, "suggest target": 2.0,
    "generate report": 2.0, "build report": 2.0, "export report": 1.5,
    "hunt": 1.5, "start hunting": 2.0, "replay": 1.0,
    "evidence": 1.0, "screenshot": 1.0, "auto mode": 1.5,
}

# Research keywords with per-keyword weights
RESEARCH_KEYWORD_WEIGHTS: Dict[str, float] = {
    # General knowledge triggers — high weight
    "what is": 2.0, "what are": 2.0, "what was": 2.0, "what were": 2.0,
    "define": 2.0, "explain": 2.0, "meaning": 1.5, "definition": 2.0,
    "how does": 1.5, "how do": 1.5, "how is": 1.5, "how are": 1.5,
    "how to": 1.5, "how can": 1.5,
    "who is": 2.0, "who was": 2.0, "who invented": 2.0, "who discovered": 2.0,
    "when was": 1.5, "when did": 1.5, "when is": 1.5,
    "where is": 1.5, "where was": 1.5, "where are": 1.5,
    "why is": 1.5, "why does": 1.5, "why do": 1.5, "why are": 1.5,
    "tell me about": 2.0, "describe": 1.5,
    "history of": 1.5, "origin of": 1.5,
    "difference between": 2.0,
    "translate": 1.0, "calculate": 1.0, "convert": 1.0,
    # Informational — medium weight
    "science": 1.0, "physics": 1.0, "chemistry": 1.0, "biology": 1.0,
    "mathematics": 1.0, "math": 1.0, "geography": 1.0, "literature": 1.0,
    "programming": 1.0, "algorithm": 1.0,
    # Hindi knowledge triggers — medium weight
    "kya hai": 1.5, "kya hota hai": 1.5, "kya karte hain": 1.5,
    "kya matlab hai": 1.5, "batao": 1.5, "samjhao": 1.5,
}

# Backward-compatible frozensets (for existing tests)
SECURITY_KEYWORDS = frozenset(SECURITY_KEYWORD_WEIGHTS.keys())
RESEARCH_KEYWORDS = frozenset(RESEARCH_KEYWORD_WEIGHTS.keys())

# Patterns that indicate research mode
RESEARCH_PATTERNS = [
    r'^what\s+(?:is|are|was|were)\s+',
    r'^(?:who|when|where|why|how)\s+',
    r'^define\s+',
    r'^explain\s+',
    r'^tell\s+me\s+about\s+',
    r'^(?:what|kya)\s+(?:is|hai|hota)',
    r'^history\s+of\s+',
    r'^difference\s+between\s+',
    r'^meaning\s+of\s+',
    r'\bkya\s+hai\b',
    r'\bsamjhao\b',
    r'\bbatao\b.*\bkya\b',
]

# =========================================================================
# QUERY ROUTER
# =========================================================================

class QueryRouter:
    """Classifies voice queries into SECURITY or RESEARCH mode using weighted scoring."""

    def classify(self, text: str) -> RouteDecision:
        """Classify a voice query. Returns routing decision with confidence."""
        text_lower = text.lower().strip()
        if not text_lower:
            return RouteDecision(
                mode=VoiceMode.SECURITY,
                confidence=1.0,
                reason="Empty query defaults to security",
                matched_keywords=(),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # Weighted keyword scoring
        security_score = 0.0
        research_score = 0.0
        security_matches: List[str] = []
        research_matches: List[str] = []

        for kw, weight in SECURITY_KEYWORD_WEIGHTS.items():
            if kw in text_lower:
                security_score += weight
                security_matches.append(kw)

        for kw, weight in RESEARCH_KEYWORD_WEIGHTS.items():
            if kw in text_lower:
                research_score += weight
                research_matches.append(kw)

        # Research pattern regex bonus (+3.0 weight)
        research_pattern_match = False
        for pattern in RESEARCH_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                research_pattern_match = True
                research_score += 3.0
                research_matches.append(f"pattern:{pattern[:30]}")
                break

        # Compute confidence for each mode
        total_score = security_score + research_score
        if total_score == 0:
            # No keywords matched — ask clarification instead of defaulting
            return RouteDecision(
                mode=VoiceMode.CLARIFICATION,
                confidence=0.0,
                reason="No keywords matched. Please clarify your query.",
                matched_keywords=(),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        research_confidence = research_score / total_score if total_score > 0 else 0.0
        security_confidence = security_score / total_score if total_score > 0 else 0.0

        # Cap at 0.99
        research_confidence = min(0.99, research_confidence)
        security_confidence = min(0.99, security_confidence)

        # Decision with threshold enforcement
        if research_confidence >= CONFIDENCE_THRESHOLD:
            return RouteDecision(
                mode=VoiceMode.RESEARCH,
                confidence=round(research_confidence, 4),
                reason=f"Research confidence {research_confidence:.2f} >= threshold {CONFIDENCE_THRESHOLD}",
                matched_keywords=tuple(research_matches[:5]),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        elif security_confidence >= CONFIDENCE_THRESHOLD:
            return RouteDecision(
                mode=VoiceMode.SECURITY,
                confidence=round(security_confidence, 4),
                reason=f"Security confidence {security_confidence:.2f} >= threshold {CONFIDENCE_THRESHOLD}",
                matched_keywords=tuple(security_matches[:5]),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        elif max(research_confidence, security_confidence) < LOW_CONFIDENCE_THRESHOLD:
            # Both below 0.6 — route to RESEARCH for knowledge expansion
            return RouteDecision(
                mode=VoiceMode.RESEARCH,
                confidence=round(max(research_confidence, 0.3), 4),
                reason=f"Low confidence ({max(research_confidence, security_confidence):.2f} < {LOW_CONFIDENCE_THRESHOLD}), routing to Research",
                matched_keywords=tuple((research_matches + security_matches)[:5]),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        else:
            # Ambiguous (0.6-0.75) — ask clarification
            return RouteDecision(
                mode=VoiceMode.CLARIFICATION,
                confidence=round(max(security_confidence, research_confidence), 4),
                reason=f"Ambiguous ({max(security_confidence, research_confidence):.2f}). Did you mean a security operation or a research question?",
                matched_keywords=tuple((security_matches + research_matches)[:5]),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )


# =========================================================================
# RESEARCH SEARCH PIPELINE (Python side, mirrors C++ engine)
# =========================================================================

# Blocked content patterns — research queries cannot contain these
BLOCKED_RESEARCH_PATTERNS = [
    r'\b(execute|run|start|launch|attack|exploit|hack)\b',
    r'\b(approve|confirm|submit|send|post)\b',
    r'\b(delete|drop|truncate|rm\s+-rf)\b',
    r'\b(sudo|chmod|chown|passwd)\b',
]


class ResearchSearchPipeline:
    """
    Performs isolated web searches for research queries.
    Uses headless Edge browser (mirrors C++ engine logic).
    """

    # Allowed search domains (mirrors C++ whitelist)
    ALLOWED_DOMAINS = frozenset([
        "www.bing.com",
        "bing.com",
        "duckduckgo.com",
        "www.duckduckgo.com",
        "en.wikipedia.org",
        "wikipedia.org",
        "en.m.wikipedia.org",
    ])

    # Maximum response size
    MAX_RESPONSE_BYTES = 65536
    TIMEOUT_SECONDS = 10
    MAX_SUMMARY_WORDS = 500

    def search(self, query: str) -> ResearchResult:
        """Execute a research search query."""
        timestamp = datetime.now(timezone.utc).isoformat()
        query = query.strip()

        # Block dangerous patterns
        for pattern in BLOCKED_RESEARCH_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return ResearchResult(
                    query=query,
                    status=ResearchStatus.BLOCKED,
                    title="",
                    summary=f"Query blocked: contains forbidden pattern",
                    source="",
                    key_terms=(),
                    word_count=0,
                    elapsed_ms=0,
                    mode=VoiceMode.RESEARCH,
                    timestamp=timestamp,
                )

        import time
        t_start = time.monotonic()

        try:
            # Build search URL
            from urllib.parse import quote_plus
            encoded_query = quote_plus(query)
            search_url = f"https://www.bing.com/search?q={encoded_query}"

            # Launch headless Edge with --dump-dom
            result = subprocess.run(
                [
                    "msedge",
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-extensions",
                    "--disable-plugins",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--disable-translate",
                    "--no-first-run",
                    "--inprivate",
                    "--dump-dom",
                    search_url,
                ],
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT_SECONDS,
            )

            elapsed = (time.monotonic() - t_start) * 1000
            raw_html = result.stdout[:self.MAX_RESPONSE_BYTES]

            if not raw_html:
                return ResearchResult(
                    query=query,
                    status=ResearchStatus.NO_RESULTS,
                    title="",
                    summary="I couldn't find results for that query. Could you rephrase your question?",
                    source="bing.com",
                    key_terms=(),
                    word_count=0,
                    elapsed_ms=elapsed,
                    mode=VoiceMode.CLARIFICATION,
                    timestamp=timestamp,
                )

            # Extract text from HTML (mirrors C++ content_extractor)
            text = self._extract_text(raw_html)

            # Empty extraction fail-safe → route to CLARIFICATION
            if not text or len(text.strip()) < 10:
                return ResearchResult(
                    query=query,
                    status=ResearchStatus.NO_RESULTS,
                    title="",
                    summary="I found the page but couldn't extract useful content. Could you try a different question?",
                    source="bing.com",
                    key_terms=(),
                    word_count=0,
                    elapsed_ms=elapsed,
                    mode=VoiceMode.CLARIFICATION,
                    timestamp=timestamp,
                )

            # Sanitize (mirrors C++ research_sanitizer)
            text = self._sanitize(text)

            # Summarize (mirrors C++ result_summarizer)
            summary, key_terms = self._summarize(text, query)

            return ResearchResult(
                query=query,
                status=ResearchStatus.SUCCESS,
                title=query.title(),
                summary=summary,
                source="bing.com",
                key_terms=tuple(key_terms[:10]),
                word_count=len(summary.split()),
                elapsed_ms=elapsed,
                mode=VoiceMode.RESEARCH,
                timestamp=timestamp,
            )

        except subprocess.TimeoutExpired:
            elapsed = (time.monotonic() - t_start) * 1000
            return ResearchResult(
                query=query,
                status=ResearchStatus.TIMEOUT,
                title="",
                summary="The search took too long. Could you try a simpler question?",
                source="",
                key_terms=(),
                word_count=0,
                elapsed_ms=elapsed,
                mode=VoiceMode.CLARIFICATION,
                timestamp=timestamp,
            )

        except Exception as e:
            elapsed = (time.monotonic() - t_start) * 1000
            logger.error(f"Research search failed: {e}")
            return ResearchResult(
                query=query,
                status=ResearchStatus.ERROR,
                title="",
                summary="I couldn't complete the search. Could you rephrase your question?",
                source="",
                key_terms=(),
                word_count=0,
                elapsed_ms=elapsed,
                mode=VoiceMode.CLARIFICATION,
                timestamp=timestamp,
            )

    # =====================================================================
    # TEXT EXTRACTION (Python mirror of C++ content_extractor)
    # =====================================================================

    def _extract_text(self, raw_html: str) -> str:
        """Extract visible text from HTML, stripping scripts/styles."""
        # Remove script and style blocks
        text = re.sub(r'<script[^>]*>.*?</script>', '', raw_html,
                      flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text,
                      flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<iframe[^>]*>.*?</iframe>', '', text,
                      flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

        # Replace block tags with newlines
        text = re.sub(r'</?(?:p|div|h[1-6]|li|tr|br|hr|blockquote|pre|article'
                      r'|section|header|footer|main)[^>]*>', '\n', text,
                      flags=re.IGNORECASE)

        # Strip remaining tags
        text = re.sub(r'<[^>]+>', ' ', text)

        # Decode HTML entities
        text = html.unescape(text)

        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()[:4096]  # 4KB cap (matches C++)

    # =====================================================================
    # SANITIZER (Python mirror of C++ research_sanitizer)
    # =====================================================================

    def _sanitize(self, text: str) -> str:
        """Strip any remaining dangerous content from extracted text."""
        # Remove javascript: URIs
        text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
        # Remove data: URIs
        text = re.sub(r'data:[^\s]+', '', text, flags=re.IGNORECASE)
        # Remove event handlers
        text = re.sub(r'on\w+\s*=\s*["\'][^"\']*["\']', '', text,
                      flags=re.IGNORECASE)
        # Remove tracking params from any embedded URLs
        text = re.sub(r'[?&](?:utm_\w+|fbclid|gclid|msclkid)=[^\s&]*', '',
                      text)
        return text

    # =====================================================================
    # SUMMARIZER (Python mirror of C++ result_summarizer)
    # =====================================================================

    STOP_WORDS = frozenset([
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "can", "shall", "must",
        "and", "or", "but", "nor", "not", "so", "yet", "for", "of",
        "in", "to", "with", "at", "by", "from", "on", "as", "if",
        "that", "this", "it", "its", "he", "she", "they", "we", "you",
        "their", "his", "her", "our", "my", "your", "who", "which",
        "what", "where", "when", "how", "all", "each", "every", "both",
        "few", "more", "most", "other", "some", "such", "than", "too",
        "very",
    ])

    def _summarize(self, text: str, query: str) -> Tuple[str, List[str]]:
        """Summarize text using keyword scoring. Returns (summary, key_terms)."""
        # Split into sentences
        sentences = re.split(r'[.!?\n]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

        if not sentences:
            return "No relevant information found.", []

        # Extract keywords (TF-IDF style)
        words = re.findall(r'[a-zA-Z]{3,}', text.lower())
        word_freq: Dict[str, int] = {}
        for w in words:
            if w not in self.STOP_WORDS:
                word_freq[w] = word_freq.get(w, 0) + 1

        # Sort by frequency
        sorted_keywords = sorted(word_freq.items(), key=lambda x: -x[1])
        key_terms = [kw for kw, _ in sorted_keywords[:10]]

        # Score sentences
        scored: List[Tuple[float, int, str]] = []
        query_words = set(re.findall(r'[a-zA-Z]{3,}', query.lower()))

        for idx, sent in enumerate(sentences):
            sent_lower = sent.lower()
            score = 0.0

            # Keyword match score
            for kw, freq in sorted_keywords[:20]:
                if kw in sent_lower:
                    score += freq * (1.0 + 0.1 * len(kw))

            # Query word match bonus
            for qw in query_words:
                if qw in sent_lower:
                    score += 5.0

            # Position bonus (first sentences)
            if idx < 3:
                score *= 1.2

            scored.append((score, idx, sent))

        # Select top 3 by score, present in original order
        scored.sort(key=lambda x: -x[0])
        top = scored[:3]
        top.sort(key=lambda x: x[1])  # Re-sort by position

        summary = ". ".join(t[2].strip().rstrip('.') for t in top) + "."

        # Cap at 500 words
        words_list = summary.split()
        if len(words_list) > self.MAX_SUMMARY_WORDS:
            summary = " ".join(words_list[:self.MAX_SUMMARY_WORDS]) + "..."

        return summary, key_terms

    # Guards — research mode cannot do these
    @staticmethod
    def can_access_training() -> bool:
        return False

    @staticmethod
    def can_modify_governance() -> bool:
        return False

    @staticmethod
    def can_execute_commands() -> bool:
        return False

    @staticmethod
    def can_persist_data() -> bool:
        return False
