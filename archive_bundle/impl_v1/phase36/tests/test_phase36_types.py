from impl_v1.phase36.phase36_types import SandboxBoundaryType, SandboxCapability, SandboxDecision


def test_phase36_types_are_closed_enums():
    assert [member.name for member in SandboxBoundaryType] == ["PROCESS", "CONTAINER", "VM", "UNKNOWN"]
    assert [member.name for member in SandboxCapability] == ["READ_ONLY", "WRITE_ALLOWED", "EXEC_ALLOWED", "NONE"]
    assert [member.name for member in SandboxDecision] == ["ALLOW", "DENY", "ESCALATE"]
