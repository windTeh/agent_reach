from __future__ import annotations

import json

from agent_reach.cli import main


def test_doctor_json_is_structured(project_root, capsys):
    result = main(["doctor", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert result == 0
    assert payload["active_backend"]["id"] is None
    assert payload["channels"][0]["id"] == "opencli"
    checks = payload["channels"][0]["checks"]
    assert all(check.get("fix") for check in checks if check["status"] != "ok")
    assert "\x1b" not in captured.out


def test_doctor_never_creates_runtime_on_read_only_check(project_root, capsys):
    main(["doctor", "--json"])
    assert not (project_root / "runtime").exists()
