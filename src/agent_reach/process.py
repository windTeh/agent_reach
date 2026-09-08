"""Safe subprocess wrapper for project-managed tools."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .paths import RuntimePaths


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


def run_project_process(
    command: Sequence[str], paths: RuntimePaths, *, timeout: float = 15.0
) -> ProcessResult:
    """Run an argument vector without a shell and with project-local homes."""
    completed = subprocess.run(
        list(command),
        cwd=paths.project_root,
        env=paths.child_environment(),
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)
