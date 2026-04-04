# 30-Day Production Hardening Plan

## Overview
Systematic 4-week plan to achieve ≥95% LAB precision, stable ECE ≤ 0.02, and zero governance violations.

---

## Week 1 — Calibration Tightening & Threshold Optimization
| Day | Task | Target |
|-----|------|--------|
| 1-2 | Temperature scaling calibration sweep | ECE ≤ 0.03 |
| 3-4 | Confidence threshold optimization (ROC curve analysis) | Precision ≥ 0.93 |
| 5 | Monotonicity enforcement validation | Zero non-monotonic bins |
| 6-7 | Brier score minimization + abstention band tuning | Brier ≤ 0.05 |

**Gate:** Lab precision ≥ 0.93, ECE ≤ 0.03

---

## Week 2 — Stress Hardening & Drift Robustness
| Day | Task | Target |
|-----|------|--------|
| 8-9 | Synthetic drift injection (KL spikes 0.3–0.8) | Auto-contain at KL > 0.45 |
| 10-11 | Confidence inflation attack resistance | Zero undetected inflation |
| 12 | Thermal stress testing (simulate 85°C GPU ramps) | Auto-pause verified |
| 13-14 | IO latency injection + recovery validation | <2s recovery time |

**Gate:** Zero uncontained drift events, thermal guard functional

---

## Week 3 — Duplicate Suppression Refinement
| Day | Task | Target |
|-----|------|--------|
| 15-16 | Duplicate cluster rate calibration | False positive rate ≤ 5% |
| 17-18 | High-similarity flood stress testing (20-50% dup rate) | Suppression ≥ 90% |
| 19 | Adaptive threshold decay verification | Smooth recovery after spike |
| 20-21 | Cross-scope duplicate detection validation | Zero cross-scope leaks |

**Gate:** Dup suppression ≥ 90%, zero cross-scope duplicates

---

## Week 4 — Parallel Hunt Stabilization
| Day | Task | Target |
|-----|------|--------|
| 22-23 | 5-target concurrent execution stress test | Zero resource violations |
| 24-25 | Mode switch timing validation (TRAIN↔HUNT) | <100ms transition |
| 26 | Scope validation under load (100 scope mutations) | 100% correct rejection |
| 27-28 | End-to-end hunt pipeline run (target→scope→dup→execute→report) | Full flow verified |

**Gate:** Zero governance violations, all 5 targets stable

---

## Final Goals
| Metric | Target | status |
|--------|--------|--------|
| LAB Precision | ≥ 95% | Pending |
| ECE | ≤ 0.02 | Pending |
| Brier Score | ≤ 0.04 | Pending |
| Duplicate Suppression | ≥ 92% | Pending |
| Scope Compliance | ≥ 99% | Pending |
| Governance Violations | 0 | Pending |
| Test Coverage (Python) | ≥ 95% | Pending |
| Test Coverage (C++) | ≥ 85% | Pending |
