#!/usr/bin/env python3
"""Approve a pending high-risk action.

Usage:
    python scripts/approve_action.py REQUEST_ID your_name
    python scripts/approve_action.py --list
    python scripts/approve_action.py --deny REQUEST_ID your_name "reason"
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def list_pending():
    """List all pending approvals."""
    from backend.hunter.live_gate import LiveActionGate

    gate = LiveActionGate()
    pending = gate.get_pending_approvals()

    if not pending:
        print("No pending approvals.")
        return

    print(f"\n{'='*70}")
    print(f"PENDING APPROVALS: {len(pending)}")
    print(f"{'='*70}\n")

    for action in pending:
        print(f"Request ID: {action.request_id}")
        print(f"Risk Level: {action.risk_level}")
        print(f"Vuln Type: {action.vuln_type}")
        print(f"Target: {action.target_url}")
        print(f"Payload: {action.payload_value[:80]}...")
        print(f"Timestamp: {action.timestamp}")
        print("-" * 70)


def approve(request_id: str, approver: str):
    """Approve a pending action."""
    from backend.hunter.live_gate import LiveActionGate

    gate = LiveActionGate()

    try:
        decision = gate.approve_pending(request_id, approver)
        print(f"\n✓ Action APPROVED by {approver}")
        print(f"  Request ID: {request_id}")
        print(f"  Risk Level: {decision.risk_level}")
        print(f"  Timestamp: {decision.timestamp}")
        return 0
    except ValueError as e:
        print(f"\n✗ Error: {e}")
        return 1


def deny(request_id: str, approver: str, reason: str):
    """Deny a pending action."""
    from backend.hunter.live_gate import LiveActionGate

    gate = LiveActionGate()

    try:
        decision = gate.deny_pending(request_id, approver, reason)
        print(f"\n✗ Action DENIED by {approver}")
        print(f"  Request ID: {request_id}")
        print(f"  Reason: {reason}")
        print(f"  Timestamp: {decision.timestamp}")
        return 0
    except ValueError as e:
        print(f"\n✗ Error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Approve or deny pending hunter actions")
    parser.add_argument("request_id", nargs="?", help="Request ID to approve/deny")
    parser.add_argument("approver", nargs="?", help="Your name")
    parser.add_argument("--list", action="store_true", help="List pending approvals")
    parser.add_argument("--deny", action="store_true", help="Deny instead of approve")
    parser.add_argument("--reason", help="Reason for denial")

    args = parser.parse_args()

    if args.list:
        list_pending()
        return 0

    if not args.request_id or not args.approver:
        parser.print_help()
        return 1

    if args.deny:
        reason = args.reason or "Manual denial"
        return deny(args.request_id, args.approver, reason)
    else:
        return approve(args.request_id, args.approver)


if __name__ == "__main__":
    sys.exit(main())
