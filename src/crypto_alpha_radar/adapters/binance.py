from __future__ import annotations

from datetime import datetime

from ..config import AppConfig
from ..domain import SourceSignal
from ..integrations import fetch_announcements
from ..parsing import extract_name, extract_symbol, is_trigger
from ..timeutils import utc_now_naive
from .base import SourceAdapter


class BinanceAnnouncementAdapter(SourceAdapter):
    source_type = "binance"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.poll_interval_seconds = config.announcement_poll_interval

    async def fetch_signals(self) -> list[SourceSignal]:
        articles = await fetch_announcements(self.config)
        signals: list[SourceSignal] = []

        for article in articles:
            title = article.get("title", "")
            triggered, _ = is_trigger(title)
            if not triggered:
                continue

            symbol = extract_symbol(title)
            if not symbol:
                continue

            release_ts = article.get("releaseDate")
            created_at = (
                datetime.fromtimestamp(release_ts / 1000)
                if isinstance(release_ts, (int, float)) and release_ts
                else utc_now_naive()
            )

            external_id = str(article.get("code") or f"{symbol}-{created_at.isoformat()}")
            signals.append(
                SourceSignal(
                    source_type=self.source_type,
                    external_id=external_id,
                    text=title,
                    created_at=created_at,
                    metadata={
                        "symbol": symbol,
                        "name": extract_name(title),
                        "launch_time": created_at.isoformat(),
                        "article_code": article.get("code"),
                        "catalog_id": article.get("_catalog_id"),
                    },
                )
            )

        return signals
