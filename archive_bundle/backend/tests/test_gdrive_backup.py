from pathlib import Path


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
    assert any("--include" in arg for arg in calls[0])
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
