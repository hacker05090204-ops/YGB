def test_request_sync_engine_stop_sets_stop_event(monkeypatch):
    from backend.sync import sync_engine as se

    original_event = se._SYNC_STOP_EVENT
    try:
        se._SYNC_STOP_EVENT.clear()
        se.request_sync_engine_stop()
        assert se._SYNC_STOP_EVENT.is_set() is True
    finally:
        se._SYNC_STOP_EVENT = original_event
