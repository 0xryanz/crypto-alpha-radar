from __future__ import annotations

import logging
import re

from ..config import AppConfig
from ..constants import (
    TWITTER_EXCLUDE_KEYWORDS,
    TWITTER_OPPORTUNITY_KEYWORDS,
    TWITTER_STOP_SYMBOLS,
)
from ..domain import OpportunityCandidate, SourceSignal
from ..integrations import llm_extract_tweet

logger = logging.getLogger("alpha.analyzers.opportunity")


class OpportunityAnalyzer:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    async def analyze(self, signal: SourceSignal) -> OpportunityCandidate | None:
        if signal.source_type == "binance":
            return self._analyze_binance_signal(signal)
        if signal.source_type == "twitter":
            return await self._analyze_twitter_signal(signal)
        return None

    def _analyze_binance_signal(self, signal: SourceSignal) -> OpportunityCandidate | None:
        symbol = str(signal.metadata.get("symbol") or "").strip().upper()
        if not symbol:
            return None

        return OpportunityCandidate(
            symbol=symbol,
            name=signal.metadata.get("name"),
            launch_time=signal.metadata.get("launch_time"),
            source="binance_announcement",
            raw_text=signal.text,
            metadata={"origin": "binance"},
        )

    async def _analyze_twitter_signal(self, signal: SourceSignal) -> OpportunityCandidate | None:
        text = signal.text.strip()
        text_lower = text.lower()

        if any(keyword in text_lower for keyword in TWITTER_EXCLUDE_KEYWORDS):
            return None

        candidate_symbols = self._extract_candidate_symbols(text)
        if not candidate_symbols:
            return None

        analysis = await llm_extract_tweet(
            text=text,
            account=signal.account or "",
            candidate_symbols=candidate_symbols,
            config=self.config,
        )

        is_opportunity = bool(analysis.get("is_opportunity", False))
        if not is_opportunity:
            return None

        confidence = float(analysis.get("confidence", 0.0) or 0.0)
        if confidence < self.config.twitter_min_confidence:
            return None

        symbol = str(analysis.get("symbol") or "").upper().strip()
        if not symbol and candidate_symbols:
            symbol = candidate_symbols[0]
        if not symbol:
            return None

        metadata = {
            "origin": "twitter",
            "confidence": confidence,
            "reason": analysis.get("reason", ""),
            "tweet_url": signal.metadata.get("url"),
            "candidate_symbols": candidate_symbols,
        }

        account = signal.account or "unknown"
        raw_text = text
        if signal.metadata.get("url"):
            raw_text = f"{text}\n\n来源: {signal.metadata['url']}"

        return OpportunityCandidate(
            symbol=symbol,
            name=analysis.get("name"),
            launch_time=analysis.get("launch_time"),
            source=f"twitter:{account}",
            raw_text=raw_text,
            metadata=metadata,
        )

    @staticmethod
    def _extract_candidate_symbols(text: str) -> list[str]:
        cashtags = re.findall(r"\$([A-Za-z0-9]{2,10})", text)
        tickers = re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", text)
        merged = cashtags + tickers

        ordered: list[str] = []
        seen = set()
        for item in merged:
            symbol = item.upper()
            if symbol in TWITTER_STOP_SYMBOLS:
                continue
            if symbol in seen:
                continue
            seen.add(symbol)
            ordered.append(symbol)

        if ordered:
            return ordered[:5]

        lowered = text.lower()
        if any(keyword in lowered for keyword in TWITTER_OPPORTUNITY_KEYWORDS):
            logger.debug("tweet has opportunity keywords but no symbol extracted")

        return []
