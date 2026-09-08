"""Protocol for safe, read-only channel diagnostics."""

from __future__ import annotations

from typing import Protocol

from ..models import ChannelReport


class ChannelAdapter(Protocol):
    id: str

    def inspect(self) -> ChannelReport:
        """Inspect channel health without logging in or modifying browser state."""
