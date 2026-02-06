"""
Evolution Test Harness
=======================

Simulate future threats:
- New vulnerability patterns
- API structure shifts
- Randomized header formats
- Future payload mutation

Quarterly forced adversarial update test.
"""

from dataclasses import dataclass
from typing import List, Tuple
from datetime import datetime
import random


# =============================================================================
# EVOLUTION SCENARIOS
# =============================================================================

@dataclass
class EvolutionScenario:
    """An evolution test scenario."""
    scenario_id: str
    category: str
    description: str
    payloads: List[str]
    expected_detection_rate: float


# =============================================================================
# EVOLUTION GENERATOR
# =============================================================================

class EvolutionTestGenerator:
    """Generate evolution test scenarios."""
    
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
    
    def generate_new_vuln_patterns(self, count: int = 50) -> EvolutionScenario:
        """Generate new vulnerability patterns."""
        patterns = [
            "prototype_pollution_" + str(i) for i in range(count // 4)
        ] + [
            "graphql_injection_" + str(i) for i in range(count // 4)
        ] + [
            "jwt_confusion_" + str(i) for i in range(count // 4)
        ] + [
            "cache_poisoning_" + str(i) for i in range(count // 4)
        ]
        
        return EvolutionScenario(
            scenario_id="EVOL_NEW_VULN",
            category="new_vulnerability_patterns",
            description="Emerging vulnerability classes",
            payloads=patterns,
            expected_detection_rate=0.70,  # Lower for novel patterns
        )
    
    def generate_api_shifts(self, count: int = 50) -> EvolutionScenario:
        """Generate API structure shifts."""
        patterns = []
        
        for i in range(count):
            # GraphQL-like structures
            patterns.append(f'{{"query": "mutation {{ inject_{i} }}"}}')
            # gRPC-like
            patterns.append(f"grpc://service/inject_{i}")
        
        return EvolutionScenario(
            scenario_id="EVOL_API_SHIFT",
            category="api_structure_shifts",
            description="New API paradigms",
            payloads=patterns[:count],
            expected_detection_rate=0.75,
        )
    
    def generate_random_headers(self, count: int = 50) -> EvolutionScenario:
        """Generate randomized header formats."""
        patterns = []
        
        header_names = ["X-Custom-Auth", "X-Forward-Token", "X-Internal-Api"]
        
        for i in range(count):
            header = self.rng.choice(header_names)
            value = f"inject_{self.rng.randint(1000, 9999)}"
            patterns.append(f"{header}: {value}\r\n")
        
        return EvolutionScenario(
            scenario_id="EVOL_HEADERS",
            category="randomized_headers",
            description="Novel header injection patterns",
            payloads=patterns,
            expected_detection_rate=0.80,
        )
    
    def generate_payload_mutations(self, count: int = 50) -> EvolutionScenario:
        """Generate mutated payloads."""
        base_payloads = [
            "'; DROP TABLE--",
            "<script>alert(1)</script>",
            "{{7*7}}",
            "${jndi:ldap://evil}",
        ]
        
        mutations = []
        
        for i in range(count):
            base = self.rng.choice(base_payloads)
            
            # Apply random mutation
            mutation_type = self.rng.choice(["encode", "pad", "split", "case"])
            
            if mutation_type == "encode":
                mutated = base.replace("<", "%3C").replace(">", "%3E")
            elif mutation_type == "pad":
                mutated = " " * self.rng.randint(1, 5) + base + " " * self.rng.randint(1, 5)
            elif mutation_type == "split":
                mid = len(base) // 2
                mutated = base[:mid] + "/**/" + base[mid:]
            else:
                mutated = "".join(
                    c.upper() if self.rng.random() > 0.5 else c.lower()
                    for c in base
                )
            
            mutations.append(mutated)
        
        return EvolutionScenario(
            scenario_id="EVOL_MUTATION",
            category="payload_mutations",
            description="Mutated known payloads",
            payloads=mutations,
            expected_detection_rate=0.85,
        )
    
    def generate_all_scenarios(self) -> List[EvolutionScenario]:
        """Generate all evolution scenarios."""
        return [
            self.generate_new_vuln_patterns(),
            self.generate_api_shifts(),
            self.generate_random_headers(),
            self.generate_payload_mutations(),
        ]


# =============================================================================
# EVOLUTION TESTER
# =============================================================================

class EvolutionTestHarness:
    """Run evolution tests against model."""
    
    QUARTERLY_DAYS = 90
    
    def __init__(self):
        self.generator = EvolutionTestGenerator()
        self.last_test_date: datetime = None
        self.last_results: dict = None
    
    def is_test_due(self) -> Tuple[bool, str]:
        """Check if quarterly test is due."""
        if self.last_test_date is None:
            return True, "No previous test recorded"
        
        days_since = (datetime.now() - self.last_test_date).days
        
        if days_since >= self.QUARTERLY_DAYS:
            return True, f"Test due: {days_since} days since last test"
        
        return False, f"Next test in {self.QUARTERLY_DAYS - days_since} days"
    
    def run_evolution_test(self, scanner_func) -> dict:
        """Run full evolution test suite."""
        scenarios = self.generator.generate_all_scenarios()
        results = {}
        
        for scenario in scenarios:
            detected = 0
            
            for payload in scenario.payloads:
                try:
                    is_detected, confidence = scanner_func(payload)
                    if is_detected:
                        detected += 1
                except Exception:
                    pass
            
            detection_rate = detected / len(scenario.payloads) if scenario.payloads else 0
            
            results[scenario.category] = {
                "detection_rate": round(detection_rate, 4),
                "expected": scenario.expected_detection_rate,
                "passed": detection_rate >= scenario.expected_detection_rate * 0.9,
                "detected": detected,
                "total": len(scenario.payloads),
            }
        
        self.last_test_date = datetime.now()
        self.last_results = results
        
        return results
    
    def all_tests_passed(self) -> Tuple[bool, List[str]]:
        """Check if all evolution tests passed."""
        if self.last_results is None:
            return False, ["No test results"]
        
        failed = [
            cat for cat, result in self.last_results.items()
            if not result["passed"]
        ]
        
        return len(failed) == 0, failed
