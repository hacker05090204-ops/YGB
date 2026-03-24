"""Unified real training entrypoint.

This script intentionally delegates to the canonical training core so the system
has one execution pipeline, one checkpoint system, and one scheduler path.
"""

from __future__ import annotations

import json

from training_core.entrypoints import run_real_training_main


def main():
    result = run_real_training_main()
    if result is not None:
        print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
