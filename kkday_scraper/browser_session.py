"""Compatibility import for the ego-browser-only session runtime."""

from .ego_browser import (
    BrowserSession,
    EgoBrowserBridge,
    EgoBrowserError as SessionUnavailableError,
    PROBE_SCRIPT,
    build_agent_handoff,
    classify_probe,
    default_task_space,
)

__all__ = [
    "BrowserSession",
    "EgoBrowserBridge",
    "SessionUnavailableError",
    "PROBE_SCRIPT",
    "build_agent_handoff",
    "classify_probe",
    "default_task_space",
]
