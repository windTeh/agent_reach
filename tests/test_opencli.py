from __future__ import annotations

from agent_reach.channels.opencli import OpenCLIChannel
from agent_reach.models import HealthStatus


def test_opencli_does_not_assume_browser_access(paths):
    report = OpenCLIChannel(paths).inspect()
    by_id = {check.id: check for check in report.checks}
    assert by_id["browser_extension"].status == HealthStatus.MANUAL_ACTION_REQUIRED
    assert by_id["browser_login"].status == HealthStatus.MANUAL_ACTION_REQUIRED
    assert "Cookie" in " ".join(by_id["browser_extension"].fix.instructions)
