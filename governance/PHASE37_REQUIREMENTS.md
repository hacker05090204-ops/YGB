# PHASE-37 REQUIREMENTS

**Phase:** Phase-37 — Native Capability Governor  
**Status:** REQUIREMENTS DEFINED — DESIGN ONLY  
**Date:** 2026-01-26T18:55:00-05:00  

---

## 1. OVERVIEW

Phase-37 defines the **governance model for capability requests** from native code. This specifies how requests are structured, validated, decided, rate-limited, and audited BEFORE any native code exists.

> [!WARNING]
> **DEFAULT BEHAVIOR: DENY**
>
> Any capability request not explicitly permitted is DENIED by default.
> Unknown request formats are DENIED.
> Malformed requests are DENIED.
> Rate-exceeded requests are DENIED.

---

## 2. FUNCTIONAL REQUIREMENTS

### FR-01: Capability Request Lifecycle

The design MUST define a complete request lifecycle:

| Stage | Description |
|-------|-------------|
| **SUBMISSION** | Request arrives from native zone |
| **VALIDATION** | Request format and content checked |
| **CLASSIFICATION** | Request mapped to capability state |
| **DECISION** | ALLOW / DENY / ESCALATE determined |
| **EXECUTION** | If ALLOW, capability granted |
| **AUDIT** | Request and outcome logged |

### FR-02: Capability Intent Schema

The design MUST define what a request MUST contain:

| Field | Required | Purpose |
|-------|----------|---------|
| request_id | ✅ YES | Unique identifier |
| capability | ✅ YES | Which SandboxCapability |
| intent_description | ✅ YES | Human-readable purpose |
| requested_scope | ✅ YES | Limits on the request |
| timestamp | ✅ YES | When request was made |
| context_hash | ✅ YES | Execution context |
| expiry | ✅ YES | When approval expires |

### FR-03: Request Validation Rules

The design MUST specify validation rules:

| Rule | Action on Failure |
|------|-------------------|
| request_id format valid | DENY |
| capability is registered | DENY |
| intent_description non-empty | DENY |
| timestamp is valid | DENY |
| expiry is after timestamp | DENY |
| context_hash matches | DENY |
| capability is not NEVER | DENY |

### FR-04: Conflict Detection Rules

The design MUST detect conflicting requests:

| Conflict Type | Resolution |
|---------------|------------|
| Same capability, different scope | DENY both |
| Mutually exclusive capabilities | DENY both |
| Overlapping time windows | DENY later |
| Contradictory intents | DENY both |

### FR-05: Rate Limiting Structure

The design MUST define rate limit structure:

| Rate Limit Category | Enforcement |
|--------------------|-------------|
| Requests per time period | Hard limit |
| ESCALATE requests per period | Hard limit (lower) |
| Requests per capability | Hard limit |
| Consecutive denied requests | Backoff required |

### FR-06: Audit Requirements

The design MUST define audit logging:

| Audit Event | What Is Logged |
|-------------|----------------|
| Request received | Full request content |
| Validation result | Pass/fail + reasons |
| Decision made | ALLOW/DENY/ESCALATE + reasons |
| Human response | Approval/denial + timestamp |
| Execution | Success/failure |
| Violation detected | Full context |

### FR-07: Integration with Phase-36

The design MUST specify Phase-36 integration:

| Integration Point | Specification |
|------------------|---------------|
| Capability lookup | Use Phase-36 SandboxCapability |
| State lookup | Use Phase-36 CapabilityState |
| Decision output | Use Phase-36 BoundaryDecision |
| Violation reporting | Use Phase-36 ViolationType |

---

## 3. NON-FUNCTIONAL REQUIREMENTS

### NFR-01: Zero Trust Assumption

The design MUST assume:

| Assumption |
|------------|
| All requests originate from hostile native code |
| All request contents may be crafted to bypass validation |
| All request timing may be adversarial |
| Human reviewers may be fatigued |

### NFR-02: Deny-by-Default

The design MUST enforce:

| Condition | Result |
|-----------|--------|
| Unknown request format → DENY |
| Unknown capability → DENY |
| Missing field → DENY |
| Invalid field → DENY |
| Rate limit exceeded → DENY |
| Conflict detected → DENY |
| Default → DENY |

### NFR-03: Determinism

The design MUST ensure:

| Requirement |
|-------------|
| Same request + same state → same outcome |
| No randomness in decisions |
| No time-of-day dependencies |
| Order-independent validation |

### NFR-04: Auditability

The design MUST ensure:

| Requirement |
|-------------|
| Every request is logged |
| Every decision is logged with reasons |
| Every human action is logged |
| Logs are immutable |
| Logs contain timestamp |

### NFR-05: Human Fatigue Protection

The design MUST include:

| Protection |
|------------|
| Rate limits prevent flooding |
| Mandatory cooling periods |
| Auto-deny after threshold |
| Batch size limits |
| Human can pause all requests |

---

## 4. EXPLICIT PROHIBITIONS

### PR-01: Forbidden in Phase-37 Design

| Item | Status |
|------|--------|
| Python code | ❌ FORBIDDEN |
| C/C++ code | ❌ FORBIDDEN |
| Compilation instructions | ❌ FORBIDDEN |
| Execution flow | ❌ FORBIDDEN |
| Actual rate limit numbers | ❌ FORBIDDEN (policy) |

### PR-02: Requests MUST NOT

| Prohibition |
|-------------|
| Self-approve |
| Approve other requests |
| Bypass Phase-36 boundary |
| Bypass Phase-13 human gate |
| Override NEVER capabilities |
| Persist beyond expiry |
| Be reused after consumption |

---

## 5. INTEGRATION REQUIREMENTS

### IR-01: Phase-36 Integration

| Requirement | Specification |
|-------------|---------------|
| Capability enum | Use SandboxCapability |
| Capability state | Use CapabilityState |
| Decision enum | Use BoundaryDecision |
| Violation enum | Extend ViolationType |

### IR-02: Phase-13 Integration

| Requirement | Specification |
|-------------|---------------|
| ESCALATE routing | Route to Phase-13 human gate |
| Human presence | Respect HumanPresence states |
| Confirmation | Require human_confirmed |
| Blocking | Honor BLOCKING state |

### IR-03: Phase-35 Integration

| Requirement | Specification |
|-------------|---------------|
| Interface validation | Use Phase-35 validators |
| Decision vocabulary | Consistent with InterfaceDecision |
| Executor classification | Consistent with ExecutorClass |

---

## 6. BOUNDARY PRESERVATION REQUIREMENTS

### BP-01: No Earlier Phase Modification

| Frozen Phase | Status |
|--------------|--------|
| Phase-01 through Phase-36 | ❌ NO MODIFICATION PERMITTED |

### BP-02: No Authority Leakage

| Requirement |
|-------------|
| Requests cannot grant request-approval authority |
| Approved requests do not bypass Phase-36 validation |
| No request can modify Phase-37 rules |

---

## 7. VERIFICATION REQUIREMENTS

### VR-01: Design Testability

All design elements MUST be testable via:

| Method |
|--------|
| Governance document review |
| Decision table completeness check |
| Conflict rule enumeration |
| Rate limit structure validation |

### VR-02: No Code Required

Verification MUST NOT require:

| Not Required |
|--------------|
| Compilation of any code |
| Execution of any binary |
| Runtime testing |

### VR-03: 100% Coverage Required

All design elements MUST have:

| Coverage |
|----------|
| Documented test strategy |
| Explicit acceptance criteria |
| Failure condition enumeration |

---

**END OF REQUIREMENTS**
