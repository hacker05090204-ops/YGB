# PHASE-19 REQUIREMENTS

**Phase:** Phase-19 - Browser Capability Governance & Action Authorization  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-25T15:05:00-05:00  

---

## 1. BROWSER ACTION TYPES

### 1.1 Action Types (CLOSED Enum)

| Action | Description | Default Risk |
|--------|-------------|--------------|
| NAVIGATE | Navigate to URL | MEDIUM |
| CLICK | Click element | LOW |
| READ | Read text content | LOW |
| SCROLL | Scroll page | LOW |
| EXTRACT_TEXT | Extract text from element | LOW |
| SCREENSHOT | Capture screenshot | LOW |
| FILL_INPUT | Fill input field | MEDIUM |
| SUBMIT_FORM | Submit form | HIGH |
| FILE_UPLOAD | Upload file | FORBIDDEN |
| SCRIPT_EXECUTE | Execute JavaScript | FORBIDDEN |

---

## 2. ACTION RISK LEVELS

| Level | Description | Policy |
|-------|-------------|--------|
| LOW | Safe read operations | May auto-allow |
| MEDIUM | State-changing but limited | Validate context |
| HIGH | Significant state change | HUMAN_REQUIRED |
| FORBIDDEN | Never allowed | Always DENIED |

---

## 3. CAPABILITY DECISION TABLE

| Action | Risk | Ledger State | Result |
|--------|------|--------------|--------|
| Any | FORBIDDEN | Any | ❌ DENIED |
| Any | Any | COMPLETED | ❌ DENIED |
| Any | Any | ESCALATED | ❌ HUMAN_REQUIRED |
| Any | HIGH | ATTEMPTED | ⚠️ HUMAN_REQUIRED |
| Any | MEDIUM | ATTEMPTED | ✅ ALLOWED (with checks) |
| Any | LOW | ATTEMPTED | ✅ ALLOWED |
| Unknown | Any | Any | ❌ DENIED |

---

## 4. POLICY DATACLASS

```python
@dataclass(frozen=True)
class BrowserCapabilityPolicy:
    policy_id: str
    allowed_actions: frozenset  # Set of BrowserActionType
    risk_overrides: tuple  # Custom risk levels
    require_evidence: bool
    max_actions_per_execution: int
```

---

## 5. FUNCTION REQUIREMENTS

| Function | Input | Output |
|----------|-------|--------|
| `classify_action_risk()` | action_type | ActionRiskLevel |
| `is_action_allowed()` | action, policy | bool |
| `decide_capability()` | context | CapabilityDecisionResult |
| `validate_action_against_policy()` | action, policy, state | bool |

---

## 6. DENY-BY-DEFAULT RULES

| Condition | Result |
|-----------|--------|
| Unknown action type | ❌ DENIED |
| Missing policy | ❌ DENIED |
| Action not in allowed_actions | ❌ DENIED |
| FORBIDDEN risk level | ❌ DENIED |
| Execution finalized | ❌ DENIED |
| HIGH risk + no human | ⚠️ HUMAN_REQUIRED |

---

## 7. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| No subprocess | No subprocess module |
| No os.system | No os module |
| No browser | No playwright/selenium |
| No execution | Policy only |
| Immutable | frozen=True |

---

**END OF REQUIREMENTS**
