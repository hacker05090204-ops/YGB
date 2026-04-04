# YGB Governance Boundaries

## What This System Never Does

This system NEVER:
- Scans any target autonomously
- Submits any finding without human confirmation
- Executes any action the human has not explicitly approved
- Overrides a governance decision
- Learns bug labels without verified human-confirmed proof
- Uses network access during training
- Makes any security assessment without human review

## What Requires Human Authorization

Every state transition requires explicit human approval.
The approval workflow is enforced at the API level.
No code path bypasses the approval panel.
REAL mode requires a second explicit confirmation.
AUTONOMOUS_FIND mode caps at 12 hours maximum.

## Guard Functions

11 guards in g38_self_trained_model.py all return False.
They represent capabilities the AI intentionally does not have.
These are permanent governance constraints, not configuration.
They cannot be overridden by any runtime flag or environment variable.

## What The Intelligence Layer Does

G38 learns structural patterns from 37,000+ public vulnerability
reports. It identifies what kinds of targets historically have
had what kinds of issues. It presents this to human researchers
as context, not as findings. Humans decide everything.
