from __future__ import annotations

from agent_reach.update import check_for_updates


def test_offline_update_without_cache_does_not_write(paths):
    result = check_for_updates(paths, offline=True)
    assert result.available_version is None
    assert "离线" in result.message
    assert not paths.runtime_root.exists()


def test_update_result_uses_cache_in_offline_mode(paths):
    paths.ensure_directories()
    (paths.state_dir / "update-check.json").write_text(
        '{"current_version":"0.1.0","available_version":"0.2.0","update_available":true,"source":"test","checked_at":"now","message":"old"}',
        encoding="utf-8",
    )
    result = check_for_updates(paths, offline=True)
    assert result.available_version == "0.2.0"
    assert result.update_available is True
