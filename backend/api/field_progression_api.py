"""
FIELD PROGRESSION API — Real-Time Field Ladder State
=====================================================
Endpoints:
  GET  /fields/state          — Full 23-field ladder state
  GET  /fields/progress       — Active field progress %
  POST /fields/approve/{id}   — Submit signed human approval
  POST /training/start        — Trigger training pipeline
  POST /hunt/start            — Enable hunt mode (gated)

GOVERNANCE:
  - All certification requires signed approval token (not boolean)
  - Hunt only enabled when CERTIFIED + FROZEN + human + authority locked
  - No mock data — "Awaiting Data" if unavailable
  - No auto-certification. No authority unlock.
=====================================================
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# =========================================================================
# PROJECT PATHS
# =========================================================================

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..'))

FIELD_STATE_PATH = os.path.join(PROJECT_ROOT, 'data', 'field_state.json')
APPROVAL_LEDGER_PATH = os.path.join(PROJECT_ROOT, 'data', 'approval_ledger.jsonl')

# =========================================================================
# GOVERNANCE IMPORTS (real modules, no mocks)
# =========================================================================

import sys
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

from governance.authority_lock import AuthorityLock
from governance.approval_ledger import ApprovalLedger


# =========================================================================
# FIELD LIFECYCLE CONSTANTS (mirrors C++ field_tasklist_engine.cpp)
# =========================================================================

TOTAL_FIELDS = 23

FIELD_NAMES = [
    "Client-Side Application Security",
    "API / Business Logic Security",
    "Subdomain Intelligence",
    "Authentication Systems",
    "Authorization Logic",
    "Rate Limiting",
    "Token Security",
    "Session Management",
    "CORS Misconfiguration",
    "SSRF",
    "Request Smuggling",
    "Template Injection",
    "Cache Poisoning",
    "Cloud Misconfiguration",
    "IAM",
    "CI/CD Security",
    "Container Security",
    "Kubernetes",
    "WAF Bypass",
    "CDN Misconfiguration",
    "Data Leakage",
    "Supply Chain",
    "Dependency Confusion",
]

LIFECYCLE_STATES = [
    "NOT_STARTED",
    "TRAINING",
    "STABILITY_CHECK",
    "CERTIFICATION_PENDING",
    "CERTIFIED",
    "FROZEN",
    "NEXT_FIELD",
]

# Thresholds (mirrors C++ field_certification_engine.cpp)
CLIENT_SIDE_THRESHOLDS = {
    "min_precision": 0.96,
    "max_fpr": 0.04,
    "min_dup": 0.88,
    "max_ece": 0.018,
    "min_stability_days": 7,
}

API_THRESHOLDS = {
    "min_precision": 0.95,
    "max_fpr": 0.05,
    "min_dup": 0.85,
    "max_ece": 0.02,
    "min_stability_days": 7,
}

# Tier mapping
TIERS = {
    0: {"tier": 1, "label": "Master", "thresholds": CLIENT_SIDE_THRESHOLDS},
    1: {"tier": 1, "label": "Master", "thresholds": API_THRESHOLDS},
}
# Fields 2–22 are all Tier 2/3 extended ladder → API thresholds
for i in range(2, TOTAL_FIELDS):
    tier = 2 if i < 12 else 3
    TIERS[i] = {"tier": tier, "label": "Extended", "thresholds": API_THRESHOLDS}


# =========================================================================
# STATE PERSISTENCE
# =========================================================================

def _load_field_state() -> dict:
    """Load field ladder state from disk."""
    if os.path.exists(FIELD_STATE_PATH):
        try:
            with open(FIELD_STATE_PATH) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load field state: {e}")

    # Initialize default state — only field 0 active
    return _default_state()


def _default_state() -> dict:
    """Generate initial ladder state."""
    fields = []
    for i in range(TOTAL_FIELDS):
        fields.append({
            "id": i,
            "name": FIELD_NAMES[i],
            "tier": TIERS[i]["tier"],
            "label": TIERS[i]["label"],
            "state": "NOT_STARTED" if i > 0 else "TRAINING",
            "precision": None,
            "fpr": None,
            "dup_detection": None,
            "ece": None,
            "stability_days": 0,
            "human_approved": False,
            "active": (i == 0),
            "locked": (i > 0),
            "certified": False,
            "frozen": False,
        })
    return {
        "active_field_id": 0,
        "certified_count": 0,
        "total_fields": TOTAL_FIELDS,
        "fields": fields,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def _save_field_state(state: dict) -> None:
    """Persist field state atomically (temp → rename)."""
    os.makedirs(os.path.dirname(FIELD_STATE_PATH) or ".", exist_ok=True)
    tmp = FIELD_STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
        f.flush()
    if os.path.exists(FIELD_STATE_PATH):
        os.remove(FIELD_STATE_PATH)
    os.rename(tmp, FIELD_STATE_PATH)


# =========================================================================
# PROGRESS CALCULATOR (mirrors C++ field_progress_calculator.cpp)
# =========================================================================

W_PRECISION = 0.30
W_FPR = 0.25
W_DUPLICATE = 0.20
W_ECE = 0.15
W_STABILITY = 0.10


def _calculate_progress(field: dict) -> dict:
    """Calculate weighted progress for a field. No mock data."""
    thresholds = TIERS[field["id"]]["thresholds"]
    weighted_sum = 0.0
    weight_sum = 0.0
    available = 0

    # Precision (higher=better)
    if field.get("precision") is not None:
        target = thresholds["min_precision"]
        score = min(field["precision"] / target, 1.0) if target > 0 else 0.0
        weighted_sum += score * W_PRECISION
        weight_sum += W_PRECISION
        available += 1
    else:
        score = None

    precision_score = score

    # FPR (lower=better)
    if field.get("fpr") is not None:
        target = thresholds["max_fpr"]
        score = 1.0 if field["fpr"] <= target else max(0.0, 1.0 - (field["fpr"] / (target * 2)))
        weighted_sum += score * W_FPR
        weight_sum += W_FPR
        available += 1
    else:
        score = None

    fpr_score = score

    # Duplicate detection (higher=better)
    if field.get("dup_detection") is not None:
        target = thresholds["min_dup"]
        score = min(field["dup_detection"] / target, 1.0) if target > 0 else 0.0
        weighted_sum += score * W_DUPLICATE
        weight_sum += W_DUPLICATE
        available += 1
    else:
        score = None

    dup_score = score

    # ECE (lower=better)
    if field.get("ece") is not None:
        target = thresholds["max_ece"]
        score = 1.0 if field["ece"] <= target else max(0.0, 1.0 - (field["ece"] / (target * 2)))
        weighted_sum += score * W_ECE
        weight_sum += W_ECE
        available += 1
    else:
        score = None

    ece_score = score

    # Stability
    stab = field.get("stability_days", 0)
    target_stab = thresholds["min_stability_days"]
    stab_score = min(stab / target_stab, 1.0) if target_stab > 0 else 1.0
    weighted_sum += stab_score * W_STABILITY
    weight_sum += W_STABILITY
    available += 1

    overall = (weighted_sum / weight_sum * 100.0) if weight_sum > 0 else 0.0
    overall = max(0.0, min(100.0, overall))

    return {
        "overall_percent": round(overall, 1),
        "precision_score": round(precision_score, 4) if precision_score is not None else None,
        "fpr_score": round(fpr_score, 4) if fpr_score is not None else None,
        "dup_score": round(dup_score, 4) if dup_score is not None else None,
        "ece_score": round(ece_score, 4) if ece_score is not None else None,
        "stability_score": round(stab_score, 4),
        "metrics_available": available,
        "metrics_total": 5,
        "status": "Awaiting Data" if available <= 1 else f"PROGRESS: {overall:.1f}%",
    }


# =========================================================================
# RUNTIME STATUS BUILDER — backend-authoritative, no frontend trust
# =========================================================================

RUNTIME_STATE_PATH = os.path.join(PROJECT_ROOT, 'data', 'runtime_status.json')


def _build_runtime_status(ladder_state: dict) -> dict:
    """Build runtime status from persisted runtime data.

    All values default to safe/awaiting state when unavailable.
    Frontend must NEVER trust its own cached state over this.
    """
    runtime = {
        "containment_active": False,
        "containment_reason": None,
        "precision_breach": False,
        "drift_alert": False,
        "freeze_valid": None,
        "freeze_reason": None,
        "training_velocity_samples_hr": None,
        "training_velocity_batches_sec": None,
        "gpu_utilization": None,
        "determinism_pass": None,
        "data_freshness": None,
        "merge_status": None,
    }

    # Load persisted runtime status if available
    if os.path.exists(RUNTIME_STATE_PATH):
        try:
            with open(RUNTIME_STATE_PATH) as f:
                persisted = json.load(f)

            # Only use explicitly set values — no fallback assumptions
            for key in runtime:
                if key in persisted:
                    runtime[key] = persisted[key]
        except Exception as e:
            logger.warning(f"Failed to load runtime status: {e}")

    # Check for demoted fields — containment override
    for field in ladder_state.get("fields", []):
        if field.get("demoted", False):
            runtime["containment_active"] = True
            runtime["containment_reason"] = (
                f"Field '{field.get('name', '?')}' demoted to TRAINING"
            )
            break

    return runtime


# =========================================================================
# ENDPOINT HANDLERS
# =========================================================================

def get_fields_state() -> dict:
    """
    GET /fields/state

    Returns full 23-field ladder state with progress and governance.
    """
    state = _load_field_state()

    # Enrich with progress, thresholds, and demotion flag
    for field in state["fields"]:
        field["progress"] = _calculate_progress(field)
        field["thresholds"] = TIERS[field["id"]]["thresholds"]
        # Demoted flag: field previously CERTIFIED/FROZEN but now back to TRAINING
        field["demoted"] = (
            field.get("state") == "TRAINING" and
            field.get("certified", False)
        )

    # Authority lock status
    auth = AuthorityLock.verify_all_locked()

    # Approval ledger status
    ledger = ApprovalLedger(APPROVAL_LEDGER_PATH)
    ledger.load()

    # Runtime status — backend-authoritative, no frontend-trusted state
    runtime = _build_runtime_status(state)

    return {
        "status": "ok",
        "ladder": state,
        "authority_lock": auth,
        "approval_ledger": {
            "entry_count": ledger.entry_count,
            "chain_hash": ledger.chain_hash,
            "chain_valid": ledger.verify_chain(),
        },
        "runtime": runtime,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_active_progress() -> dict:
    """
    GET /fields/progress

    Returns progress for the currently active field only.
    """
    state = _load_field_state()
    active_id = state.get("active_field_id", 0)

    if active_id >= TOTAL_FIELDS:
        return {
            "status": "all_complete",
            "message": "All fields certified",
            "certified_count": state.get("certified_count", 0),
            "total_fields": TOTAL_FIELDS,
        }

    field = state["fields"][active_id]
    progress = _calculate_progress(field)

    return {
        "status": "ok",
        "active_field": {
            "id": active_id,
            "name": field["name"],
            "tier": field["tier"],
            "state": field["state"],
            "progress": progress,
            "stability_days": field.get("stability_days", 0),
            "human_approved": field.get("human_approved", False),
        },
        "certified_count": state.get("certified_count", 0),
        "total_fields": TOTAL_FIELDS,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def approve_field(field_id: int, approver_id: str, reason: str) -> dict:
    """
    POST /fields/approve/{field_id}

    Submit signed human approval token for a field.
    Requires real approver ID and reason (not a boolean flag).
    """
    if not approver_id or not reason:
        return {
            "status": "error",
            "message": "APPROVAL_REJECTED: approver_id and reason required",
        }

    if field_id < 0 or field_id >= TOTAL_FIELDS:
        return {
            "status": "error",
            "message": f"INVALID_FIELD_ID: {field_id}",
        }

    # Sign and append to ledger
    ledger = ApprovalLedger(APPROVAL_LEDGER_PATH)
    ledger.load()

    token = ledger.sign_approval(field_id, approver_id, reason)

    if not ledger.verify_token(token):
        return {
            "status": "error",
            "message": "SIGNATURE_VERIFICATION_FAILED",
        }

    entry = ledger.append(token)

    # Update field state
    state = _load_field_state()
    state["fields"][field_id]["human_approved"] = True
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_field_state(state)

    return {
        "status": "ok",
        "message": f"APPROVED: field {field_id} ({FIELD_NAMES[field_id]})",
        "entry_sequence": entry["sequence"],
        "chain_hash": ledger.chain_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def start_training() -> dict:
    """
    POST /training/start

    Trigger full MODE-A→B→C training pipeline for active field.
    """
    # Verify authority locks
    auth = AuthorityLock.verify_all_locked()
    if not auth["all_locked"]:
        return {
            "status": "error",
            "message": f"AUTHORITY_VIOLATION: {auth['violations']}",
        }

    state = _load_field_state()
    active_id = state.get("active_field_id", 0)

    if active_id >= TOTAL_FIELDS:
        return {
            "status": "error",
            "message": "ALL_FIELDS_COMPLETE: no active field to train",
        }

    field = state["fields"][active_id]

    if field["state"] not in ("NOT_STARTED", "TRAINING"):
        return {
            "status": "error",
            "message": f"FIELD_STATE_ERROR: field '{field['name']}' is in "
                       f"state '{field['state']}', expected NOT_STARTED or TRAINING",
        }

    # Transition to TRAINING
    field["state"] = "TRAINING"
    field["active"] = True
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_field_state(state)

    return {
        "status": "ok",
        "message": f"TRAINING_STARTED: '{field['name']}' (field {active_id})",
        "field_id": active_id,
        "field_name": field["name"],
        "tier": field["tier"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def start_hunt() -> dict:
    """
    POST /hunt/start

    Enable hunt mode. Requires ALL gates:
      1. Active field CERTIFIED
      2. Active field FROZEN
      3. Human approval verified in ledger
      4. All authority locks intact
    """
    # Gate 1: Authority locks
    auth = AuthorityLock.verify_all_locked()
    if not auth["all_locked"]:
        return {
            "status": "blocked",
            "gate": "AUTHORITY_LOCK",
            "message": f"AUTHORITY_VIOLATION: {auth['violations']}",
        }

    state = _load_field_state()
    active_id = state.get("active_field_id", 0)

    if active_id >= TOTAL_FIELDS:
        return {"status": "error", "message": "NO_ACTIVE_FIELD"}

    field = state["fields"][active_id]

    # Gate 2: Must be CERTIFIED
    if not field.get("certified", False):
        return {
            "status": "blocked",
            "gate": "CERTIFICATION",
            "message": f"FIELD_NOT_CERTIFIED: '{field['name']}'",
        }

    # Gate 3: Must be FROZEN
    if not field.get("frozen", False):
        return {
            "status": "blocked",
            "gate": "FREEZE",
            "message": f"FIELD_NOT_FROZEN: '{field['name']}'",
        }

    # Gate 4: Human approval in ledger (not boolean)
    ledger = ApprovalLedger(APPROVAL_LEDGER_PATH)
    ledger.load()

    if not ledger.has_approval(active_id):
        return {
            "status": "blocked",
            "gate": "HUMAN_APPROVAL",
            "message": f"NO_APPROVAL_TOKEN: field {active_id} not in ledger",
        }

    # Verify chain integrity
    if not ledger.verify_chain():
        return {
            "status": "blocked",
            "gate": "LEDGER_INTEGRITY",
            "message": "LEDGER_TAMPERED: hash chain verification failed",
        }

    return {
        "status": "ok",
        "message": f"HUNT_ENABLED: '{field['name']}' (field {active_id})",
        "field_id": active_id,
        "field_name": field["name"],
        "tier": field["tier"],
        "gates_passed": 4,
        "gates_total": 4,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# =========================================================================
# FLASK REGISTRATION
# =========================================================================

def register_routes(app):
    """Register field progression endpoints with Flask app."""
    try:
        from flask import jsonify, request

        @app.route("/fields/state", methods=["GET"])
        def fields_state_route():
            return jsonify(get_fields_state())

        @app.route("/fields/progress", methods=["GET"])
        def fields_progress_route():
            return jsonify(get_active_progress())

        @app.route("/fields/approve/<int:field_id>", methods=["POST"])
        def fields_approve_route(field_id):
            data = request.get_json(force=True, silent=True) or {}
            return jsonify(approve_field(
                field_id,
                data.get("approver_id", ""),
                data.get("reason", ""),
            ))

        @app.route("/training/start", methods=["POST"])
        def training_start_route():
            return jsonify(start_training())

        @app.route("/hunt/start", methods=["POST"])
        def hunt_start_route():
            return jsonify(start_hunt())

        logger.info("Field progression endpoints registered (Flask)")
    except Exception as e:
        logger.warning(f"Flask registration skipped: {e}")


# =========================================================================
# SELF-TEST
# =========================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== Fields State ===")
    print(json.dumps(get_fields_state(), indent=2))
    print("\n=== Active Progress ===")
    print(json.dumps(get_active_progress(), indent=2))
    print("\n=== Start Training ===")
    print(json.dumps(start_training(), indent=2))
    print("\n=== Start Hunt (should be blocked) ===")
    print(json.dumps(start_hunt(), indent=2))
