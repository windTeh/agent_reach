"""Minimal protocol for future backend adapters."""

from __future__ import annotations

from typing import Protocol

from ..models import BackendReport


class BackendAdapter(Protocol):
    """A pluggable backend that can provide a diagnostic report."""

    id: str

    def inspect(self) -> BackendReport:
        """Return only non-destructive availability information."""
