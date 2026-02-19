"""
language_detector.py — Multi-Language Detection

Supports:
  - English (en)
  - Hindi (hi)
  - Marathi (mr)

Auto-detects language from text input for routing.
NO auto-hunt from voice. Voice cannot trigger submission.
"""

import re
from typing import Optional

# Unicode ranges for Devanagari script
DEVANAGARI_RANGE = re.compile(r'[\u0900-\u097F]')

# Common Marathi-specific patterns (distinct from Hindi)
MARATHI_MARKERS = {
    "आहे", "नाही", "काय", "कसं", "कसे", "मला", "तुम्ही",
    "करा", "करतो", "करते", "होतो", "होते", "आम्ही"
}

# Common Hindi patterns
HINDI_MARKERS = {
    "है", "हैं", "नहीं", "क्या", "कैसे", "मुझे", "आप",
    "करो", "करता", "करती", "होता", "होती", "हम"
}


class LanguageDetector:
    """Detects language from text input."""

    SUPPORTED = {"en", "hi", "mr"}
    ALLOW_AUTO_HUNT = False
    ALLOW_VOICE_SUBMIT = False

    def detect(self, text: str) -> dict:
        """
        Detect language from input text.

        Returns:
            dict with 'language', 'confidence', 'script'
        """
        if not text or not text.strip():
            return {"language": "en", "confidence": 0.0, "script": "latin"}

        text_clean = text.strip()

        # Count Devanagari characters
        devanagari_chars = len(DEVANAGARI_RANGE.findall(text_clean))
        total_alpha = sum(1 for c in text_clean if c.isalpha())

        if total_alpha == 0:
            return {"language": "en", "confidence": 0.5, "script": "latin"}

        devanagari_ratio = devanagari_chars / total_alpha

        # If primarily Devanagari script
        if devanagari_ratio > 0.3:
            # Distinguish Hindi vs Marathi
            words = set(text_clean.split())
            marathi_score = len(words & MARATHI_MARKERS)
            hindi_score = len(words & HINDI_MARKERS)

            if marathi_score > hindi_score:
                confidence = min(0.95, 0.6 + marathi_score * 0.1)
                return {"language": "mr", "confidence": confidence,
                        "script": "devanagari"}
            else:
                confidence = min(0.95, 0.6 + hindi_score * 0.1)
                return {"language": "hi", "confidence": confidence,
                        "script": "devanagari"}

        # Default: English
        return {"language": "en", "confidence": 0.9, "script": "latin"}

    def is_supported(self, lang: str) -> bool:
        return lang in self.SUPPORTED
