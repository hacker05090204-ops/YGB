# PHASE-37 DESIGN

**Phase:** Phase-37 — Native Capability Governor  
**Status:** DESIGN COMPLETE — NO IMPLEMENTATION AUTHORIZED  
**Date:** 2026-01-26T18:55:00-05:00  

---

## 1. CAPABILITY REQUEST LIFECYCLE

### 1.1 Lifecycle Stages

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         CAPABILITY REQUEST LIFECYCLE                          │
└──────────────────────────────────────────────────────────────────────────────┘

  NATIVE ZONE                    INTERFACE ZONE                 GOVERNANCE ZONE
      │                               │                               │
      │ (1) SUBMISSION                │                               │
      │──────────────────────────────▶│                               │
      │   CapabilityRequest           │                               │
      │                               │                               │
      │                               │ (2) VALIDATION                │
      │                               │   • Format check              │
      │                               │   • Field validation          │
      │                               │   • Rate limit check          │
      │                               │                               │
      │                               │ (3) CLASSIFICATION            │
      │                               │   • Lookup capability state   │
      │                               │   • NEVER → immediate DENY    │
      │                               │   • ALLOW → proceed           │
      │                               │   • ESCALATE → route to human │
      │                               │                               │
      │                               │ (4) CONFLICT DETECTION        │
      │                               │   • Check pending requests    │
      │                               │   • Check granted capabilities│
      │                               │   • Conflict → DENY both      │
      │                               │                               │
      │          ┌────────────────────│──────────────────────────────▶│
      │          │                    │                               │ (5) HUMAN
      │          │ If ESCALATE        │                               │    REVIEW
      │          │                    │                               │
      │          │                    │◀──────────────────────────────│
      │          │                    │   Approval / Denial           │
      │          └────────────────────│                               │
      │                               │                               │
      │                               │ (6) DECISION                  │
      │                               │   • ALLOW / DENY / ESCALATE   │
      │◀──────────────────────────────│                               │
      │   CapabilityResponse          │                               │
      │                               │                               │
      │                               │ (7) AUDIT                     │
      │                               │   • Log request               │
      │                               │   • Log decision              │
      │                               │   • Log human response        │
      │                               │                               │
```

### 1.2 Stage Specifications

| Stage | Input | Output | Failure Mode |
|-------|-------|--------|--------------|
| SUBMISSION | Raw request bytes | Parsed request | Malformed → DENY |
| VALIDATION | Parsed request | Valid request | Invalid → DENY |
| CLASSIFICATION | Valid request | Capability state | Unknown → DENY |
| CONFLICT DETECTION | Request + state | Conflict status | Conflict → DENY |
| HUMAN REVIEW | ESCALATE request | Approval/Denial | No response → DENY |
| DECISION | All inputs | Final decision | Any failure → DENY |
| AUDIT | All events | Audit log entry | Log failure → Alert |

---

## 2. CAPABILITY INTENT SCHEMA

### 2.1 CapabilityRequest Dataclass (frozen=True)

```
CapabilityRequest (frozen=True):
  request_id: str              # Format: REQ-[a-fA-F0-9]{16}
  capability: SandboxCapability # From Phase-36
  intent_description: str       # Human-readable (max 256 chars)
  requested_scope: RequestScope # Scope specification
  timestamp: str               # ISO 8601 format
  expiry: str                  # ISO 8601 format
  context_hash: str            # SHA-256 of execution context
  requester_id: str            # Native instance identifier
```

### 2.2 RequestScope Dataclass (frozen=True)

```
RequestScope (frozen=True):
  scope_type: ScopeType        # What kind of scope
  scope_value: str             # Scope specification
  scope_limit: int             # Maximum operations/bytes/etc.
```

### 2.3 CapabilityResponse Dataclass (frozen=True)

```
CapabilityResponse (frozen=True):
  request_id: str              # Echo back request_id
  decision: RequestDecision    # GRANTED / DENIED / PENDING
  reason_code: str             # Machine-readable reason
  reason_description: str      # Human-readable reason
  grant_token: str             # If GRANTED, one-time token
  grant_expiry: str            # When grant expires
  requires_human: bool         # True if ESCALATE
```

### 2.4 CapabilityGrant Dataclass (frozen=True)

```
CapabilityGrant (frozen=True):
  grant_id: str                # Format: GRANT-[a-fA-F0-9]{16}
  request_id: str              # Original request
  capability: SandboxCapability
  scope: RequestScope
  granted_at: str              # Timestamp
  expires_at: str              # Expiry timestamp
  context_hash: str            # Must match at use time
  consumed: bool               # One-time use flag
```

---

## 3. ENUM SPECIFICATIONS (DESIGN ONLY)

### 3.1 RequestDecision Enum

```
RequestDecision (CLOSED ENUM - 3 members):
  GRANTED    # Request approved, grant token issued
  DENIED     # Request rejected
  PENDING    # Awaiting human review
```

### 3.2 ScopeType Enum

```
ScopeType (CLOSED ENUM - 6 members):
  MEMORY_RANGE    # Specific memory addresses
  TIME_WINDOW     # Duration limit
  OPERATION_COUNT # Number of operations
  BYTE_LIMIT      # Data size limit
  SINGLE_USE      # One operation only
  UNBOUNDED       # No limit (requires ESCALATE)
```

### 3.3 DenialReason Enum

```
DenialReason (CLOSED ENUM - 12 members):
  MALFORMED_REQUEST
  UNKNOWN_CAPABILITY
  NEVER_CAPABILITY
  MISSING_FIELD
  INVALID_FIELD
  RATE_LIMITED
  CONFLICT_DETECTED
  CONTEXT_MISMATCH
  EXPIRED_REQUEST
  HUMAN_DENIED
  SCOPE_EXCEEDED
  REPLAY_DETECTED
```

### 3.4 ConflictType Enum

```
ConflictType (CLOSED ENUM - 5 members):
  MUTUAL_EXCLUSION      # Capabilities cannot coexist
  SCOPE_OVERLAP         # Overlapping scope ranges
  INTENT_CONTRADICTION  # Conflicting stated purposes
  TEMPORAL_CONFLICT     # Overlapping time windows
  RESOURCE_CONTENTION   # Same resource requested
```

---

## 4. REQUEST VALIDATION FLOW

### 4.1 Validation Decision Flow

```
Request arrives
      │
      ▼
┌─────────────────┐
│ Parse request   │──FAIL──▶ DENY (MALFORMED_REQUEST)
└───────┬─────────┘
        │ OK
        ▼
┌─────────────────┐
│ request_id      │──INVALID──▶ DENY (INVALID_FIELD)
│ format valid?   │
└───────┬─────────┘
        │ OK
        ▼
┌─────────────────┐
│ capability      │──NO──▶ DENY (UNKNOWN_CAPABILITY)
│ registered?     │
└───────┬─────────┘
        │ YES
        ▼
┌─────────────────┐
│ capability      │──YES──▶ DENY (NEVER_CAPABILITY)
│ state = NEVER?  │
└───────┬─────────┘
        │ NO
        ▼
┌─────────────────┐
│ intent_desc     │──EMPTY──▶ DENY (MISSING_FIELD)
│ non-empty?      │
└───────┬─────────┘
        │ OK
        ▼
┌─────────────────┐
│ scope           │──INVALID──▶ DENY (INVALID_FIELD)
│ valid?          │
└───────┬─────────┘
        │ OK
        ▼
┌─────────────────┐
│ timestamp       │──INVALID──▶ DENY (INVALID_FIELD)
│ valid?          │
└───────┬─────────┘
        │ OK
        ▼
┌─────────────────┐
│ expiry after    │──NO──▶ DENY (INVALID_FIELD)
│ timestamp?      │
└───────┬─────────┘
        │ YES
        ▼
┌─────────────────┐
│ context_hash    │──MISMATCH──▶ DENY (CONTEXT_MISMATCH)
│ matches?        │
└───────┬─────────┘
        │ OK
        ▼
┌─────────────────┐
│ rate limit      │──EXCEEDED──▶ DENY (RATE_LIMITED)
│ OK?             │
└───────┬─────────┘
        │ OK
        ▼
┌─────────────────┐
│ replay          │──YES──▶ DENY (REPLAY_DETECTED)
│ detected?       │
└───────┬─────────┘
        │ NO
        ▼
    VALIDATED
```

### 4.2 Validation Decision Table

| Condition | Result | Reason Code |
|-----------|--------|-------------|
| Parse failure | DENY | MALFORMED_REQUEST |
| Invalid request_id format | DENY | INVALID_FIELD |
| Unknown capability | DENY | UNKNOWN_CAPABILITY |
| Capability state = NEVER | DENY | NEVER_CAPABILITY |
| Empty intent_description | DENY | MISSING_FIELD |
| Invalid scope | DENY | INVALID_FIELD |
| Invalid timestamp | DENY | INVALID_FIELD |
| Expiry before timestamp | DENY | INVALID_FIELD |
| Context hash mismatch | DENY | CONTEXT_MISMATCH |
| Rate limit exceeded | DENY | RATE_LIMITED |
| Replay detected | DENY | REPLAY_DETECTED |
| All checks pass | PROCEED | — |

---

## 5. CONFLICT RESOLUTION RULES

### 5.1 Conflict Detection Matrix

| Capability A | Capability B | Conflicting? |
|--------------|--------------|--------------|
| MEMORY_READ | MEMORY_WRITE | ⚠️ CHECK SCOPE |
| NETWORK | Any | NEVER coexists |
| FILESYSTEM | Any | NEVER coexists |
| PROCESS | Any | NEVER coexists |
| HEAP_ALLOCATE | HEAP_ALLOCATE | ⚠️ CHECK SCOPE |
| INPUT_READ | OUTPUT_WRITE | ✅ ALLOWED |

### 5.2 Conflict Resolution Rules

| Rule | Condition | Resolution |
|------|-----------|------------|
| CR-01 | Two requests for same capability | DENY both |
| CR-02 | Requests for mutually exclusive capabilities | DENY both |
| CR-03 | Overlapping scope ranges | DENY later request |
| CR-04 | Contradictory intents | DENY both |
| CR-05 | Overlapping time windows for same resource | DENY later request |
| CR-06 | NETWORK + any other request | DENY NETWORK |

### 5.3 Conflict Response

| Conflict Detected | Action |
|-------------------|--------|
| YES | DENY both requests |
| YES | Log as ConflictViolation |
| YES | Alert if pattern detected |
| YES | Increase backoff for requester |

---

## 6. RATE/VOLUME GOVERNANCE

### 6.1 Rate Limit Structure

| Limit Category | Structure | Enforcement |
|---------------|-----------|-------------|
| Requests per time window | `max_requests`, `window_seconds` | Hard DENY |
| ESCALATE requests per window | `max_escalate`, `window_seconds` | Hard DENY |
| Requests per capability | `max_per_capability`, `window_seconds` | Hard DENY |
| Consecutive denials | `max_consecutive_denials` | Backoff required |
| Pending requests | `max_pending` | Hard DENY |

### 6.2 Backoff Structure

| Trigger | Backoff Action |
|---------|----------------|
| Rate limit exceeded | Mandatory wait before new request |
| Consecutive denials | Exponential backoff |
| Conflict detected | Fixed backoff per conflict |
| Replay detected | Maximum backoff |

### 6.3 RateLimitState Dataclass (frozen=True)

```
RateLimitState (frozen=True):
  requester_id: str
  window_start: str
  request_count: int
  escalate_count: int
  last_denial: str
  consecutive_denials: int
  backoff_until: str
```

---

## 7. AUDIT REQUIREMENTS

### 7.1 Audit Event Types

```
AuditEventType (CLOSED ENUM - 8 members):
  REQUEST_RECEIVED
  VALIDATION_PASSED
  VALIDATION_FAILED
  HUMAN_ESCALATED
  HUMAN_APPROVED
  HUMAN_DENIED
  GRANT_ISSUED
  GRANT_CONSUMED
```

### 7.2 AuditEntry Dataclass (frozen=True)

```
AuditEntry (frozen=True):
  audit_id: str
  event_type: AuditEventType
  timestamp: str
  request_id: str
  capability: SandboxCapability
  decision: RequestDecision
  reason_code: str
  requester_id: str
  context_hash: str
```

### 7.3 Audit Requirements

| Requirement | Description |
|-------------|-------------|
| Completeness | Every request is logged |
| Immutability | Logs cannot be modified |
| Timeliness | Logged at event time |
| Traceability | Full request chain visible |
| Reviewability | Human-readable format |

---

## 8. INTEGRATION WITH PHASE-36

### 8.1 Capability Mapping

| Phase-37 Request | Phase-36 Boundary |
|------------------|-------------------|
| CapabilityRequest.capability | SandboxCapability |
| RequestDecision.GRANTED | BoundaryDecision.ALLOW |
| RequestDecision.DENIED | BoundaryDecision.DENY |
| RequestDecision.PENDING | BoundaryDecision.ESCALATE |

### 8.2 Boundary Interaction

| Phase-37 Event | Phase-36 Action |
|----------------|-----------------|
| Grant issued | Boundary allows capability |
| Grant consumed | Boundary tracks usage |
| Grant expired | Boundary revokes access |
| Grant missing | Boundary denies access |

### 8.3 Integration Flow

```
Native Zone attempts capability use
           │
           ▼
   ┌───────────────┐
   │ Grant exists? │──NO──▶ DENY
   └───────┬───────┘
           │ YES
           ▼
   ┌───────────────┐
   │ Grant valid?  │──NO──▶ DENY
   │ (not expired) │
   └───────┬───────┘
           │ YES
           ▼
   ┌───────────────┐
   │ Context       │──NO──▶ DENY
   │ matches?      │
   └───────┬───────┘
           │ YES
           ▼
   ┌───────────────┐
   │ Scope check   │──EXCEED──▶ DENY
   │ passed?       │
   └───────┬───────┘
           │ YES
           ▼
       Mark grant consumed
           │
           ▼
   Phase-36 ALLOW
```

---

## 9. INVARIANTS

1. **All requests are logged** — No silent request processing
2. **NEVER capabilities are immediately denied** — No validation required
3. **Grants are one-time use** — Must re-request after consumption
4. **Grants expire** — No permanent authority from single request
5. **Context must match** — Request context = use context
6. **Conflicts deny all parties** — No preference for any request
7. **Rate limits are hard** — No override mechanism
8. **Human approval routes through Phase-13** — No parallel path
9. **Determinism is enforced** — Same request + same state = same result

---

## 10. DESIGN VALIDATION RULES

| Rule | Validation Method |
|------|-------------------|
| All enums are CLOSED | Member count verification |
| All dataclasses are frozen=True | Specification check |
| All validation rules are explicit | Decision table completeness |
| All conflicts are detected | Conflict matrix coverage |
| All rate limits are structured | Structure documentation |
| All audit events are typed | Enum coverage |
| Phase-36 integration is complete | Mapping verification |

---

**END OF DESIGN**
