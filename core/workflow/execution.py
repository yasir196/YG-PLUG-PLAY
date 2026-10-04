"""Helpers for capability execution metadata."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class CapabilityExecution:
    outputs: dict[str, Any]
    provider_plugin_id: str | None = None
    model: str | None = None
    options: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
