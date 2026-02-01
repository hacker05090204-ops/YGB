# PHASE-11 REQUIREMENTS

**Phase:** Phase-11 - Work Scheduling, Fair Distribution & Delegation Governance  
**Status:** REQUIREMENTS DEFINED  
**Date:** 2026-01-24T13:25:00-05:00  

---

## 1. OVERVIEW

Phase-11 defines the scheduling and delegation POLICY for distributed bug bounty work. This is a **pure backend** module that determines work distribution—NOT execution.

---

## 2. FAIR TARGET DISTRIBUTION RULES

### 2.1 Distribution Principles

| Principle | Description |
|-----------|-------------|
| **Equitable** | Work distributed fairly across available workers |
| **Load-balanced** | Workers with fewer active assignments get priority |
| **Capability-aware** | Assign based on worker capability (not execution) |
| **Deterministic** | Same input → same distribution |

### 2.2 Distribution Decision Table

| Worker Load | Worker Capability | Target Difficulty | → Assignment |
|-------------|-------------------|-------------------|--------------|
| Light (0-2) | Matches | Any | **ASSIGN** |
| Medium (3-5) | Matches | Low/Medium | **ASSIGN** |
| Medium (3-5) | Matches | High | **QUEUE** |
| Heavy (6+) | Any | Any | **QUEUE** |
| Any | Not Matches | Any | **DENY** |

---

## 3. TEAM-WIDE UNIQUENESS CONSTRAINTS

### 3.1 Uniqueness Rules

| Rule ID | Rule | Enforcement |
|---------|------|-------------|
| `UNQ-001` | Same bug cannot be assigned to multiple workers | DENY duplicate |
| `UNQ-002` | Same target cannot be worked by multiple workers | DENY conflict |
| `UNQ-003` | Workers cannot hold duplicate assignments | DENY self-duplicate |

### 3.2 Conflict Resolution

| Conflict Type | Resolution |
|---------------|------------|
| Worker A has target, Worker B requests | DENY to B |
| Worker A expired, Worker B requests | ALLOW to B |
| Worker A completed, Worker B requests | ALLOW to B (different instance) |

---

## 4. PARALLEL WORK ELIGIBILITY

### 4.1 Parallel Policy Rules

| Worker Type | Max Parallel | GPU Impact |
|-------------|--------------|------------|
| Standard | 3 | N/A |
| Premium | 5 | N/A |
| GPU-enabled | 5 | Eligibility flag only |

### 4.2 GPU Capability

> **CRITICAL:** GPU capability affects ELIGIBILITY, not execution.
> Phase-11 does NOT control GPU hardware.

| Attribute | Use |
|-----------|-----|
| `has_gpu` | Eligibility for GPU-requiring targets |
| `gpu_memory_gb` | Threshold eligibility check |

---

## 5. DELEGATION & TAKEOVER AUTHORITY

### 5.1 Delegation Decision Table

| Delegator | Target Owner | Explicit Consent | → Decision |
|-----------|--------------|------------------|------------|
| HUMAN | Any | N/A | **ALLOW** (override) |
| OPERATOR | Self-owned | N/A | **ALLOW** |
| OPERATOR | Other-owned | YES | **ALLOW** |
| OPERATOR | Other-owned | NO | **DENY** |
| SYSTEM | Any | Any | **DENY** (no system delegation) |

### 5.2 Takeover Authority

| Role | Can Takeover | Conditions |
|------|--------------|------------|
| HUMAN | YES | Always |
| ADMINISTRATOR | YES | With reason |
| OPERATOR | NO | Must request |
| SYSTEM | NO | Never |

---

## 6. DENY-BY-DEFAULT SCHEDULING

### 6.1 Principle

> **INVARIANT:** In the absence of explicit permission, scheduling is DENIED.

### 6.2 Deny Conditions

| Condition | Result |
|-----------|--------|
| Unknown worker | DENY |
| Invalid assignment context | DENY |
| Inactive policy | DENY |
| Worker at capacity | DENY |
| Target already assigned | DENY |
| Capability mismatch | DENY |
| All conditions met | ALLOW |

---

## 7. DATA TYPES REQUIRED

| Type | Kind | Frozen |
|------|------|--------|
| `WorkSlotStatus` | Enum | N/A (enum) |
| `DelegationDecision` | Enum | N/A (enum) |
| `SchedulingPolicy` | Dataclass | ✅ `frozen=True` |
| `WorkerProfile` | Dataclass | ✅ `frozen=True` |
| `WorkAssignmentContext` | Dataclass | ✅ `frozen=True` |
| `AssignmentResult` | Dataclass | ✅ `frozen=True` |

---

## 8. FUNCTIONAL REQUIREMENTS

### 8.1 Required Functions

| Function | Input | Output |
|----------|-------|--------|
| `assign_work()` | context | `AssignmentResult` |
| `can_assign()` | worker, target | `bool` |
| `get_worker_load()` | worker_id, assignments | `int` |
| `delegate_work()` | context | `DelegationDecision` |
| `is_eligible_for_target()` | worker, target | `bool` |

### 8.2 Function Constraints

All functions MUST be:
- Pure (no side effects)
- Deterministic (same input → same output)
- Total (handle all possible inputs)

---

## 9. SECURITY REQUIREMENTS

| Requirement | Enforcement |
|-------------|-------------|
| No execution logic | No `exec()`, `eval()`, `subprocess` |
| No network access | No `socket`, `http`, `requests` |
| No filesystem write | No `open(..., 'w')` |
| No async/threading | No `asyncio`, `threading` |

---

**END OF REQUIREMENTS**
