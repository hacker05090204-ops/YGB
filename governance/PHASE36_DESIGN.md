# PHASE-36 DESIGN

**Phase:** Phase-36 — Native Execution Sandbox Boundary (C/C++)  
**Status:** DESIGN COMPLETE — NO IMPLEMENTATION AUTHORIZED  
**Date:** 2026-01-26T18:45:00-05:00  

---

## 1. CONCEPTUAL SANDBOX BOUNDARY

### 1.1 Fundamental Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         GOVERNANCE ZONE                                    │
│  (Human-controlled, Full authority, Phase-01 through Phase-35)            │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                     INTERFACE ZONE                                   │  │
│  │  (Limited trust, Validation only, Phase-35 boundary)                │  │
│  │                                                                      │  │
│  │  ┌───────────────────────────────────────────────────────────────┐  │  │
│  │  │                    NATIVE ZONE                                 │  │  │
│  │  │  (ZERO trust, NO authority, Sandboxed C/C++)                  │  │  │
│  │  │                                                                │  │  │
│  │  │  ❌ CANNOT escape to Interface Zone                           │  │  │
│  │  │  ❌ CANNOT call syscalls                                      │  │  │
│  │  │  ❌ CANNOT access network                                     │  │  │
│  │  │  ❌ CANNOT spawn processes                                    │  │  │
│  │  │  ❌ CANNOT modify governance                                  │  │  │
│  │  │                                                                │  │  │
│  │  └───────────────────────────────────────────────────────────────┘  │  │
│  │                           ▲                                          │  │
│  │                           │ BOUNDARY (all crossings validated)       │  │
│  │                           ▼                                          │  │
│  │  ┌───────────────────────────────────────────────────────────────┐  │  │
│  │  │              BOUNDARY VALIDATOR                                │  │  │
│  │  │  • Validates all data crossing boundary                       │  │  │
│  │  │  • Enforces capability model                                  │  │  │
│  │  │  • Applies DENY-BY-DEFAULT                                    │  │  │
│  │  │  • Escalates to human when required                           │  │  │
│  │  └───────────────────────────────────────────────────────────────┘  │  │
│  │                                                                      │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
└───────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Zone Characteristics

| Zone | Trust Level | Authority | Modification Rights |
|------|-------------|-----------|---------------------|
| **GOVERNANCE** | FULL | Complete system authority | Human only |
| **INTERFACE** | LIMITED | Validation and routing | Frozen by design |
| **NATIVE** | ZERO | No authority whatsoever | None |

---

## 2. TRUST ZONES

### 2.1 GOVERNANCE Zone

**Definition:** The outer ring containing all human-controlled governance logic.

| Property | Value |
|----------|-------|
| Trust level | FULL |
| Contains | Phase-01 through Phase-35 |
| Authority | Complete system control |
| Modification | Human-only, requires governance reopening |
| Responsibility | Defines all sandbox rules |

### 2.2 INTERFACE Zone

**Definition:** The intermediate layer that validates all boundary crossings.

| Property | Value |
|----------|-------|
| Trust level | LIMITED |
| Contains | Phase-35 validation engine |
| Authority | Validate, route, deny, escalate |
| Modification | Frozen, no runtime changes |
| Responsibility | Enforce sandbox boundary |

**Interface Zone Responsibilities:**

1. Validate all data entering from NATIVE zone
2. Validate all data exiting to NATIVE zone
3. Check capability permissions for all operations
4. Apply DENY-BY-DEFAULT to all unknown operations
5. ESCALATE dangerous operations to GOVERNANCE zone
6. Log all boundary crossings for audit

### 2.3 NATIVE Zone

**Definition:** The innermost ring containing sandboxed native code with ZERO trust.

| Property | Value |
|----------|-------|
| Trust level | ZERO |
| Contains | Future C/C++ execution (not yet implemented) |
| Authority | NONE |
| Modification | Impossible from within |
| Responsibility | Execute only permitted operations |

**Native Zone Absolute Prohibitions:**

| Prohibition | Reason |
|-------------|--------|
| ❌ Escape to Interface zone | Boundary is one-way |
| ❌ Call syscalls directly | OS access forbidden |
| ❌ Access network | Exfiltration prevention |
| ❌ Spawn processes | Isolation enforcement |
| ❌ Access filesystem | Data protection |
| ❌ Modify memory outside sandbox | Containment |
| ❌ Read governance files | Metadata protection |

---

## 3. CAPABILITY MODEL

### 3.1 Capability Classification

All capabilities are classified into one of three states:

| State | Meaning | Action |
|-------|---------|--------|
| **NEVER** | Capability is absolutely forbidden | DENY always |
| **ESCALATE** | Capability requires human approval | ESCALATE to Phase-13 |
| **ALLOW** | Capability may be permitted | Check further constraints |

### 3.2 Capability Registry

#### 3.2.1 Compute Capabilities

| Capability | State | Rationale |
|------------|-------|-----------|
| Pure arithmetic | ALLOW | Safe, deterministic |
| Floating point | ALLOW | Safe with caveats |
| Memory read (within sandbox) | ALLOW | Contained |
| Memory write (within sandbox) | ALLOW | Contained |
| Function calls (within sandbox) | ALLOW | Contained |

#### 3.2.2 System Capabilities

| Capability | State | Rationale |
|------------|-------|-----------|
| open() | NEVER | Filesystem access |
| read() from fd | NEVER | I/O escape |
| write() to fd | NEVER | I/O escape |
| mmap() | NEVER | Memory mapping |
| mprotect() | NEVER | Memory permissions |
| fork() | NEVER | Process creation |
| exec*() | NEVER | Code execution |
| socket() | NEVER | Network access |
| connect() | NEVER | Network access |
| send/recv | NEVER | Network access |
| ioctl() | NEVER | Device control |
| ptrace() | NEVER | Process debugging |
| *ANY OTHER SYSCALL* | NEVER | Default deny |

#### 3.2.3 Resource Capabilities

| Capability | State | Rationale |
|------------|-------|-----------|
| Allocate heap memory | ESCALATE | Resource consumption |
| Spawn threads | NEVER | Concurrency escape |
| Create shared memory | NEVER | IPC escape |
| Set signal handlers | NEVER | Control flow hijack |
| Access clock | ESCALATE | Timing attacks |
| Random number generation | ESCALATE | Entropy consumption |

#### 3.2.4 Data Capabilities

| Capability | State | Rationale |
|------------|-------|-----------|
| Read input buffer | ALLOW | Designed input channel |
| Write output buffer | ALLOW | Designed output channel |
| Access environment variables | NEVER | Information leak |
| Access command line args | NEVER | Information leak |

---

## 4. BOUNDARY DECISION MODEL

### 4.1 Decision Flow

```
Request arrives at boundary
        │
        ▼
┌─────────────────┐
│ Is capability   │ ──NO──▶ DENY (unknown = forbidden)
│ registered?     │
└───────┬─────────┘
        │ YES
        ▼
┌─────────────────┐
│ Is capability   │ ──YES──▶ DENY (absolute prohibition)
│ state = NEVER?  │
└───────┬─────────┘
        │ NO
        ▼
┌─────────────────┐
│ Is capability   │ ──YES──▶ ESCALATE to Phase-13
│ state = ESCALT? │           │
└───────┬─────────┘           │
        │ NO                  ▼
        ▼              ┌───────────────┐
┌─────────────────┐    │ Human         │
│ Is context      │    │ approved?     │──NO──▶ DENY
│ valid?          │    └───────┬───────┘
└───────┬─────────┘            │ YES
        │ NO → DENY            ▼
        │ YES                ALLOW
        ▼
┌─────────────────┐
│ Is request      │
│ well-formed?    │ ──NO──▶ DENY
└───────┬─────────┘
        │ YES
        ▼
      ALLOW
```

### 4.2 Decision Table

| Capability State | Context Valid | Request Valid | Human Required | Human Approved | Decision |
|------------------|---------------|---------------|----------------|----------------|----------|
| UNREGISTERED | Any | Any | Any | Any | DENY |
| NEVER | Any | Any | Any | Any | DENY |
| ESCALATE | Any | Any | N/A | NO | DENY |
| ESCALATE | Any | Any | N/A | YES | ALLOW |
| ALLOW | NO | Any | Any | Any | DENY |
| ALLOW | YES | NO | Any | Any | DENY |
| ALLOW | YES | YES | NO | N/A | ALLOW |
| ALLOW | YES | YES | YES | NO | DENY |
| ALLOW | YES | YES | YES | YES | ALLOW |

### 4.3 Decision Reasons

| Decision | Reason Code | Description |
|----------|-------------|-------------|
| DENY | `BD-001` | Unknown capability |
| DENY | `BD-002` | NEVER capability |
| DENY | `BD-003` | ESCALATE without human approval |
| DENY | `BD-004` | Invalid context |
| DENY | `BD-005` | Malformed request |
| DENY | `BD-006` | Human required but not approved |
| ALLOW | `BD-100` | All checks passed |
| ESCALATE | `BD-200` | Requires human approval |

---

## 5. ENUM SPECIFICATIONS (DESIGN ONLY)

### 5.1 SandboxCapability Enum

```
SandboxCapability (CLOSED ENUM - 12 members):
  COMPUTE
  MEMORY_READ
  MEMORY_WRITE
  INPUT_READ
  OUTPUT_WRITE
  HEAP_ALLOCATE
  CLOCK_ACCESS
  RANDOM_ACCESS
  FILESYSTEM
  NETWORK
  PROCESS
  UNKNOWN
```

### 5.2 CapabilityState Enum

```
CapabilityState (CLOSED ENUM - 3 members):
  NEVER
  ESCALATE
  ALLOW
```

### 5.3 BoundaryDecision Enum

```
BoundaryDecision (CLOSED ENUM - 3 members):
  ALLOW
  DENY
  ESCALATE
```

### 5.4 ViolationType Enum

```
ViolationType (CLOSED ENUM - 8 members):
  UNKNOWN_CAPABILITY
  FORBIDDEN_CAPABILITY
  INVALID_CONTEXT
  MALFORMED_REQUEST
  HUMAN_DENIAL
  BOUNDARY_ESCAPE
  MEMORY_VIOLATION
  TIMEOUT
```

---

## 6. DATACLASS SPECIFICATIONS (DESIGN ONLY)

### 6.1 SandboxBoundaryRequest (frozen=True)

```
SandboxBoundaryRequest:
  request_id: str
  capability: SandboxCapability
  context_hash: str
  timestamp: str
  payload_hash: str
```

### 6.2 SandboxBoundaryResponse (frozen=True)

```
SandboxBoundaryResponse:
  request_id: str
  decision: BoundaryDecision
  reason_code: str
  reason_description: str
  escalation_required: bool
```

### 6.3 SandboxViolation (frozen=True)

```
SandboxViolation:
  violation_id: str
  violation_type: ViolationType
  timestamp: str
  context_snapshot: str
  severity: str
```

---

## 7. FAILURE MODES

### 7.1 Failure Mode Catalog

| Failure Mode | Detection | Response |
|--------------|-----------|----------|
| **Memory violation** | Boundary validator | DENY + log + terminate |
| **Capability violation** | Capability checker | DENY + log |
| **Boundary escape attempt** | Monitor | DENY + log + alert + terminate |
| **Timeout** | Watchdog | DENY + log + terminate |
| **Crash** | Signal handler | Log + quarantine |
| **Invalid output** | Output validator | DENY + log |
| **Malformed request** | Request parser | DENY + log |

### 7.2 Design-Time Detection

Violations MUST be detectable at design-time via:

| Detection Method | What It Detects |
|------------------|-----------------|
| Capability enumeration | Unknown capabilities |
| Decision table analysis | Inconsistent rules |
| Enum closure verification | New forbidden members |
| Dataclass freeze verification | Mutability violations |

---

## 8. INTEGRATION WITH EXISTING PHASES

### 8.1 Phase-35 Integration

| Phase-35 Concept | Phase-36 Usage |
|------------------|----------------|
| `ExecutorClass.NATIVE` | Native zone executor type |
| `CapabilityType` | Maps to SandboxCapability |
| `InterfaceDecision` | Maps to BoundaryDecision |
| `validate_executor_interface` | Pre-boundary validation |

### 8.2 Phase-13 Integration

| Phase-13 Concept | Phase-36 Usage |
|------------------|----------------|
| `HumanPresence.REQUIRED` | ESCALATE triggers this |
| `HumanPresence.BLOCKING` | NEVER capabilities block |
| `human_confirmed` | Required for ESCALATE → ALLOW |
| `ReadinessState` | Gate before native execution |

### 8.3 Phase-22 Integration

| Phase-22 Concept | Phase-36 Usage |
|------------------|----------------|
| `NativeProcessState` | Sandbox process state |
| `NativeExitReason` | Sandbox exit classification |
| `IsolationDecision` | Post-execution decision |

---

## 9. INVARIANTS

1. **Native zone has ZERO authority** — Cannot grant itself permissions
2. **All boundary crossings are validated** — No unchecked data passes
3. **Default is DENY** — Unknown operations are forbidden
4. **ESCALATE requires human** — No automatic escalation approval
5. **NEVER means NEVER** — No override possible
6. **Frozen phases are immutable** — Phase-35 and earlier cannot be modified
7. **Human authority is supreme** — Only human can approve escalations

---

## 10. DESIGN VALIDATION RULES

| Rule | Validation Method |
|------|-------------------|
| All enums are closed | Member count verification |
| All dataclasses are frozen | frozen=True verification |
| All capabilities are registered | Exhaustive enumeration |
| No orphan capabilities | Coverage check |
| Decision table is complete | All combinations tested |
| No contradictory rules | Formal consistency check |

---

**END OF DESIGN**
