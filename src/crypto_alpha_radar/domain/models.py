from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SourceSignal:
    source_type: str
    external_id: str
    text: str
    account: str | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OpportunityCandidate:
    symbol: str
    source: str
    raw_text: str
    name: str | None = None
    launch_time: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
