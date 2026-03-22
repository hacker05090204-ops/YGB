from pathlib import Path


def test_phase36_has_no_forbidden_imports():
    phase_root = Path("impl_v1/phase36")
    forbidden_markers = ("subprocess", "os.system", "requests", "phase37", "phase48")
    for path in phase_root.rglob("*.py"):
        if path.name == "test_forbidden_imports.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert not any(marker in text for marker in forbidden_markers), path
