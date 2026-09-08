from __future__ import annotations

from agent_reach import __version__
from agent_reach.cli import main


def test_version_command(capsys):
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_skill_dry_run_json(project_root, capsys):
    assert main(["skill", "--install", "--dry-run", "--json"]) == 0
    assert '"status": "planned"' in capsys.readouterr().out
