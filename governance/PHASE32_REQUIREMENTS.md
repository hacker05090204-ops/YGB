# PHASE-32 REQUIREMENTS

**Phase:** Phase-32 — Human-Mediated Execution Decision & Continuation Governance  
**Type:** DESIGN-ONLY (NO CODE)  
**Version:** 1.0  
**Date:** 2026-01-25  
**Authority:** Human-Only  

---

## EXECUTIVE SUMMARY

Phase-32 defines the **human decision layer** that operates AFTER evidence is captured. Humans receive evidence presentations and issue explicit commands. The system never decides, only presents and executes explicit human instructions.

---

## FUNCTIONAL REQUIREMENTS

### REQ-01: Human Decision Points

The system SHALL present decision points at the following execution states:

| From State | Event | Decision Required |
|------------|-------|-------------------|
| DISPATCHED | Executor responds | Human decides next step |
| EVALUATED | Evaluation complete | Human decides continuation |
| AWAITING_RESPONSE | Timeout | Human decides abort/retry |
| ANY | Error detected | Human decides response |
| ANY | Human requests | Human can intervene anytime |

**Each decision point SHALL:**
- Present relevant evidence summary
- Wait for explicit human command
- NOT auto-proceed under any circumstance
- Log the decision request timestamp

---

### REQ-02: Decision Types

#### REQ-02.1: CONTINUE

| Aspect | Requirement |
|--------|-------------|
| Meaning | Proceed with next execution step |
| Trigger | Explicit human command only |
| Evidence | Human acknowledges evidence was reviewed |
| Audit | Decision logged with human identifier |

#### REQ-02.2: RETRY

| Aspect | Requirement |
|--------|-------------|
| Meaning | Re-attempt the same execution step |
| Trigger | Explicit human command + mandatory reason |
| Limits | Maximum retry count configurable by human |
| Audit | Each retry logged with reason |

#### REQ-02.3: ABORT

| Aspect | Requirement |
|--------|-------------|
| Meaning | Terminate execution permanently |
| Trigger | Explicit human command OR ambiguity default |
| Finality | No resumption after abort |
| Audit | Abort reason captured |

#### REQ-02.4: ESCALATE

| Aspect | Requirement |
|--------|-------------|
| Meaning | Escalate to higher authority |
| Trigger | Explicit human command + target authority |
| Effect | Decision deferred to escalation target |
| Audit | Escalation chain captured |

---

### REQ-03: Evidence Presentation

#### REQ-03.1: Evidence Human MAY See

| Evidence | Presentation |
|----------|--------------|
| Observation Point | Name (e.g., "PRE_DISPATCH") |
| Evidence Type | Name (e.g., "STATE_TRANSITION") |
| Timestamp | ISO-8601 formatted |
| Execution State | Current loop state |
| Chain Length | Number of evidence records |
| Decision History | Prior decisions in this session |
| Confidence Score | From Phase-30 normalization |

#### REQ-03.2: Evidence Human MUST NOT See (Directly)

| Evidence | Reason | Access Method |
|----------|--------|---------------|
| Raw Executor Output | May contain malicious/deceptive content | Governance override only |
| Raw Payload Bytes | Never parsed, never displayed | Audit access only |
| Self-Reported Status | Executor claims are untrusted | Shown only as "CLAIMED" |

---

### REQ-04: Decision Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    HUMAN DECISION FLOW                           │
│                                                                  │
│   ┌─────────────┐                                               │
│   │  EVIDENCE   │                                               │
│   │  CAPTURED   │                                               │
│   └──────┬──────┘                                               │
│          │                                                       │
│          ▼                                                       │
│   ┌─────────────┐                                               │
│   │   PRESENT   │                                               │
│   │  TO HUMAN   │                                               │
│   └──────┬──────┘                                               │
│          │                                                       │
│          ▼                                                       │
│   ┌─────────────┐     No input      ┌─────────────┐            │
│   │    WAIT     │ ──────────────────▶│    ABORT    │            │
│   │  FOR INPUT  │   (timeout)        │  (DEFAULT)  │            │
│   └──────┬──────┘                    └─────────────┘            │
│          │                                                       │
│          │ Human decides                                         │
│          ▼                                                       │
│   ┌──────────────────────────────────────────────────┐          │
│   │                                                   │          │
│   ▼             ▼             ▼             ▼         │          │
│ CONTINUE      RETRY        ABORT       ESCALATE      │          │
│   │             │             │             │         │          │
│   │             │             │             │         │          │
│   ▼             ▼             ▼             ▼         │          │
│ Proceed     Re-attempt    Terminate    Defer to      │          │
│ to next     same step     execution    authority     │          │
│                                                       │          │
└──────────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

---

### REQ-05: STOP Conditions

The following conditions SHALL trigger mandatory STOP (await human):

| ID | Condition | Action |
|----|-----------|--------|
| STOP-01 | Evidence captured | STOP, present to human |
| STOP-02 | Execution state change | STOP, present to human |
| STOP-03 | Timeout reached | STOP, request decision |
| STOP-04 | Error detected | STOP, request decision |
| STOP-05 | Chain integrity failure | STOP, ABORT recommended |
| STOP-06 | Prior decision pending | STOP, await prior resolution |
| STOP-07 | Escalation response received | STOP, present to original human |
| STOP-08 | Maximum retries reached | STOP, ABORT only option |
| STOP-09 | Human requests intervention | STOP immediately |
| STOP-10 | Ambiguity detected | STOP, ABORT default |

---

### REQ-06: Audit Requirements

Every decision SHALL be logged with:

| Field | Required |
|-------|----------|
| Decision ID | Unique identifier |
| Human Identifier | Who made decision |
| Timestamp | When decision made |
| Decision Type | CONTINUE/RETRY/ABORT/ESCALATE |
| Evidence Chain Hash | Link to evidence at decision time |
| Reason | Mandatory for RETRY and ESCALATE |
| Session ID | Link to observation session |

---

### REQ-07: Authority Preservation

| Invariant | Enforcement |
|-----------|-------------|
| Only humans decide | No automated decision paths |
| Explicit commands only | No implicit continuation |
| Audit trail immutable | Append-only decision log |
| Escalation preserved | Higher authority can override |
| Abort is final | No resumption post-abort |

---

## NON-FUNCTIONAL REQUIREMENTS

### REQ-NF01: Response Time

- Evidence presentation MUST complete within 500ms of capture
- Decision input MUST be accepted within 10ms of human action
- Audit logging MUST complete within 100ms

### REQ-NF02: Timeout Behavior

- Decision timeout: Configurable, default 5 minutes
- Timeout action: ABORT (not silent continuation)
- Timeout warning: At 80% of timeout period

### REQ-NF03: Accessibility

- Evidence presentation MUST be human-readable
- Decision interface MUST be unambiguous
- Error messages MUST be actionable

---

## ACCEPTANCE CRITERIA

| Criterion | Verification |
|-----------|--------------|
| All 4 decision types implemented | Unit test per type |
| All 10 STOP conditions enforced | Unit test per condition |
| Evidence visibility rules enforced | Unit test per rule |
| Audit trail complete | Integration test |
| No auto-continuation | Design review |
| No AI decision logic | Code review |
| 100% test coverage | Coverage report |

---

**END OF REQUIREMENTS**
