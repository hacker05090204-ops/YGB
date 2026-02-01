# PHASE-38 DESIGN

**Phase:** Phase-38 — Browser Execution Boundary  
**Status:** DESIGN COMPLETE — NO IMPLEMENTATION AUTHORIZED  
**Date:** 2026-01-26T19:00:00-05:00  

---

## 1. BROWSER EXECUTION LIFECYCLE

### 1.1 Lifecycle Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                       BROWSER EXECUTION LIFECYCLE                             │
└──────────────────────────────────────────────────────────────────────────────┘

  GOVERNANCE ZONE              INTERFACE ZONE                BROWSER ZONE
       │                            │                              │
       │ (1) EXECUTION REQUEST      │                              │
       │───────────────────────────▶│                              │
       │   BrowserExecutionRequest  │                              │
       │                            │                              │
       │                            │ (2) VALIDATION               │
       │                            │   • Browser type allowed?    │
       │                            │   • Target approved?         │
       │                            │   • Capabilities granted?    │
       │                            │                              │
       │                            │ (3) INITIALIZATION           │
       │                            │──────────────────────────────▶│
       │                            │   Start browser process      │
       │                            │   Apply security flags       │
       │                            │   Create isolated profile    │
       │                            │                              │
       │                            │ (4) NAVIGATION               │
       │                            │──────────────────────────────▶│
       │                            │   Navigate to target URL     │
       │                            │   Wait for page load         │
       │                            │                              │
       │                            │ (5) ACTION EXECUTION         │
       │                            │◀─────────────────────────────▶│
       │                            │   Execute approved actions   │
       │                            │   Validate each action       │
       │                            │   Log all actions            │
       │                            │                              │
       │                            │ (6) RESULT CAPTURE           │
       │                            │◀──────────────────────────────│
       │                            │   Screenshot                 │
       │                            │   DOM extraction             │
       │                            │   Specified data             │
       │                            │                              │
       │                            │ (7) TERMINATION              │
       │                            │──────────────────────────────▶│
       │                            │   Kill browser process       │
       │                            │   Clear profile              │
       │                            │   Delete temp files          │
       │                            │                              │
       │ (8) RESULT DELIVERY        │                              │
       │◀───────────────────────────│                              │
       │   BrowserExecutionResult   │                              │
       │                            │                              │
```

### 1.2 Lifecycle Stage Specifications

| Stage | Input | Output | Failure Mode |
|-------|-------|--------|--------------|
| REQUEST | Execution parameters | Parsed request | Malformed → DENY |
| VALIDATION | Request + policies | Approval decision | Invalid → DENY |
| INITIALIZATION | Approved request | Browser process | Start failure → ABORT |
| NAVIGATION | Target URL | Page state | Navigation failure → ABORT |
| ACTION EXECUTION | Action list | Action results | Action failure → DENY action |
| RESULT CAPTURE | Capture spec | Result data | Capture failure → PARTIAL |
| TERMINATION | - | Cleanup confirmation | Force kill if needed |
| RESULT DELIVERY | All results | Final result | Always succeeds |

---

## 2. EXECUTOR CLASSIFICATION

### 2.1 BrowserExecutorType Enum

```
BrowserExecutorType (CLOSED ENUM - 7 members):
  HEADED_CHROMIUM      # Visible Ungoogled Chromium
  HEADLESS_CHROMIUM    # Invisible Ungoogled Chromium
  HEADED_EDGE          # Visible Microsoft Edge
  HEADLESS_EDGE        # Invisible Microsoft Edge
  HEADED_UNKNOWN       # Any other headed browser
  HEADLESS_UNKNOWN     # Any other headless browser
  FORBIDDEN            # Explicitly forbidden browser
```

### 2.2 Executor Risk Classification

| Executor Type | Risk Level | Default Policy |
|---------------|------------|----------------|
| HEADED_CHROMIUM | MEDIUM | ALLOW with constraints |
| HEADLESS_CHROMIUM | HIGH | ESCALATE for sensitive |
| HEADED_EDGE | MEDIUM-HIGH | ESCALATE always |
| HEADLESS_EDGE | HIGH | ESCALATE always |
| HEADED_UNKNOWN | CRITICAL | DENY |
| HEADLESS_UNKNOWN | CRITICAL | DENY |
| FORBIDDEN | CRITICAL | DENY always |

### 2.3 Headed vs Headless Decision Matrix

| Action | Headed | Headless |
|--------|--------|----------|
| Navigate to approved URL | ALLOW | ALLOW |
| Navigate to unknown domain | ESCALATE | ESCALATE |
| Form submission (data) | ALLOW | ALLOW |
| Form submission (credentials) | ESCALATE | DENY |
| Download file | ESCALATE | DENY |
| Upload file | ESCALATE | ESCALATE |
| Screenshot | ALLOW | ALLOW |
| Install extension | DENY | DENY |

---

## 3. CAPABILITY BOUNDARY MAPPING

### 3.1 BrowserCapability Enum

```
BrowserCapability (CLOSED ENUM - 18 members):
  NAVIGATE_SAME_ORIGIN
  NAVIGATE_CROSS_ORIGIN
  FORM_SUBMIT_DATA
  FORM_SUBMIT_CREDENTIALS
  FILE_DOWNLOAD
  FILE_UPLOAD
  EXECUTE_JAVASCRIPT
  INJECT_JAVASCRIPT
  ACCESS_LOCALSTORAGE
  ACCESS_INDEXEDDB
  ACCESS_COOKIES
  ACCESS_SESSION_STORAGE
  INSTALL_EXTENSION
  ACCESS_PASSWORDS
  ACCESS_HISTORY
  OPEN_TAB
  CLOSE_TAB
  SCREENSHOT
```

### 3.2 Capability State Matrix

| Capability | State | Headed | Headless |
|------------|-------|--------|----------|
| NAVIGATE_SAME_ORIGIN | ALLOW | ✅ | ✅ |
| NAVIGATE_CROSS_ORIGIN | ESCALATE | ESCALATE | ESCALATE |
| FORM_SUBMIT_DATA | ALLOW | ✅ | ✅ |
| FORM_SUBMIT_CREDENTIALS | ESCALATE | ESCALATE | DENY |
| FILE_DOWNLOAD | ESCALATE | ESCALATE | DENY |
| FILE_UPLOAD | ESCALATE | ESCALATE | ESCALATE |
| EXECUTE_JAVASCRIPT | ALLOW | ✅ | ✅ |
| INJECT_JAVASCRIPT | ESCALATE | ESCALATE | ESCALATE |
| ACCESS_LOCALSTORAGE | ESCALATE | ESCALATE | ESCALATE |
| ACCESS_INDEXEDDB | ESCALATE | ESCALATE | ESCALATE |
| ACCESS_COOKIES | ESCALATE | ESCALATE | ESCALATE |
| ACCESS_SESSION_STORAGE | ALLOW | ✅ | ✅ |
| INSTALL_EXTENSION | NEVER | ❌ | ❌ |
| ACCESS_PASSWORDS | NEVER | ❌ | ❌ |
| ACCESS_HISTORY | NEVER | ❌ | ❌ |
| OPEN_TAB | ESCALATE | ESCALATE | DENY |
| CLOSE_TAB | ALLOW | ✅ | ✅ |
| SCREENSHOT | ALLOW | ✅ | ✅ |

---

## 4. STORAGE GOVERNANCE

### 4.1 StorageType Enum

```
StorageType (CLOSED ENUM - 6 members):
  LOCAL_STORAGE
  SESSION_STORAGE
  INDEXED_DB
  COOKIES
  CACHE_API
  SERVICE_WORKER
```

### 4.2 Storage Access Matrix

| Storage Type | Same-Origin | Cross-Origin | Clear After |
|--------------|-------------|--------------|-------------|
| LOCAL_STORAGE | ESCALATE | NEVER | ✅ YES |
| SESSION_STORAGE | ALLOW | NEVER | ✅ YES |
| INDEXED_DB | ESCALATE | NEVER | ✅ YES |
| COOKIES | ESCALATE | NEVER | ✅ YES |
| CACHE_API | ESCALATE | NEVER | ✅ YES |
| SERVICE_WORKER | NEVER | NEVER | ✅ YES |

### 4.3 Storage Lifecycle Rules

| Rule | Enforcement |
|------|-------------|
| Fresh storage per execution | Profile created fresh |
| No cross-execution persistence | Profile deleted after |
| No cross-origin access | SOP strictly enforced |
| Audit logging | All access logged |

---

## 5. TAB ISOLATION

### 5.1 TabPolicy Enum

```
TabPolicy (CLOSED ENUM - 4 members):
  SINGLE_TAB        # Only one tab allowed
  CONTROLLED_MULTI  # Multiple tabs, all controlled
  INDEPENDENT_MULTI # Multiple independent tabs
  FORBIDDEN         # No tabs allowed
```

### 5.2 Tab Isolation Rules

| Rule | Enforcement |
|------|-------------|
| Single-tab policy | Only one active tab per execution |
| No cross-tab messaging | PostMessage blocked |
| No SharedWorker | SharedWorker registration blocked |
| No BroadcastChannel | BroadcastChannel blocked |
| Popup blocking | All popups blocked |
| Tab lifetime | Tab terminates with execution |

### 5.3 Cross-Tab Decision Table

| Action | Single-Tab | Controlled-Multi | Independent-Multi |
|--------|------------|------------------|-------------------|
| Open new tab | DENY | ESCALATE | NEVER |
| PostMessage | DENY | DENY | NEVER |
| SharedWorker | DENY | DENY | NEVER |
| BroadcastChannel | DENY | DENY | NEVER |
| Window reference | DENY | DENY | NEVER |

---

## 6. BROWSER TYPE ROLES

### 6.1 Ungoogled Chromium Role

| Aspect | Specification |
|--------|---------------|
| Role | Primary automation browser |
| Trust level | LIMITED |
| Default policy | ALLOW with constraints |
| Telemetry | None (removed) |
| Update policy | Manual updates required |
| Extension policy | Disabled by default |

### 6.2 Microsoft Edge Role

| Aspect | Specification |
|--------|---------------|
| Role | Secondary/testing browser |
| Trust level | LOWER |
| Default policy | ESCALATE always |
| Telemetry | Present (Microsoft) |
| Update policy | System-managed |
| Extension policy | Disabled always |

### 6.3 Browser Selection Logic

```
Browser type specified
        │
        ▼
┌─────────────────┐
│ Is Ungoogled    │──YES──▶ Apply Chromium rules
│ Chromium?       │
└───────┬─────────┘
        │ NO
        ▼
┌─────────────────┐
│ Is Microsoft    │──YES──▶ ESCALATE + Apply Edge rules
│ Edge?           │
└───────┬─────────┘
        │ NO
        ▼
┌─────────────────┐
│ Is explicitly   │──YES──▶ DENY
│ forbidden?      │
└───────┬─────────┘
        │ NO
        ▼
    DENY (unknown)
```

---

## 7. ENUM SPECIFICATIONS (DESIGN ONLY)

### 7.1 BrowserExecutionState Enum

```
BrowserExecutionState (CLOSED ENUM - 8 members):
  PENDING
  VALIDATED
  INITIALIZING
  NAVIGATING
  EXECUTING
  CAPTURING
  TERMINATING
  COMPLETED
```

### 7.2 BrowserDecision Enum

```
BrowserDecision (CLOSED ENUM - 4 members):
  ALLOW
  DENY
  ESCALATE
  ABORT
```

### 7.3 BrowserViolationType Enum

```
BrowserViolationType (CLOSED ENUM - 12 members):
  UNKNOWN_BROWSER_TYPE
  FORBIDDEN_BROWSER_TYPE
  NAVIGATION_DENIED
  CAPABILITY_DENIED
  STORAGE_VIOLATION
  TAB_POLICY_VIOLATION
  EXTENSION_VIOLATION
  CREDENTIAL_ACCESS_ATTEMPT
  CROSS_ORIGIN_VIOLATION
  SANDBOX_FLAG_VIOLATION
  TIMEOUT
  CRASH
```

---

## 8. DATACLASS SPECIFICATIONS (DESIGN ONLY)

### 8.1 BrowserExecutionRequest (frozen=True)

```
BrowserExecutionRequest (frozen=True):
  request_id: str
  browser_type: BrowserExecutorType
  target_url: str
  actions: List[BrowserAction]
  timeout_seconds: int
  capture_screenshot: bool
  capture_dom: bool
  context_hash: str
```

### 8.2 BrowserAction (frozen=True)

```
BrowserAction (frozen=True):
  action_id: str
  action_type: BrowserActionType
  target_selector: str
  value: str
  capability_required: BrowserCapability
```

### 8.3 BrowserExecutionResult (frozen=True)

```
BrowserExecutionResult (frozen=True):
  request_id: str
  final_state: BrowserExecutionState
  decision: BrowserDecision
  screenshot_hash: str
  dom_hash: str
  action_results: List[ActionResult]
  violations: List[BrowserViolationType]
  duration_ms: int
```

### 8.4 BrowserSecurityContext (frozen=True)

```
BrowserSecurityContext (frozen=True):
  sandbox_enabled: bool
  site_isolation_enabled: bool
  extensions_disabled: bool
  remote_debugging_disabled: bool
  profile_isolated: bool
  storage_cleared: bool
```

---

## 9. DANGEROUS FLAGS GOVERNANCE

### 9.1 ForbiddenBrowserFlag Enum

```
ForbiddenBrowserFlag (CLOSED ENUM - 10 members):
  NO_SANDBOX
  DISABLE_WEB_SECURITY
  DISABLE_SITE_ISOLATION
  REMOTE_DEBUGGING_PORT
  ALLOW_INSECURE_CONTENT
  DISABLE_GPU_SANDBOX
  DISABLE_FEATURES_ISOLATE_ORIGINS
  USER_DATA_DIR_SHARED
  ENABLE_AUTOMATION_DETECTION_BYPASS
  DISABLE_EXTENSIONS_EXCEPT
```

### 9.2 Flag Validation Rule

| Rule | Action |
|------|--------|
| Any forbidden flag detected | DENY execution |
| Unknown flag detected | ESCALATE |
| Required security flag missing | DENY execution |

### 9.3 Required Security Flags

| Flag | Required Value |
|------|----------------|
| `--no-sandbox` | NOT PRESENT |
| `--disable-web-security` | NOT PRESENT |
| `--site-per-process` | PRESENT |
| `--disable-extensions` | PRESENT |

---

## 10. INTEGRATION WITH EARLIER PHASES

### 10.1 Phase-35 Integration

| Phase-35 Concept | Phase-38 Usage |
|------------------|----------------|
| `ExecutorClass.BROWSER` | Maps to BrowserExecutorType |
| `InterfaceDecision` | Consistent decision vocabulary |
| `validate_executor_interface` | Pre-execution validation |

### 10.2 Phase-13 Integration

| Phase-13 Concept | Phase-38 Usage |
|------------------|----------------|
| `HumanPresence.REQUIRED` | ESCALATE triggers |
| `human_confirmed` | Required for ESCALATE actions |
| Human Safety Gate | All sensitive browser actions |

### 10.3 Phase-36/37 Integration

| Phase | Integration |
|-------|-------------|
| Phase-36 | Browser is bounded executor |
| Phase-37 | Browser actions use capability request model |

---

## 11. INVARIANTS

1. **Saved passwords are NEVER accessible** — Absolute prohibition
2. **Browser history is NEVER accessible** — Privacy protection
3. **Extensions are NEVER auto-installed** — Privilege protection
4. **Cross-origin storage is NEVER accessible** — SOP enforcement
5. **Single-tab policy by default** — Isolation enforcement
6. **Fresh profile per execution** — No state leakage
7. **Sandbox is always enabled** — No bypass flags
8. **Human approves sensitive actions** — ESCALATE enforcement
9. **All browser actions are logged** — Audit trail
10. **Browser terminates after execution** — No persistence

---

## 12. DESIGN VALIDATION RULES

| Rule | Validation Method |
|------|-------------------|
| All enums are CLOSED | Member count verification |
| All dataclasses are frozen=True | Specification check |
| All capabilities classified | Matrix completeness |
| All browser types handled | Decision coverage |
| All flags governed | Flag list exhaustive |
| Phase integration complete | Reference verification |

---

**END OF DESIGN**
