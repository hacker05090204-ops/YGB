# PHASE-07 REQUIREMENTS

**Phase:** Phase-07 - Bug Intelligence & Knowledge Resolution Layer  
**Status:** 📋 **APPROVED**  
**Creation Date:** 2026-01-23T15:03:00-05:00  

---

## PURPOSE

Phase-07 provides deterministic bug intelligence and knowledge resolution. It returns structured explanations for known vulnerability types and explicitly marks unknown bugs as UNKNOWN.

---

## BUG TAXONOMY

Phase-07 MUST support the following bug types:

| Bug Type | Category | CWE Reference |
|----------|----------|---------------|
| XSS | Injection | CWE-79 |
| SQLI | Injection | CWE-89 |
| IDOR | Access Control | CWE-639 |
| SSRF | Request Forgery | CWE-918 |
| CSRF | Request Forgery | CWE-352 |
| XXE | Injection | CWE-611 |
| PATH_TRAVERSAL | File Access | CWE-22 |
| OPEN_REDIRECT | Validation | CWE-601 |
| RCE | Code Execution | CWE-94 |
| LFI | File Inclusion | CWE-98 |
| UNKNOWN | Unknown | N/A |

---

## KNOWLEDGE SOURCE MODEL

| Source | Description |
|--------|-------------|
| CVE | Common Vulnerabilities and Exposures (abstract reference) |
| CWE | Common Weakness Enumeration (abstract reference) |
| MANUAL | Manually defined explanation |
| UNKNOWN | Bug type not recognized |

---

## EXPLANATION REQUIREMENTS

Each explanation MUST include:

| Field | Required | Description |
|-------|----------|-------------|
| bug_type | ✅ YES | The BugType enum value |
| title_en | ✅ YES | English title |
| title_hi | ✅ YES | Hindi title (Devanagari) |
| description_en | ✅ YES | English description |
| description_hi | ✅ YES | Hindi description (Devanagari) |
| impact_en | ✅ YES | English impact statement |
| impact_hi | ✅ YES | Hindi impact statement |
| steps_en | ✅ YES | English step-by-step explanation |
| steps_hi | ✅ YES | Hindi step-by-step explanation |
| cwe_id | ✅ YES | CWE identifier (or None) |
| source | ✅ YES | KnowledgeSource enum value |

---

## NO GUESSING RULE

> **CRITICAL:** If bug type is unknown, the resolver MUST:
>
> 1. Return `BugType.UNKNOWN`
> 2. Return source as `KnowledgeSource.UNKNOWN`
> 3. Return explicit "Unknown vulnerability type" message
> 4. NEVER fabricate explanations
> 5. NEVER guess similar bug types

---

## HINDI + ENGLISH SUPPORT

All explanations MUST provide:

- English (en): Default language
- Hindi (hi): Devanagari script

Example:
```
title_en: "Cross-Site Scripting (XSS)"
title_hi: "क्रॉस-साइट स्क्रिप्टिंग (XSS)"
```

---

## SECURITY INVARIANTS

| Invariant ID | Name | Description |
|--------------|------|-------------|
| KNOW_INV_01 | NO_GUESSING | Unknown bugs return UNKNOWN |
| KNOW_INV_02 | DETERMINISTIC | Same input always gives same output |
| KNOW_INV_03 | NO_FABRICATION | No fake CVE/CWE numbers |
| KNOW_INV_04 | BILINGUAL | Hindi and English required |
| KNOW_INV_05 | EXPLICIT_STEPS | Step-by-step explanations |
| KNOW_INV_06 | NO_EXECUTION | No exploit execution |
| KNOW_INV_07 | IMMUTABLE | All dataclasses frozen |

---

## IMPLEMENTATION CONSTRAINTS

- Python only
- Pure functions only
- Frozen dataclasses only
- Closed enums only
- No IO
- No network
- No browser
- No subprocess
- No exec/eval
- No guessing

---

**END OF REQUIREMENTS**
