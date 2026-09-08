"""Domain errors and stable process exit codes."""

from __future__ import annotations


class AgentReachError(Exception):
    """Base class for expected CLI failures."""


class PathBoundaryError(AgentReachError):
    """Raised when a requested path escapes the project root."""


class NetworkError(AgentReachError):
    """Raised for controlled update-check network failures."""


class ConfigurationError(AgentReachError):
    """Raised when project-local configuration is invalid."""
