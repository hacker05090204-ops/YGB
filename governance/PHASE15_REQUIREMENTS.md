# PHASE-15 REQUIREMENTS

**Phase:** Phase-15 - Frontend ↔ Backend Contract Authority  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-25T05:58:00-05:00  

---

## 1. OVERVIEW

Phase-15 defines the contract validation layer for frontend requests. The backend has **ABSOLUTE AUTHORITY** over critical fields. Frontend requests that violate the contract are **DENIED**.

---

## 2. ALLOWED FRONTEND REQUEST FIELDS (EXACT)

### 2.1 Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | str | Unique request identifier |
| `bug_id` | str | Bug being queried |
| `target_id` | str | Target identifier |
| `request_type` | str | Type of request (from allowed list) |
| `timestamp` | str | ISO timestamp |

### 2.2 Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | str | Optional session identifier |
| `user_context` | str | Optional user context |
| `notes` | str | Optional notes |

### 2.3 Allowed Request Types

| Value | Description |
|-------|-------------|
| `STATUS_CHECK` | Check current status |
| `READINESS_CHECK` | Check browser readiness |
| `FULL_EVALUATION` | Full pipeline evaluation |

---

## 3. FORBIDDEN FIELDS (BACKEND-ONLY)

### 3.1 Forbidden Field List

| Field | Reason |
|-------|--------|
| `confidence` | Backend-only: Phase-12 determines |
| `confidence_level` | Backend-only: Phase-12 determines |
| `severity` | Backend-only: Bug analysis determines |
| `bug_severity` | Backend-only: Bug analysis determines |
| `readiness` | Backend-only: Phase-13 determines |
| `readiness_state` | Backend-only: Phase-13 determines |
| `human_presence` | Backend-only: Phase-13 determines |
| `can_proceed` | Backend-only: Phase-13 determines |
| `is_blocked` | Backend-only: Phase-13 determines |
| `evidence_state` | Backend-only: Phase-12 determines |
| `trust_level` | Backend-only: Phase-03 determines |
| `authority` | Backend-only: Governance determines |

### 3.2 Forbidden Field Detection

If ANY forbidden field is present in the request:
- → Request is DENIED
- → Reason: "FORBIDDEN_FIELD_DETECTED"
- → No further processing

---

## 4. REQUIRED VS OPTIONAL FIELD RULES

### 4.1 Required Field Missing

| Condition | Result |
|-----------|--------|
| Missing `request_id` | DENIED |
| Missing `bug_id` | DENIED |
| Missing `target_id` | DENIED |
| Missing `request_type` | DENIED |
| Missing `timestamp` | DENIED |

### 4.2 Optional Field Missing

| Condition | Result |
|-----------|--------|
| Missing `session_id` | ALLOWED (default: None) |
| Missing `user_context` | ALLOWED (default: None) |
| Missing `notes` | ALLOWED (default: None) |

---

## 5. ENUM VALIDATION RULES

### 5.1 Request Type Validation

| Value | Valid |
|-------|-------|
| `STATUS_CHECK` | ✅ YES |
| `READINESS_CHECK` | ✅ YES |
| `FULL_EVALUATION` | ✅ YES |
| Any other value | ❌ NO → DENIED |

### 5.2 Invalid Enum Detection

If request_type is not in the allowed list:
- → Request is DENIED
- → Reason: "INVALID_REQUEST_TYPE"

---

## 6. MISSING FIELD BEHAVIOR

> **RULE:** If ANY required field is missing → DENY.

| Missing Field | Result Code |
|---------------|-------------|
| request_id | "MISSING_REQUEST_ID" |
| bug_id | "MISSING_BUG_ID" |
| target_id | "MISSING_TARGET_ID" |
| request_type | "MISSING_REQUEST_TYPE" |
| timestamp | "MISSING_TIMESTAMP" |

---

## 7. EXTRA FIELD BEHAVIOR

> **RULE:** If ANY unexpected field is present → DENY.

Unexpected fields that are NOT in the allowed list (required or optional) result in:
- → Request is DENIED
- → Reason: "UNEXPECTED_FIELD"

Only the fields listed in Section 2 are allowed.

---

## 8. DATA TYPES REQUIRED

| Type | Kind | Frozen |
|------|------|--------|
| `FrontendRequestField` | Enum | N/A |
| `RequestType` | Enum | N/A |
| `ValidationStatus` | Enum | N/A |
| `FrontendRequest` | Dataclass | ✅ `frozen=True` |
| `ContractValidationResult` | Dataclass | ✅ `frozen=True` |

---

## 9. FUNCTIONAL REQUIREMENTS

### 9.1 Required Functions

| Function | Input | Output |
|----------|-------|--------|
| `validate_required_fields()` | payload | ValidationResult |
| `validate_forbidden_fields()` | payload | ValidationResult |
| `validate_request_type()` | payload | ValidationResult |
| `validate_contract()` | payload | ContractValidationResult |

### 9.2 Function Constraints

All functions MUST be:
- Pure (no side effects)
- Deterministic (same input → same output)
- Deny-by-default (unknown → denied)

---

## 10. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| Frontend cannot set confidence | Forbidden field check |
| Frontend cannot set severity | Forbidden field check |
| Frontend cannot set readiness | Forbidden field check |
| No execution logic | No `exec()`, `eval()` |
| No network access | Pure validation |

---

**END OF REQUIREMENTS**
