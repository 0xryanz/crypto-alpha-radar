from __future__ import annotations

import json
import logging
from datetime import datetime

from .analyzers import OpportunityAnalyzer
from .db import Database
from .domain import SourceSignal
from .timeutils import utc_now_naive

logger = logging.getLogger("alpha.pipeline")


class SignalIngestionPipeline:
    def __init__(self, db: Database, analyzer: OpportunityAnalyzer) -> None:
        self.db = db
        self.analyzer = analyzer

    async def process_signal(self, signal: SourceSignal) -> bool:
        event_created = self.db.save_source_event(
            source_type=signal.source_type,
            external_id=signal.external_id,
            account=signal.account,
            text=signal.text,
            created_at=signal.created_at.isoformat() if signal.created_at else None,
            raw_json=json.dumps(signal.metadata, ensure_ascii=False),
        )
        if not event_created:
            return False

        candidate = await self.analyzer.analyze(signal)
        if candidate is None:
            return False

        reference_date = self._pick_reference_date(candidate.launch_time, signal.created_at)
        project_id = self.db.make_project_id(candidate.symbol, reference_date)
        if self.db.project_exists(project_id):
            return False

        project = {
            "id": project_id,
            "symbol": candidate.symbol,
            "name": candidate.name,
            "launch_time": candidate.launch_time,
            "source": candidate.source,
            "raw_text": candidate.raw_text,
            "tier": "PENDING",
            "vcs": [],
            "is_darling": False,
            "excluded": 0,
        }
        self.db.save_project(project)
        logger.info("candidate project created from %s: $%s", candidate.source, candidate.symbol)
        return True

    @staticmethod
    def _pick_reference_date(launch_time: str | None, created_at: datetime | None) -> str:
        if launch_time:
            return launch_time[:10]
        if created_at:
            return created_at.date().isoformat()
        return utc_now_naive().date().isoformat()
