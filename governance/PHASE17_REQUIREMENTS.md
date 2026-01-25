# PHASE-17 REQUIREMENTS

**Phase:** Phase-17 - Browser Execution Interface Contract  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-25T07:05:00-05:00  

---

## 1. EXECUTION REQUEST REQUIREMENTS

### 1.1 MUST Contain (Required)

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | str | Unique request ID |
| `bug_id` | str | Bug identifier |
| `target_id` | str | Target identifier |
| `action_type` | str | Action to perform |
| `timestamp` | str | ISO timestamp |
| `execution_permission` | str | ALLOWED (from Phase-16) |

### 1.2 MAY Contain (Optional)

| Field | Type | Description |
|-------|------|-------------|
| `parameters` | dict | Action-specific parameters |
| `timeout_seconds` | int | Execution timeout |
| `session_id` | str | Session identifier |

### 1.3 FORBIDDEN (Never Allowed)

| Field | Reason |
|-------|--------|
| `trust_level` | Backend determines |
| `confidence` | Backend determines |
| `severity` | Backend determines |
| `override` | No override allowed |
| `bypass` | No bypass allowed |

---

## 2. EXECUTION RESPONSE REQUIREMENTS

### 2.1 MUST Contain (Required)

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | str | Matching request ID |
| `status` | str | SUCCESS, FAILURE, TIMEOUT |
| `evidence_hash` | str | Hash of evidence (if success) |
| `timestamp` | str | Response timestamp |

### 2.2 MAY Contain (Optional)

| Field | Type | Description |
|-------|------|-------------|
| `error_code` | str | Error code if failure |
| `error_message` | str | Error message |
| `execution_time_ms` | int | Execution duration |

### 2.3 FORBIDDEN (Never Trusted)

| Field | Reason |
|-------|--------|
| `approved` | Executor cannot approve |
| `validated` | Executor cannot validate |
| `trusted` | Executor cannot set trust |

---

## 3. EXECUTOR OBLIGATIONS

### 3.1 Executor MUST

| Obligation | Enforcement |
|------------|-------------|
| Return matching request_id | VERIFIED by backend |
| Provide evidence_hash on SUCCESS | VERIFIED by backend |
| Not claim SUCCESS without proof | DENIED if missing |
| Complete within timeout | TIMEOUT if exceeded |

### 3.2 Executor MUST NOT

| Violation | Result |
|-----------|--------|
| Claim SUCCESS without evidence_hash | DENIED |
| Claim trust/approval | DENIED |
| Include forbidden fields | DENIED |
| Modify request_id | DENIED |

---

## 4. DENY-BY-DEFAULT RULES

| Condition | Result |
|-----------|--------|
| Missing required field in request | DENIED |
| Missing required field in response | DENIED |
| Extra forbidden field | DENIED |
| Invalid action_type | DENIED |
| Invalid status value | DENIED |
| Mismatched request_id | DENIED |
| SUCCESS without evidence_hash | DENIED |

---

## 5. DATA TYPES REQUIRED

| Type | Kind | Frozen |
|------|------|--------|
| `ActionType` | Enum | N/A |
| `ResponseStatus` | Enum | N/A |
| `ExecutionRequest` | Dataclass | ✅ `frozen=True` |
| `ExecutionResponse` | Dataclass | ✅ `frozen=True` |
| `ExecutionContract` | Dataclass | ✅ `frozen=True` |
| `ContractValidationResult` | Dataclass | ✅ `frozen=True` |

---

## 6. FUNCTIONAL REQUIREMENTS

### 6.1 Required Functions

| Function | Purpose |
|----------|---------|
| `validate_execution_request()` | Validate outgoing request |
| `validate_execution_response()` | Validate incoming response |
| `verify_request_id_match()` | Verify request_id matches |
| `verify_success_has_evidence()` | Verify SUCCESS has proof |

### 6.2 Function Constraints

All functions MUST be:
- Pure (no side effects)
- Deterministic
- Deny-by-default

---

**END OF REQUIREMENTS**
