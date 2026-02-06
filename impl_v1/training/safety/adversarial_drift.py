"""
Adversarial Drift Test
=======================

Generate synthetic adversarial payloads:
- Obfuscated parameters
- Unicode confusion
- Nested JSON
- Header manipulation

Test model robustness weekly.
Auto-mode disabled if robustness < 85%.
"""

from dataclasses import dataclass
from typing import List, Tuple
from datetime import datetime
import random
import string


# =============================================================================
# ADVERSARIAL PAYLOAD TYPES
# =============================================================================

@dataclass
class AdversarialPayload:
    """An adversarial test payload."""
    id: str
    payload_type: str
    content: str
    expected_detection: bool


# =============================================================================
# PAYLOAD GENERATORS
# =============================================================================

class AdversarialPayloadGenerator:
    """Generate adversarial test payloads."""
    
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
    
    def generate_obfuscated(self, count: int = 50) -> List[AdversarialPayload]:
        """Generate obfuscated parameter payloads."""
        payloads = []
        
        # SQL injection variants
        sqli_bases = [
            "' OR 1=1--",
            "'; DROP TABLE users--",
            "' UNION SELECT * FROM users--",
        ]
        
        for i in range(count):
            base = sqli_bases[i % len(sqli_bases)]
            
            # Obfuscation techniques
            obfuscated = self._apply_obfuscation(base)
            
            payloads.append(AdversarialPayload(
                id=f"OBFUSC_{i:03d}",
                payload_type="obfuscated_sqli",
                content=obfuscated,
                expected_detection=True,
            ))
        
        return payloads
    
    def _apply_obfuscation(self, payload: str) -> str:
        """Apply random obfuscation."""
        techniques = [
            lambda s: s.replace(" ", "/**/"),  # Comment injection
            lambda s: s.replace("'", "%27"),   # URL encoding
            lambda s: "".join(c.upper() if self.rng.random() > 0.5 else c for c in s),  # Case mixing
            lambda s: s.replace("OR", "O/**/R"),  # Keyword splitting
        ]
        
        technique = self.rng.choice(techniques)
        return technique(payload)
    
    def generate_unicode_confusion(self, count: int = 50) -> List[AdversarialPayload]:
        """Generate unicode confusion payloads."""
        payloads = []
        
        confusables = [
            ("a", "а"),  # Cyrillic
            ("e", "е"),
            ("o", "о"),
            ("c", "с"),
        ]
        
        for i in range(count):
            base = "script alert xss"
            
            for orig, conf in confusables:
                if self.rng.random() > 0.5:
                    base = base.replace(orig, conf)
            
            payloads.append(AdversarialPayload(
                id=f"UNICODE_{i:03d}",
                payload_type="unicode_confusion",
                content=f"<{base}>",
                expected_detection=True,
            ))
        
        return payloads
    
    def generate_nested_json(self, count: int = 50) -> List[AdversarialPayload]:
        """Generate nested JSON payloads."""
        payloads = []
        
        for i in range(count):
            depth = self.rng.randint(3, 10)
            
            nested = '{"injection": "DROP TABLE--"}'
            for _ in range(depth):
                nested = '{"nested": ' + nested + '}'
            
            payloads.append(AdversarialPayload(
                id=f"NESTED_{i:03d}",
                payload_type="nested_json",
                content=nested,
                expected_detection=True,
            ))
        
        return payloads
    
    def generate_header_manipulation(self, count: int = 50) -> List[AdversarialPayload]:
        """Generate header manipulation payloads."""
        payloads = []
        
        header_attacks = [
            "X-Forwarded-For: 127.0.0.1\r\nX-Injection: evil",
            "Host: attacker.com\r\n",
            "Content-Type: application/json\r\n\r\n{\"evil\": true}",
        ]
        
        for i in range(count):
            base = header_attacks[i % len(header_attacks)]
            
            payloads.append(AdversarialPayload(
                id=f"HEADER_{i:03d}",
                payload_type="header_manipulation",
                content=base,
                expected_detection=True,
            ))
        
        return payloads
    
    def generate_all(self, per_type: int = 50) -> List[AdversarialPayload]:
        """Generate all adversarial payload types."""
        all_payloads = []
        all_payloads.extend(self.generate_obfuscated(per_type))
        all_payloads.extend(self.generate_unicode_confusion(per_type))
        all_payloads.extend(self.generate_nested_json(per_type))
        all_payloads.extend(self.generate_header_manipulation(per_type))
        return all_payloads


# =============================================================================
# ADVERSARIAL DRIFT TESTER
# =============================================================================

class AdversarialDriftTester:
    """Test model robustness against adversarial payloads."""
    
    ROBUSTNESS_THRESHOLD = 0.85  # 85%
    
    def __init__(self):
        self.generator = AdversarialPayloadGenerator()
        self.last_test_results = None
    
    def run_robustness_test(self, scanner_func) -> Tuple[float, dict]:
        """
        Run robustness test against adversarial payloads.
        
        Args:
            scanner_func: Function that takes payload string and returns (detected: bool, confidence: float)
        
        Returns:
            Tuple of (robustness_score, detailed_results)
        """
        payloads = self.generator.generate_all(per_type=50)
        
        results = {
            "total": len(payloads),
            "detected": 0,
            "missed": 0,
            "by_type": {},
        }
        
        for payload in payloads:
            detected, confidence = scanner_func(payload.content)
            
            if detected == payload.expected_detection:
                results["detected"] += 1
            else:
                results["missed"] += 1
            
            ptype = payload.payload_type
            if ptype not in results["by_type"]:
                results["by_type"][ptype] = {"detected": 0, "missed": 0}
            
            if detected == payload.expected_detection:
                results["by_type"][ptype]["detected"] += 1
            else:
                results["by_type"][ptype]["missed"] += 1
        
        robustness = results["detected"] / results["total"]
        results["robustness_score"] = round(robustness, 4)
        results["threshold_met"] = robustness >= self.ROBUSTNESS_THRESHOLD
        
        self.last_test_results = results
        
        return robustness, results
    
    def should_disable_auto_mode(self) -> Tuple[bool, str]:
        """Check if auto-mode should be disabled."""
        if self.last_test_results is None:
            return False, "No test results"
        
        if not self.last_test_results["threshold_met"]:
            return True, f"Robustness {self.last_test_results['robustness_score']:.2%} < 85%"
        
        return False, "Robustness threshold met"
