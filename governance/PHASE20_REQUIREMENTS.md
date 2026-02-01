# PHASE-20 REQUIREMENTS

**Phase:** Phase-20 - HUMANOID HUNTER Executor Adapter & Safety Harness  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-25T15:30:00-05:00  

---

## 1. EXECUTOR COMMAND TYPES

| Command | Description |
|---------|-------------|
| NAVIGATE | Navigate to URL |
| CLICK | Click element |
| READ | Read element text |
| SCROLL | Scroll page |
| SCREENSHOT | Take screenshot |
| EXTRACT | Extract data |
| SHUTDOWN | Shutdown executor |

---

## 2. EXECUTOR RESPONSE TYPES

| Response | Description |
|----------|-------------|
| SUCCESS | Action succeeded |
| FAILURE | Action failed |
| TIMEOUT | Action timed out |
| ERROR | Executor error |
| REFUSED | Action refused |

---

## 3. EXECUTOR STATUS VALUES

| Status | Description |
|--------|-------------|
| READY | Executor ready |
| BUSY | Executor busy |
| OFFLINE | Executor offline |
| ERROR | Executor error |

---

## 4. INSTRUCTION ENVELOPE

```python
@dataclass(frozen=True)
class ExecutorInstructionEnvelope:
    instruction_id: str
    execution_id: str
    command_type: ExecutorCommandType
    target_url: str
    target_selector: str
    timestamp: str
    timeout_ms: int
```

---

## 5. RESPONSE ENVELOPE

```python
@dataclass(frozen=True)
class ExecutorResponseEnvelope:
    instruction_id: str
    response_type: ExecutorResponseType
    evidence_hash: str
    error_message: str
    timestamp: str
```

---

## 6. SAFETY RULES

| Condition | Result |
|-----------|--------|
| SUCCESS without evidence_hash | ❌ DENIED |
| Missing instruction_id | ❌ DENIED |
| instruction_id mismatch | ❌ DENIED |
| Unknown response_type | ❌ DENIED |
| Executor claims authority | ❌ DENIED |

---

## 7. FUNCTION REQUIREMENTS

| Function | Input | Output |
|----------|-------|--------|
| `build_executor_instruction()` | request data | ExecutorInstructionEnvelope |
| `validate_executor_response()` | envelope | ExecutionSafetyResult |
| `enforce_executor_safety()` | instruction, response | bool |

---

## 8. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| No subprocess | No subprocess module |
| No os.system | No os module |
| No browser | No playwright/selenium |
| No execution | Interface only |
| Immutable | frozen=True |

---

**END OF REQUIREMENTS**
