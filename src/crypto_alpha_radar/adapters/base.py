from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain import SourceSignal


class SourceAdapter(ABC):
    source_type: str
    poll_interval_seconds: int

    @abstractmethod
    async def fetch_signals(self) -> list[SourceSignal]:
        raise NotImplementedError
