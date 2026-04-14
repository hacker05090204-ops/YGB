from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.device_manager import (
    _AUTO_TORCH,
    resolve_device_configuration,
)

COMPATIBILITY_IMPORTS = (
    "training_controller",
    "scripts.expert_task_queue",
    "scripts.device_agent",
)


def ensure_project_root_on_path() -> str:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("YGB_PROJECT_ROOT", root)
    return root


def _import_status(module_name: str) -> dict[str, Any]:
    try:
        importlib.import_module(module_name)
        return {"available": True, "error": ""}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def _recommended_commands() -> dict[str, str]:
    python_executable = sys.executable
    return {
        "setup": f"{python_executable} scripts/colab_setup.py",
        "dry_run_training": f"{python_executable} scripts/run_ybg_training_colab.py --dry-run",
        "queue_worker": f"{python_executable} scripts/device_agent.py --worker-id colab-worker --max-experts 1",
    }


def build_colab_setup_summary(
    preferred_device: str | None = None,
    *,
    validate_imports: bool = True,
    torch_module: Any | None | object = _AUTO_TORCH,
) -> dict[str, Any]:
    project_root = ensure_project_root_on_path()
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    device_configuration = resolve_device_configuration(
        preferred_device,
        torch_module=torch_module,
        configure_runtime=True,
    )

    compatibility_imports = (
        {module_name: _import_status(module_name) for module_name in COMPATIBILITY_IMPORTS}
        if validate_imports
        else {}
    )

    return {
        "project_root": project_root,
        "python_executable": sys.executable,
        "is_colab": bool(device_configuration.is_colab),
        "device": device_configuration.to_dict(),
        "environment": {
            "TOKENIZERS_PARALLELISM": os.getenv("TOKENIZERS_PARALLELISM", ""),
            "YGB_PROJECT_ROOT": os.getenv("YGB_PROJECT_ROOT", ""),
            "YGB_COLAB": os.getenv("YGB_COLAB", ""),
            "YGB_DEVICE_RESOLVED": os.getenv("YGB_DEVICE_RESOLVED", ""),
        },
        "compatibility_imports": compatibility_imports,
        "recommended_commands": _recommended_commands(),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a Colab-friendly runtime summary for YGB training scripts.",
    )
    parser.add_argument(
        "--device",
        default=os.getenv("YGB_DEVICE", "auto"),
        choices=("auto", "cuda", "mps", "cpu"),
        help="Preferred device selection for the Colab runtime.",
    )
    parser.add_argument(
        "--skip-import-checks",
        action="store_true",
        help="Skip repository compatibility import checks.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    summary = build_colab_setup_summary(
        args.device,
        validate_imports=not bool(args.skip_import_checks),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
