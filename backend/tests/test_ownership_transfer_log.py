import pytest

from backend.auth import ownership


@pytest.fixture(autouse=True)
def _reset_transfer_log(monkeypatch):
    monkeypatch.setattr(ownership, "_transfer_log", ownership.OwnershipTransferLog())


def test_transfer_resource_ownership_logs_successful_transfer():
    resource = {"id": "resource-1", "owner_id": "owner-1"}
    caller = {"sub": "owner-1", "role": "user"}

    updated = ownership.transfer_resource_ownership(resource, "owner-2", caller, resource_id="resource-1")
    history = ownership.get_transfer_history("resource-1")

    assert updated["owner_id"] == "owner-2"
    assert len(history) == 1
    assert history[0].resource_id == "resource-1"
    assert history[0].from_owner == "owner-1"
    assert history[0].to_owner == "owner-2"
    assert history[0].authorized_by == "owner-1"


def test_transfer_resource_ownership_rejects_unauthorized_caller():
    resource = {"id": "resource-2", "owner_id": "owner-1"}
    caller = {"sub": "user-2", "role": "user"}

    with pytest.raises(ownership.OwnershipTransferDenied) as exc:
        ownership.transfer_resource_ownership(resource, "owner-2", caller, resource_id="resource-2")

    assert exc.value.reason == "transfer_not_authorized"
    assert resource["owner_id"] == "owner-1"
    assert ownership.get_transfer_history("resource-2") == []


def test_get_transfer_history_filters_by_resource_id():
    owner_caller = {"sub": "owner-1", "role": "user"}
    admin_caller = {"sub": "admin-1", "role": "admin"}
    first_resource = {"id": "resource-1", "owner_id": "owner-1"}
    second_resource = {"id": "resource-2", "owner_id": "owner-2"}

    ownership.transfer_resource_ownership(first_resource, "owner-3", owner_caller, resource_id="resource-1")
    ownership.transfer_resource_ownership(second_resource, "owner-4", admin_caller, resource_id="resource-2")

    first_history = ownership.get_transfer_history("resource-1")
    second_history = ownership.get_transfer_history("resource-2")

    assert len(first_history) == 1
    assert len(second_history) == 1
    assert first_history[0].resource_id == "resource-1"
    assert second_history[0].resource_id == "resource-2"

