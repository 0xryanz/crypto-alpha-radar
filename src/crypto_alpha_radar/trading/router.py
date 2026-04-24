from __future__ import annotations

import asyncio

from ..config import AppConfig
from ..db import Database
from .exchange import CCXTExchangeClient
from .models import RouteQuote, TradeRequest


class TradeRouter:
    def __init__(self, config: AppConfig, db: Database) -> None:
        self.config = config
        self.db = db

    async def route(self, request: TradeRequest) -> RouteQuote:
        exchanges = self._pick_exchanges(request.preferred_exchange)
        quotes: list[RouteQuote] = []
        errors: list[str] = []

        for exchange in exchanges:
            try:
                quote = await self._quote_exchange(exchange, request.base_symbol, request.quote_symbol)
                quotes.append(quote)
            except Exception as exc:
                errors.append(f"{exchange}:{exc}")

        if not quotes:
            error_text = "; ".join(errors) if errors else "no routes"
            raise RuntimeError(f"unable to route {request.base_symbol}/{request.quote_symbol}: {error_text}")

        if request.side == "buy":
            ranked = sorted(
                quotes,
                key=lambda item: (
                    item.buy_price if item.buy_price is not None else float("inf"),
                    -(item.quote_volume or 0),
                ),
            )
            return ranked[0]

        ranked = sorted(
            quotes,
            key=lambda item: (
                -(item.sell_price if item.sell_price is not None else 0),
                -(item.quote_volume or 0),
            ),
        )
        return ranked[0]

    def _pick_exchanges(self, preferred_exchange: str | None) -> tuple[str, ...]:
        preferred = (preferred_exchange or "").strip().lower()
        if preferred and preferred != "auto":
            return (preferred,)

        configured = self.config.trading_exchanges or ("binance",)
        return tuple(exchange.strip().lower() for exchange in configured if exchange.strip())

    async def _quote_exchange(self, exchange: str, base_symbol: str, quote_symbol: str) -> RouteQuote:
        client = CCXTExchangeClient(exchange_name=exchange, config=self.config)
        try:
            market_symbol = await self._resolve_market_symbol(client, exchange, base_symbol, quote_symbol)
            ticker = await asyncio.to_thread(client.fetch_ticker, market_symbol)
            return RouteQuote(
                exchange=exchange,
                market_symbol=market_symbol,
                bid=ticker.get("bid"),
                ask=ticker.get("ask"),
                last=ticker.get("last"),
                quote_volume=ticker.get("quoteVolume"),
            )
        finally:
            client.close()

    async def _resolve_market_symbol(
        self,
        client: CCXTExchangeClient,
        exchange: str,
        base_symbol: str,
        quote_symbol: str,
    ) -> str:
        cached = self.db.get_market_mapping(base_symbol=base_symbol, quote_symbol=quote_symbol, exchange=exchange)
        if cached and cached.get("market_symbol"):
            return str(cached["market_symbol"])

        candidates = await asyncio.to_thread(client.find_spot_markets, base_symbol, quote_symbol)
        if not candidates:
            raise RuntimeError("market not found")
        if len(candidates) > 1:
            joined = ",".join(candidates[:5])
            raise RuntimeError(f"ambiguous markets: {joined}")

        market_symbol = candidates[0]
        self.db.upsert_market_mapping(
            {
                "base_symbol": base_symbol.upper(),
                "quote_symbol": quote_symbol.upper(),
                "exchange": exchange,
                "market_symbol": market_symbol,
            }
        )
        return market_symbol
