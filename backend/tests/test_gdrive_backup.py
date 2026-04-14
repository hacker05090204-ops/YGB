from pathlib import Path
import json


def test_upload_with_rclone_moves_payload_and_sidecar(monkeypatch, tmp_path):
    from backend.sync import gdrive_backup as gb

    staging_dir = tmp_path / "staging"
    pending_dir = staging_dir / "pending"
    uploaded_dir = staging_dir / "uploaded"
    pending_dir.mkdir(parents=True, exist_ok=True)
    uploaded_dir.mkdir(parents=True, exist_ok=True)

    payload = pending_dir / "models__checkpoint.bin.enc"
    payload.write_bytes(b"encrypted")
    sidecar = pending_dir / "models__checkpoint.bin.meta.json"
    sidecar.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(gb, "STAGING_DIR", staging_dir)
    monkeypatch.setattr(gb, "PENDING_DIR", pending_dir)
    monkeypatch.setattr(gb, "UPLOADED_DIR", uploaded_dir)
    monkeypatch.setattr(gb, "_rclone_available", lambda: True)

    calls = []

    class _Result:
        returncode = 0
        stderr = ""

    def _run(cmd, capture_output=True, text=True, timeout=600):
        calls.append(cmd)
        return _Result()

    monkeypatch.setattr("subprocess.run", _run)

    assert gb._upload_with_rclone() is True
    assert calls
    assert any(any("--include" in arg for arg in call) for call in calls)
    assert not payload.exists()
    assert not sidecar.exists()
    assert (uploaded_dir / payload.name).exists()
    assert (uploaded_dir / sidecar.name).exists()


def test_get_gdrive_status_reports_client_selection(monkeypatch, tmp_path):
    from backend.sync import gdrive_backup as gb

    staging_dir = tmp_path / "staging"
    pending_dir = staging_dir / "pending"
    uploaded_dir = staging_dir / "uploaded"
    pending_dir.mkdir(parents=True, exist_ok=True)
    uploaded_dir.mkdir(parents=True, exist_ok=True)
    (pending_dir / "manifest.json.enc").write_bytes(b"manifest")
    (uploaded_dir / "done.enc").write_bytes(b"done")

    creds_path = tmp_path / "service_account.json"
    creds_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(gb, "STAGING_DIR", staging_dir)
    monkeypatch.setattr(gb, "PENDING_DIR", pending_dir)
    monkeypatch.setattr(gb, "UPLOADED_DIR", uploaded_dir)
    monkeypatch.setattr(gb, "GDRIVE_CREDS_PATH", str(creds_path))
    monkeypatch.setattr(gb, "_sdk_available", lambda: True)
    monkeypatch.setattr(gb, "_rclone_available", lambda: False)

    status = gb.get_gdrive_status()

    assert status["pending_files"] == 1
    assert status["uploaded_files"] == 1
    assert status["sdk_available"] is True
    assert status["rclone_available"] is False
    assert status["active_client"] == "sdk"


def test_stage_file_for_upload_records_hash_identity(monkeypatch, tmp_path):
    from backend.sync import gdrive_backup as gb

    staging_dir = tmp_path / "staging"
    pending_dir = staging_dir / "pending"
    uploaded_dir = staging_dir / "uploaded"
    pending_dir.mkdir(parents=True, exist_ok=True)
    uploaded_dir.mkdir(parents=True, exist_ok=True)

    source = tmp_path / "manifest.json"
    source.write_bytes(b'{"ok": true}')

    monkeypatch.setattr(gb, "STAGING_DIR", staging_dir)
    monkeypatch.setattr(gb, "PENDING_DIR", pending_dir)
    monkeypatch.setattr(gb, "UPLOADED_DIR", uploaded_dir)
    monkeypatch.setattr(gb, "ENCRYPTION_KEY", "")

    staged = gb.stage_file_for_upload(source, "configs/manifest.json", compress=False, encrypt=False)

    assert staged is not None
    sidecar = pending_dir / f"{staged.stem}.meta.json"
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta["original_path"] == "configs/manifest.json"
    assert meta["original_sha256"] == gb._sha256_bytes(source.read_bytes())
    assert meta["sync_identity"] == gb._build_sync_identity(
        "configs/manifest.json",
        meta["original_sha256"],
    )
    assert meta["staged_sha256"] == gb._sha256_bytes(staged.read_bytes())


def test_restore_staged_backup_file_verifies_hashes(monkeypatch, tmp_path):
    from backend.sync import gdrive_backup as gb

    staging_dir = tmp_path / "staging"
    pending_dir = staging_dir / "pending"
    uploaded_dir = staging_dir / "uploaded"
    pending_dir.mkdir(parents=True, exist_ok=True)
    uploaded_dir.mkdir(parents=True, exist_ok=True)

    source = tmp_path / "weights.bin"
    payload = b"model-weights"
    source.write_bytes(payload)

    monkeypatch.setattr(gb, "STAGING_DIR", staging_dir)
    monkeypatch.setattr(gb, "PENDING_DIR", pending_dir)
    monkeypatch.setattr(gb, "UPLOADED_DIR", uploaded_dir)
    monkeypatch.setattr(gb, "ENCRYPTION_KEY", "")

    staged = gb.stage_file_for_upload(source, "models/weights.bin", compress=False, encrypt=False)
    restored, meta = gb.restore_staged_backup_file(staged)

    assert restored == payload
    assert meta["original_sha256"] == gb._sha256_bytes(payload)
