# PHASE-38 REQUIREMENTS

**Phase:** Phase-38 — Browser Execution Boundary  
**Status:** REQUIREMENTS DEFINED — DESIGN ONLY  
**Date:** 2026-01-26T19:00:00-05:00  

---

## 1. OVERVIEW

Phase-38 defines the **governance model for browser execution** including headed/headless classification, capability boundaries, storage governance, and cross-tab isolation.

> [!WARNING]
> **DEFAULT BEHAVIOR: DENY**
>
> Any browser action not explicitly permitted is DENIED by default.
> Unknown browser types are DENIED.
> Cross-origin access is DENIED.
> All external navigation requires ESCALATE.

---

## 2. FUNCTIONAL REQUIREMENTS

### FR-01: Browser Execution Lifecycle

The design MUST define a complete browser lifecycle:

| Stage | Description |
|-------|-------------|
| **INITIALIZATION** | Browser process started with security flags |
| **CONFIGURATION** | Profile, extensions, settings applied |
| **NAVIGATION** | Navigate to approved target |
| **EXECUTION** | Perform approved actions |
| **CAPTURE** | Collect results (screenshot, DOM, etc.) |
| **TERMINATION** | Browser process killed, state cleared |

### FR-02: Executor Classification

The design MUST classify browser executors:

| Executor Type | Description | Risk Level |
|---------------|-------------|------------|
| HEADED | Visible browser window | MEDIUM |
| HEADLESS | No visible window | HIGH |
| HEADED_CHROMIUM | Headed Ungoogled Chromium | MEDIUM |
| HEADLESS_CHROMIUM | Headless Ungoogled Chromium | HIGH |
| HEADED_EDGE | Headed Microsoft Edge | MEDIUM-HIGH |
| HEADLESS_EDGE | Headless Microsoft Edge | HIGH |
| UNKNOWN | Any other browser | FORBIDDEN |

### FR-03: Capability Boundary Mapping

The design MUST define capability states for all browser actions:

| Capability | State | Rationale |
|------------|-------|-----------|
| Navigate same-origin | ALLOW | Within approved scope |
| Navigate cross-origin | ESCALATE | New domain, new risk |
| Form submission (non-credential) | ALLOW | Data entry |
| Form submission (credentials) | ESCALATE | Sensitive operation |
| Download file | ESCALATE | Filesystem access |
| Upload file | ESCALATE | Data exfiltration risk |
| Execute JavaScript | ALLOW | Within page context |
| Inject JavaScript | ESCALATE | Code injection |
| Access LocalStorage | ESCALATE | Persistent data |
| Access IndexedDB | ESCALATE | Persistent data |
| Access cookies | ESCALATE | Session data |
| Install extension | NEVER | Privilege escalation |
| Access saved passwords | NEVER | Credential theft |
| Access browser history | NEVER | Privacy violation |
| Open new tab | ESCALATE | Resource expansion |
| Close tab | ALLOW | Cleanup |
| Screenshot capture | ALLOW | Result collection |
| DOM extraction | ALLOW | Result collection |

### FR-04: Storage Governance

The design MUST specify storage access rules:

| Storage Type | Same-Origin | Cross-Origin |
|--------------|-------------|--------------|
| LocalStorage | ESCALATE | NEVER |
| IndexedDB | ESCALATE | NEVER |
| SessionStorage | ALLOW | NEVER |
| Cookies | ESCALATE | NEVER |
| Cache | ESCALATE | NEVER |
| Service Workers | NEVER | NEVER |

### FR-05: Tab Isolation Rules

The design MUST enforce tab isolation:

| Rule | Enforcement |
|------|-------------|
| Single-tab policy | Only one active tab per execution |
| No cross-tab messaging | PostMessage blocked |
| Tab authority | Each tab has independent authority |
| Tab lifetime | Tab terminates with execution |
| Popup blocking | All popups blocked |

### FR-06: Browser Type Governance

The design MUST define browser type rules:

| Browser | Permitted | Conditions |
|---------|-----------|------------|
| Ungoogled Chromium | ✅ YES | Primary automation browser |
| Microsoft Edge | ⚠️ CONDITIONAL | Testing only, ESCALATE |
| Google Chrome | ❌ NO | Telemetry concerns |
| Firefox | ❌ NO | Different engine, untested |
| Safari | ❌ NO | Apple ecosystem, untested |
| Other | ❌ NO | Unknown attack surface |

---

## 3. NON-FUNCTIONAL REQUIREMENTS

### NFR-01: Zero Trust Assumption

The design MUST assume:

| Assumption |
|------------|
| All websites are potentially hostile |
| All JavaScript is potentially malicious |
| All browser extensions are suspicious |
| Headless mode does not increase safety |

### NFR-02: Deny-by-Default

The design MUST enforce:

| Condition | Result |
|-----------|--------|
| Unknown browser type → DENY |
| Unknown action → DENY |
| Cross-origin access → DENY |
| Missing human approval → DENY |
| Default → DENY |

### NFR-03: Audit Trail

The design MUST log:

| Event | Required Logging |
|-------|------------------|
| Browser start | Timestamp, type, flags |
| Navigation | URL, approval status |
| Action | Type, target, result |
| Storage access | Type, origin, data hash |
| Browser termination | Timestamp, exit code |

### NFR-04: Determinism

The design MUST ensure:

| Requirement |
|-------------|
| Same input → same output |
| No random behavior in decision logic |
| Browser randomization does not affect governance |

### NFR-05: Isolation

The design MUST ensure:

| Isolation Type | Enforcement |
|----------------|-------------|
| Profile isolation | Fresh profile per execution |
| Process isolation | Separate OS process |
| Network isolation | Scoped to approved domains |
| Storage isolation | No cross-execution persistence |

---

## 4. EXPLICIT PROHIBITIONS

### PR-01: Forbidden in Phase-38 Design

| Item | Status |
|------|--------|
| Browser automation code | ❌ FORBIDDEN |
| Playwright/Selenium scripts | ❌ FORBIDDEN |
| Actual browser process spawning | ❌ FORBIDDEN |
| Extension installation code | ❌ FORBIDDEN |
| Network request code | ❌ FORBIDDEN |

### PR-02: Browser Actions MUST NOT

| Prohibition |
|-------------|
| Access saved passwords |
| Access browser history |
| Install extensions without ESCALATE |
| Navigate without approval |
| Submit credentials without ESCALATE |
| Access cross-origin storage |
| Persist data across executions |
| Spawn child processes |
| Access OS resources |

### PR-03: Dangerous Browser Flags NEVER Permitted

| Flag | Status |
|------|--------|
| `--no-sandbox` | ❌ NEVER |
| `--disable-web-security` | ❌ NEVER |
| `--disable-features=IsolateOrigins` | ❌ NEVER |
| `--disable-site-isolation-trials` | ❌ NEVER |
| `--remote-debugging-port` (production) | ❌ NEVER |
| `--allow-running-insecure-content` | ❌ NEVER |
| `--disable-gpu-sandbox` | ❌ NEVER |

---

## 5. INTEGRATION REQUIREMENTS

### IR-01: Phase-35 Integration

| Requirement | Specification |
|-------------|---------------|
| Executor class | Use ExecutorClass.BROWSER |
| Decision vocabulary | Consistent with InterfaceDecision |
| Validation | Use Phase-35 validators |

### IR-02: Phase-13 Integration

| Requirement | Specification |
|-------------|---------------|
| ESCALATE routing | Route to Phase-13 human gate |
| Human presence | Respect HumanPresence states |
| Confirmation | Require human_confirmed |

### IR-03: Phase-36/37 Integration

| Requirement | Specification |
|-------------|---------------|
| Boundary model | Compatible with Phase-36 sandbox |
| Capability requests | Compatible with Phase-37 governor |

---

## 6. BOUNDARY PRESERVATION REQUIREMENTS

### BP-01: No Earlier Phase Modification

| Frozen Phase | Status |
|--------------|--------|
| Phase-01 through Phase-37 | ❌ NO MODIFICATION PERMITTED |

### BP-02: No Authority Leakage

| Requirement |
|-------------|
| Browser cannot grant itself authority |
| Browser cannot bypass human gates |
| Browser actions do not persist authority |

---

## 7. VERIFICATION REQUIREMENTS

### VR-01: Design Testability

All design elements MUST be testable via:

| Method |
|--------|
| Governance document review |
| Capability matrix completeness check |
| Decision table analysis |
| Boundary isolation verification |

### VR-02: No Code Required

Verification MUST NOT require:

| Not Required |
|--------------|
| Browser process execution |
| Website navigation |
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
