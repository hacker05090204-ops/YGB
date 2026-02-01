# PHASE-36 REQUIREMENTS

**Phase:** Phase-36 — Native Execution Sandbox Boundary (C/C++)  
**Status:** REQUIREMENTS DEFINED — DESIGN ONLY  
**Date:** 2026-01-26T18:45:00-05:00  

---

## 1. OVERVIEW

Phase-36 defines the **governance boundaries** that any future native code (C/C++) execution MUST obey. This is a **DESIGN SPECIFICATION ONLY** — no implementation exists or is authorized.

> [!WARNING]
> **DEFAULT BEHAVIOR: DENY**
>
> Any native code not explicitly permitted by this design is DENIED by default.

---

## 2. FUNCTIONAL REQUIREMENTS

### FR-01: Trust Zone Definitions

The design MUST define exactly three trust zones:

| Zone | Trust Level | Authority |
|------|-------------|-----------|
| **NATIVE** | ZERO trust | No authority |
| **INTERFACE** | LIMITED trust | Validation only |
| **GOVERNANCE** | FULL trust | Human-controlled |

### FR-02: Sandbox Boundary Contract

The design MUST specify a contract defining:

1. What native code can NEVER do (explicit prohibitions)
2. What native code can ONLY do with human approval (escalation)
3. What native code MAY do (minimal allow-list)

### FR-03: Capability Restriction Model

The design MUST enumerate all capabilities and their status:

| Capability Category | Status |
|--------------------|--------|
| Memory allocation | DESIGN-DEFINED |
| System calls | DESIGN-DEFINED |
| File I/O | DESIGN-DEFINED |
| Network access | DESIGN-DEFINED |
| Process spawning | DESIGN-DEFINED |
| IPC | DESIGN-DEFINED |

### FR-04: Decision Model

The design MUST define a three-state decision model:

| Decision | Meaning |
|----------|---------|
| **ALLOW** | Operation explicitly permitted |
| **DENY** | Operation explicitly forbidden |
| **ESCALATE** | Requires human approval |

### FR-05: Failure Mode Cataloging

The design MUST catalog all failure modes:

- Memory violation failures
- Capability violation failures
- Boundary crossing failures
- Timeout failures
- Crash failures

### FR-06: Integration with Phase-35

The design MUST specify integration with Phase-35:

- How `ExecutorClass.NATIVE` is validated
- How capabilities are checked via Phase-35
- How interface decisions propagate
- How errors are reported

### FR-07: Integration with Phase-13

The design MUST preserve Phase-13 Human Safety Gate:

- Native execution MUST respect `HumanPresence.REQUIRED`
- Native execution MUST respect `HumanPresence.BLOCKING`
- Native execution CANNOT bypass human confirmation

---

## 3. NON-FUNCTIONAL REQUIREMENTS

### NFR-01: Zero Trust Assumption

The design MUST assume:

| Assumption |
|------------|
| Native code is hostile by default |
| Compiler is attacker-controlled |
| Runtime is attacker-controlled |
| Inputs are attacker-controlled |

### NFR-02: Deny-by-Default

The design MUST enforce:

- Unknown operation → DENY
- Missing capability → DENY
- Invalid context → DENY
- Ambiguous request → DENY

### NFR-03: Auditability

The design MUST be:

- Fully documented
- Independently verifiable
- Testable without native code
- Reviewable by external auditors

### NFR-04: Immutability

The design MUST produce:

- Frozen dataclass specifications (frozen=True)
- Closed enum specifications (no new members)
- Immutable contract definitions

### NFR-05: Testability

The design MUST be:

- 100% testable at design level
- Verifiable via governance tests
- Validatable via negative path tests

---

## 4. EXPLICIT PROHIBITIONS

### PR-01: Forbidden in Phase-36 Design

| Item | Status |
|------|--------|
| C/C++ source code | ❌ FORBIDDEN |
| Compilation instructions | ❌ FORBIDDEN |
| Syscall invocation | ❌ FORBIDDEN |
| Memory management code | ❌ FORBIDDEN |
| Execution flow logic | ❌ FORBIDDEN |
| Runtime assumptions | ❌ FORBIDDEN |

### PR-02: Native Code MUST NOT

The design MUST specify that native code can NEVER:

| Prohibition |
|-------------|
| Execute without human pre-approval |
| Access network without ESCALATE |
| Spawn processes |
| Modify governance files |
| Access sandboxed process memory |
| Elevate privileges |
| Bypass Phase-35 interface validation |
| Bypass Phase-13 human safety gate |

---

## 5. INTEGRATION REQUIREMENTS

### IR-01: Phase-35 Integration

| Requirement | Specification |
|-------------|---------------|
| Executor class | `ExecutorClass.NATIVE` |
| Default decision | `InterfaceDecision.DENY` |
| Capability validation | Via Phase-35 engine |
| Intent validation | Via Phase-35 engine |

### IR-02: Phase-13 Integration

| Requirement | Specification |
|-------------|---------------|
| Human presence | MUST respect `HumanPresence` |
| Readiness state | MUST respect `ReadinessState` |
| Blocking condition | MUST honor `BLOCKING` |
| Confirmation | MUST require `human_confirmed` |

### IR-03: Phase-22 Integration

| Requirement | Specification |
|-------------|---------------|
| Process state | MUST use `NativeProcessState` |
| Exit reason | MUST use `NativeExitReason` |
| Isolation decision | MUST use `IsolationDecision` |

---

## 6. BOUNDARY PRESERVATION REQUIREMENTS

### BP-01: No Earlier Phase Modification

| Frozen Phase | Status |
|--------------|--------|
| Phase-01 through Phase-35 | ❌ NO MODIFICATION PERMITTED |

### BP-02: No Authority Leakage

| Requirement |
|-------------|
| Native zone CANNOT grant itself interface authority |
| Interface zone CANNOT grant itself governance authority |
| Only HUMAN can modify authority |

---

## 7. VERIFICATION REQUIREMENTS

### VR-01: Design Testability

All design elements MUST be testable via:

- Governance document review
- Formal specification checking
- Negative path enumeration
- Decision table validation

### VR-02: No Native Code Required

Verification MUST NOT require:

- Compilation of any C/C++ code
- Execution of any native binary
- Runtime testing

### VR-03: 100% Coverage Required

All design elements MUST have:

- Documented test strategy
- Explicit acceptance criteria
- Failure condition enumeration

---

**END OF REQUIREMENTS**
