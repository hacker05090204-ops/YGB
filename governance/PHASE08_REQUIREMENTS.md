# PHASE-08 REQUIREMENTS

**Phase:** Phase-08 - Evidence & Explanation Orchestration Layer  
**Status:** 📋 **APPROVED**  
**Creation Date:** 2026-01-23T15:18:00-05:00  

---

## PURPOSE

Phase-08 composes decision results (Phase-06) with bug knowledge (Phase-07) into structured evidence narratives with bilingual support.

---

## EVIDENCE NARRATIVE STRUCTURE

Each narrative MUST include:

| Field | Required | Description |
|-------|----------|-------------|
| step | ✅ YES | EvidenceStep enum value |
| decision | ✅ YES | FinalDecision from Phase-06 |
| bug_type | ✅ YES | BugType from Phase-07 |
| title_en | ✅ YES | English narrative title |
| title_hi | ✅ YES | Hindi narrative title |
| summary_en | ✅ YES | English summary |
| summary_hi | ✅ YES | Hindi summary |
| recommendation_en | ✅ YES | English recommendation |
| recommendation_hi | ✅ YES | Hindi recommendation |

---

## BUG EXPLANATION COMPOSITION RULES

1. **Decision First**: Always respect Phase-06 decision
2. **Knowledge Integration**: Pull explanation from Phase-07
3. **Bilingual**: Both Hindi and English required
4. **Explicit Templates**: Use predefined narrative templates
5. **No Guessing**: If unknown, mark as UNKNOWN

---

## DECISION + KNOWLEDGE MERGE RULES

| Decision | Bug Known | Result |
|----------|-----------|--------|
| ALLOW | Yes | "Allowed: [bug explanation]" |
| ALLOW | No | "Allowed: Unknown vulnerability type" |
| DENY | Yes | "Denied: [bug explanation]" |
| DENY | No | "Denied: Unknown vulnerability type" |
| ESCALATE | Yes | "Escalate for review: [bug explanation]" |
| ESCALATE | No | "Escalate: Unknown vulnerability type" |

---

## HINDI + ENGLISH NARRATIVE SUPPORT

All narratives MUST provide:

- English (en): Default language
- Hindi (hi): Devanagari script

Example:
```
title_en: "Security Assessment: XSS Vulnerability Detected"
title_hi: "सुरक्षा मूल्यांकन: XSS कमजोरी का पता चला"
```

---

## NO-GUESSING POLICY

> **CRITICAL:** Phase-08 MUST NEVER guess.
>
> - Unknown bugs use UNKNOWN explanation
> - Unknown decisions use default narrative
> - No fabrication of evidence
> - All output is deterministic

---

## SECURITY INVARIANTS

| Invariant ID | Name | Description |
|--------------|------|-------------|
| EVID_INV_01 | NO_GUESSING | Unknown inputs produce UNKNOWN narratives |
| EVID_INV_02 | DECISION_RESPECTED | Phase-06 decision is always reflected |
| EVID_INV_03 | KNOWLEDGE_INTEGRATED | Phase-07 knowledge is incorporated |
| EVID_INV_04 | BILINGUAL | Hindi + English required |
| EVID_INV_05 | DETERMINISTIC | Same inputs = same output |
| EVID_INV_06 | NO_EXECUTION | No exploit/action execution |
| EVID_INV_07 | IMMUTABLE | All dataclasses frozen |

---

## IMPLEMENTATION CONSTRAINTS

- Python only
- Pure functions only
- Frozen dataclasses only
- Closed enums only
- No IO
- No network
- No async/threading
- No subprocess
- No exec/eval

---

**END OF REQUIREMENTS**
