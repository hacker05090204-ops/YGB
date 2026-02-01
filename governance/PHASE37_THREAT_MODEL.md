# PHASE-37 THREAT MODEL

**Phase:** Phase-37 — Native Capability Governor  
**Status:** THREAT MODEL COMPLETE — DESIGN ONLY  
**Date:** 2026-01-26T18:55:00-05:00  

---

## 1. EXECUTIVE SUMMARY

This document enumerates threats, attack surfaces, and abuse cases for the capability request system defined in Phase-37. This is a **DESIGN-ONLY THREAT MODEL**.

> [!CAUTION]
> **ASSUMPTION: ALL CAPABILITY REQUESTS ARE HOSTILE**
>
> This threat model assumes the worst case: all requests originate from adversarial native code attempting to bypass governance, exhaust human reviewers, or exploit the request system itself.

---

## 2. THREAT ACTORS

### 2.1 Actor Categories

| Actor | Description | Capability |
|-------|-------------|------------|
| **HOSTILE_NATIVE** | Malicious native code making requests | Full request generation |
| **EXHAUSTION_ATTACKER** | Attacker aiming to tire human reviewers | High volume requests |
| **CONFUSION_ATTACKER** | Attacker crafting ambiguous requests | Deceptive request content |
| **TIMING_ATTACKER** | Attacker exploiting timing windows | Precise request timing |
| **CONFLICT_ATTACKER** | Attacker exploiting conflict handling | Conflicting request pairs |
| **REPLAY_ATTACKER** | Attacker reusing old approvals | Captured request tokens |

### 2.2 Actor Threat Matrix

| Actor | Goal | Method | Severity |
|-------|------|--------|----------|
| HOSTILE_NATIVE | Gain forbidden capability | Craft requests to bypass validation | CRITICAL |
| EXHAUSTION_ATTACKER | Tire human into auto-approve | Flood with ESCALATE requests | HIGH |
| CONFUSION_ATTACKER | Trick human into wrong approval | Misleading intent descriptions | HIGH |
| TIMING_ATTACKER | Exploit approval windows | Request during vulnerable periods | MEDIUM |
| CONFLICT_ATTACKER | Create undefined states | Submit mutually exclusive requests | HIGH |
| REPLAY_ATTACKER | Reuse expired approvals | Capture and replay tokens | HIGH |

---

## 3. ATTACK SURFACES

### 3.1 Request Content Attack Surface

| Attack Vector | Description | Exploitability |
|---------------|-------------|----------------|
| **Malformed request_id** | Invalid ID format | LOW (validation catches) |
| **Unknown capability** | Request unregistered capability | LOW (validation catches) |
| **Empty intent** | No description of purpose | LOW (validation catches) |
| **Misleading intent** | Description hides true purpose | HIGH |
| **Scope inflation** | Request broader than needed | MEDIUM |
| **Invalid timestamp** | Future or past timestamp | LOW (validation catches) |
| **Excessive expiry** | Request never-expiring approval | MEDIUM |

### 3.2 Rate/Volume Attack Surface

| Attack Vector | Description | Exploitability |
|---------------|-------------|----------------|
| **Request flooding** | Submit many requests rapidly | MEDIUM (rate limits apply) |
| **ESCALATE flooding** | Submit many ESCALATE requests | HIGH (consumes human attention) |
| **Batch abuse** | Submit max batch size repeatedly | MEDIUM |
| **Capability cycling** | Request same capability repeatedly | MEDIUM |
| **Parallel requests** | Submit from multiple native instances | HIGH |

### 3.3 Timing Attack Surface

| Attack Vector | Description | Exploitability |
|---------------|-------------|----------------|
| **Approval window snipe** | Time request when human likely tired | MEDIUM |
| **Expiry racing** | Act before approval expires | LOW |
| **Context drift** | Context changes between request and use | HIGH |
| **Concurrent modification** | Change context while request pending | HIGH |

### 3.4 Conflict Attack Surface

| Attack Vector | Description | Exploitability |
|---------------|-------------|----------------|
| **Mutual exclusion bypass** | Request capabilities that shouldn't coexist | HIGH |
| **Scope overlap** | Request overlapping scopes | MEDIUM |
| **Intent contradiction** | Request conflicting purposes | MEDIUM |
| **Temporal conflict** | Request conflicting time windows | MEDIUM |

---

## 4. ABUSE CASES

### AC-01: Human Fatigue Attack

**Precondition:** Attacker controls native code  
**Attack:** Submit 100+ ESCALATE requests in rapid succession  
**Goal:** Tire human reviewer into clicking "Approve All"  
**Impact:** Unauthorized capabilities granted  

**Mitigation Required:**
- Hard rate limit on ESCALATE requests
- Mandatory cooling period after threshold
- No "Approve All" functionality
- Auto-DENY after rate limit exceeded

### AC-02: Intent Obfuscation Attack

**Precondition:** Attacker controls request content  
**Attack:** Describe intent as "performance optimization" when actually requesting network access  
**Goal:** Trick human into approving dangerous capability  
**Impact:** Capability granted under false pretenses  

**Mitigation Required:**
- Intent must map to specific capability
- Human sees both intent AND capability name
- Contradictory intent/capability → DENY
- Intent audited for post-incident review

### AC-03: Approval Replay Attack

**Precondition:** Attacker captured previous approval token  
**Attack:** Submit captured token to gain repeated access  
**Goal:** Reuse single approval indefinitely  
**Impact:** Capability persists beyond intended scope  

**Mitigation Required:**
- Approvals are one-time use
- Approvals have mandatory expiry
- Context hash must match current context
- Replay detection in audit log

### AC-04: Conflict Exploitation Attack

**Precondition:** Attacker can submit multiple requests  
**Attack:** Submit MEMORY_READ + NETWORK simultaneously  
**Goal:** Create undefined state or leak data  
**Impact:** Sandbox integrity compromised  

**Mitigation Required:**
- Conflict detection matrix
- Both conflicting requests DENIED
- Conflict attempts logged as violations
- Pattern detection for repeated conflicts

### AC-05: Capability Cycling Attack

**Precondition:** Attacker receives DENY  
**Attack:** Immediately resubmit same request, hoping for different result  
**Goal:** Eventually receive ALLOW  
**Impact:** Determinism violated  

**Mitigation Required:**
- Same request = same result (determinism)
- Repeated denials trigger backoff
- Cycling detected and logged
- Escalating penalties for repeated attempts

### AC-06: Scope Inflation Attack

**Precondition:** Attacker controls requested_scope  
**Attack:** Request "all memory" instead of specific range  
**Goal:** Gain broader access than needed  
**Impact:** Over-permissioned access  

**Mitigation Required:**
- Scope must be validated
- Maximum scope limits defined
- Human sees requested scope
- Excessively broad scope → DENY or ESCALATE

---

## 5. EXPLICIT NON-GOALS

The following are **NOT protected against** by this design:

| Non-Goal | Reason |
|----------|--------|
| **Denial of service against request system** | Can always reject all requests |
| **Human making wrong decision with full information** | Human authority is supreme |
| **Covert channel via request timing** | Fundamental hardware limitation |
| **Insider with governance access** | Out of scope for request system |

---

## 6. THREAT SEVERITY CLASSIFICATION

| Severity | Definition | Example |
|----------|------------|---------|
| **CRITICAL** | Authority bypass or sandbox escape | Gain NEVER capability |
| **HIGH** | Human fatigue exploit or capability persistence | ESCALATE flooding |
| **MEDIUM** | Rate limit bypass or scope inflation | Parallel request abuse |
| **LOW** | Validation failure or audit gap | Malformed request |

---

## 7. THREAT MITIGATION REQUIREMENTS

### 7.1 Design-Time Mitigations

| Threat | Required Mitigation |
|--------|---------------------|
| Request flooding | Mandatory rate limit structure |
| Intent obfuscation | Intent/capability consistency check |
| Approval replay | One-time-use tokens with expiry |
| Conflict exploitation | Conflict detection matrix |
| Capability cycling | Determinism + backoff |
| Scope inflation | Scope validation + limits |

### 7.2 Human Protection Mitigations

| Threat | Required Mitigation |
|--------|---------------------|
| Fatigue attack | Rate limits + cooling periods |
| Confusion attack | Clear capability + intent display |
| Auto-approve abuse | No "Approve All" in design |
| Time pressure | Request queuing with delay |

---

## 8. INVARIANTS

1. **All requests are logged** — No silent requests
2. **All decisions are logged with reasons** — No unexplained outcomes
3. **Same request + same state = same outcome** — Determinism
4. **NEVER capabilities cannot be requested** — Immediate DENY
5. **Approvals expire** — No permanent grants from single approval
6. **Conflicts are detected and denied** — No undefined states
7. **Rate limits cannot be bypassed** — Hard enforcement

---

**END OF THREAT MODEL**
