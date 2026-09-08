from __future__ import annotations

from agent_reach.installer import install_opencli


def test_install_maps_system_to_project_managed(paths):
    result = install_opencli(paths, system=True, dry_run=True)
    assert result.status == "manual_action_required"
    assert str(paths.project_root / "tools" / "bin") == result.target
    assert any("全局" in action for action in result.actions)


def test_skill_dry_run_does_not_create_files(paths):
    from agent_reach.skill import install_managed_skill

    result = install_managed_skill(paths, dry_run=True)
    assert result.status == "planned"
    assert not (paths.project_root / "tools" / "skills").exists()
