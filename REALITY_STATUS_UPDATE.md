# Reality Status Update

This update aligns runtime behavior with governance by removing fake production-facing outputs.

## What changed

- CVE lookups now use the real NVD API path when reachable and return explicit `OFFLINE`,
  `DEGRADED`, or `INVALID_KEY` states when they are not.
- Gmail alerts no longer report fake success. They send through real SMTP only when configured;
  otherwise they fail closed.
- Screen inspection no longer pretends to inspect when no backend exists. It now requires
  externally produced findings or returns `FAILED`.
- PyTorch training and inference no longer fabricate training metrics or predictions when torch is
  unavailable.
- Training transparency reports no longer publish hardcoded calibration/accuracy numbers when real
  measurements are unavailable.
- Model registry hashing no longer returns fake hashes for missing model files.
- Verified training data encoding removes post-verification shortcut features that leaked labels
  into training vectors.
- Production validation now evaluates historical predictions instead of copying ground truth into
  predictions.
- Frontend pages for bug reports, earnings, projects, security, and the control panel now use live
  backend data or honest empty/unavailable states instead of demo content.

## Governance stance

- No change in authority boundaries.
- Discovery remains read-only.
- CVE remains passive-only.
- Screen inspection remains read-only.
- Email remains notification-only.
- Training/inference remain advisory and cannot override governance.

## Operational implication

If credentials, datasets, or native backends are missing, the system should now expose that gap
explicitly instead of showing mock success data.
