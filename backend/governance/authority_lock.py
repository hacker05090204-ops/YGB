"""
authority_lock.py — Permanent Authority Lock

Hardcoded governance constants. These are NEVER modifiable at runtime.
No configuration override. No environment variable override.
No API endpoint to modify these values.

ALL guards are permanently FALSE / blocked.
"""


class AuthorityLock:
    """Immutable authority lock — all dangerous capabilities permanently disabled."""

    # These are compile-time constants. DO NOT make them configurable.
    AUTO_SUBMIT: bool = False
    AUTHORITY_UNLOCK: bool = False
    COMPANY_TARGETING: bool = False
    MID_TRAINING_MERGE: bool = False
    VOICE_HUNT_TRIGGER: bool = False
    VOICE_SUBMIT: bool = False
    AUTO_NEGOTIATE: bool = False
    SKIP_CERTIFICATION: bool = False
    CROSS_FIELD_DATA: bool = False
    TIME_FORCED_COMPLETION: bool = False
    PARALLEL_FIELD_TRAINING: bool = False

    @classmethod
    def verify_all_locked(cls) -> dict:
        """Verify all authority locks are in their safe state (False)."""
        locks = {
            "AUTO_SUBMIT": cls.AUTO_SUBMIT,
            "AUTHORITY_UNLOCK": cls.AUTHORITY_UNLOCK,
            "COMPANY_TARGETING": cls.COMPANY_TARGETING,
            "MID_TRAINING_MERGE": cls.MID_TRAINING_MERGE,
            "VOICE_HUNT_TRIGGER": cls.VOICE_HUNT_TRIGGER,
            "VOICE_SUBMIT": cls.VOICE_SUBMIT,
            "AUTO_NEGOTIATE": cls.AUTO_NEGOTIATE,
            "SKIP_CERTIFICATION": cls.SKIP_CERTIFICATION,
            "CROSS_FIELD_DATA": cls.CROSS_FIELD_DATA,
            "TIME_FORCED_COMPLETION": cls.TIME_FORCED_COMPLETION,
            "PARALLEL_FIELD_TRAINING": cls.PARALLEL_FIELD_TRAINING,
        }

        all_safe = all(v is False for v in locks.values())
        violations = [k for k, v in locks.items() if v is not False]

        return {
            "all_locked": all_safe,
            "total_locks": len(locks),
            "violations": violations,
            "status": "ALL_SAFE" if all_safe else f"VIOLATION: {violations}"
        }

    @classmethod
    def is_action_allowed(cls, action: str) -> dict:
        """Check if an action is allowed under current authority locks."""
        blocked_actions = {
            "auto_submit": cls.AUTO_SUBMIT,
            "unlock_authority": cls.AUTHORITY_UNLOCK,
            "target_company": cls.COMPANY_TARGETING,
            "merge_mid_training": cls.MID_TRAINING_MERGE,
            "voice_hunt": cls.VOICE_HUNT_TRIGGER,
            "voice_submit": cls.VOICE_SUBMIT,
            "auto_negotiate": cls.AUTO_NEGOTIATE,
            "skip_cert": cls.SKIP_CERTIFICATION,
            "cross_field": cls.CROSS_FIELD_DATA,
            "force_time": cls.TIME_FORCED_COMPLETION,
            "parallel_train": cls.PARALLEL_FIELD_TRAINING,
        }

        if action in blocked_actions:
            return {
                "allowed": blocked_actions[action],
                "reason": f"PERMANENTLY_BLOCKED: {action}"
            }

        return {"allowed": True, "reason": f"ACTION_NOT_RESTRICTED: {action}"}
