from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from ..config import AppConfig
from ..db import Database
from .exchange import CCXTExchangeClient
from .models import RouteQuote, TradeRequest, TradeResult
from .router import TradeRouter


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TradeService:
    def __init__(self, config: AppConfig, db: Database) -> None:
        self.config = config
        self.db = db
        self.router = TradeRouter(config=config, db=db)

    async def buy_symbol(
        self,
        symbol: str,
        quote_amount: float,
        *,
        preferred_exchange: str = "auto",
        dry_run: bool | None = None,
        reason: str = "manual_buy",
    ) -> TradeResult:
        request = TradeRequest(
            side="buy",
            base_symbol=symbol.upper(),
            quote_symbol=self.config.trading_default_quote,
            quote_amount=quote_amount,
            preferred_exchange=preferred_exchange,
            dry_run=dry_run,
            reason=reason,
        )
        return await self.execute(request)

    async def sell_symbol(
        self,
        symbol: str,
        base_amount: float,
        *,
        preferred_exchange: str = "auto",
        dry_run: bool | None = None,
        reason: str = "manual_sell",
    ) -> TradeResult:
        request = TradeRequest(
            side="sell",
            base_symbol=symbol.upper(),
            quote_symbol=self.config.trading_default_quote,
            base_amount=base_amount,
            preferred_exchange=preferred_exchange,
            dry_run=dry_run,
            reason=reason,
        )
        return await self.execute(request)

    async def execute(self, request: TradeRequest) -> TradeResult:
        request_id = uuid4().hex[:20]
        dry_run = self.config.trading_dry_run if request.dry_run is None else bool(request.dry_run)
        base_symbol = request.base_symbol.upper().strip()
        quote_symbol = request.quote_symbol.upper().strip()

        order_row_id = self.db.create_trade_order(
            {
                "request_id": request_id,
                "side": request.side,
                "base_symbol": base_symbol,
                "quote_symbol": quote_symbol,
                "requested_quote_amount": request.quote_amount,
                "requested_base_amount": request.base_amount,
                "exchange": (request.preferred_exchange or "auto").lower(),
                "status": "ROUTING",
                "reason": request.reason,
                "dry_run": int(dry_run),
            }
        )

        try:
            self._validate_request(request)
            route = await self.router.route(request)
            reference_price = route.buy_price if request.side == "buy" else route.sell_price
            if not reference_price or reference_price <= 0:
                raise RuntimeError("invalid route price")

            if dry_run:
                result = self._build_dry_run_result(request=request, route=route, reference_price=reference_price)
            else:
                result = await self._execute_live(request=request, route=route, reference_price=reference_price)

            self.db.update_trade_order(
                order_row_id,
                {
                    "exchange": result.exchange,
                    "market_symbol": result.market_symbol,
                    "status": result.status,
                    "order_id": result.order_id,
                    "filled_base_amount": result.filled_base_amount,
                    "filled_quote_amount": result.filled_quote_amount,
                    "average_price": result.average_price,
                    "raw_json": result.raw,
                },
            )
            return result
        except Exception as exc:
            message = str(exc)
            self.db.update_trade_order(
                order_row_id,
                {
                    "status": "FAILED",
                    "error_message": message[:500],
                },
            )
            return TradeResult(
                ok=False,
                status="FAILED",
                side=request.side,
                base_symbol=base_symbol,
                quote_symbol=quote_symbol,
                exchange=(request.preferred_exchange or "auto").lower(),
                market_symbol="",
                dry_run=dry_run,
                order_id=None,
                requested_quote_amount=request.quote_amount,
                requested_base_amount=request.base_amount,
                filled_base_amount=None,
                filled_quote_amount=None,
                average_price=None,
                message=message,
                raw={},
            )

    def _validate_request(self, request: TradeRequest) -> None:
        if not self.config.trading_enabled:
            raise RuntimeError("trading is disabled")

        symbol = request.base_symbol.upper()
        if self.config.trading_allowed_symbols and symbol not in self.config.trading_allowed_symbols:
            raise RuntimeError(f"symbol not in allowlist: {symbol}")
        if self.config.trading_blocked_symbols and symbol in self.config.trading_blocked_symbols:
            raise RuntimeError(f"symbol blocked: {symbol}")

        if request.side == "buy":
            if request.quote_amount is None or request.quote_amount <= 0:
                raise RuntimeError("buy quote amount must be positive")
            if request.quote_amount > self.config.trading_max_order_usdt:
                raise RuntimeError(
                    f"buy quote amount exceeds TRADING_MAX_ORDER_USDT={self.config.trading_max_order_usdt}"
                )
        else:
            if request.base_amount is None or request.base_amount <= 0:
                raise RuntimeError("sell base amount must be positive")

    def _build_dry_run_result(
        self,
        request: TradeRequest,
        route: RouteQuote,
        reference_price: float,
    ) -> TradeResult:
        requested_quote = request.quote_amount
        requested_base = request.base_amount
        if request.side == "buy" and requested_quote is not None:
            requested_base = requested_quote / reference_price
        elif request.side == "sell" and requested_base is not None:
            requested_quote = requested_base * reference_price

        return TradeResult(
            ok=True,
            status="DRY_RUN",
            side=request.side,
            base_symbol=request.base_symbol.upper(),
            quote_symbol=request.quote_symbol.upper(),
            exchange=route.exchange,
            market_symbol=route.market_symbol,
            dry_run=True,
            order_id=None,
            requested_quote_amount=request.quote_amount,
            requested_base_amount=request.base_amount,
            filled_base_amount=requested_base,
            filled_quote_amount=requested_quote,
            average_price=reference_price,
            message="dry run only, no live order submitted",
            raw={
                "route": {
                    "exchange": route.exchange,
                    "market_symbol": route.market_symbol,
                    "bid": route.bid,
                    "ask": route.ask,
                    "last": route.last,
                    "quote_volume": route.quote_volume,
                }
            },
        )

    async def _execute_live(
        self,
        request: TradeRequest,
        route: RouteQuote,
        reference_price: float,
    ) -> TradeResult:
        client = CCXTExchangeClient(exchange_name=route.exchange, config=self.config)
        try:
            if request.side == "buy":
                order = await asyncio.to_thread(
                    client.create_market_buy_by_quote,
                    route.market_symbol,
                    float(request.quote_amount or 0),
                    reference_price,
                    self.config.trading_max_slippage_bps,
                )
            else:
                order = await asyncio.to_thread(
                    client.create_market_sell,
                    route.market_symbol,
                    float(request.base_amount or 0),
                )
        finally:
            client.close()

        filled_base = _to_float(order.get("filled"))
        filled_quote = _to_float(order.get("cost"))
        average_price = _to_float(order.get("average"))
        if average_price is None and filled_base and filled_quote:
            average_price = filled_quote / filled_base

        status = str(order.get("status") or "submitted").upper()
        return TradeResult(
            ok=True,
            status=status,
            side=request.side,
            base_symbol=request.base_symbol.upper(),
            quote_symbol=request.quote_symbol.upper(),
            exchange=route.exchange,
            market_symbol=route.market_symbol,
            dry_run=False,
            order_id=str(order.get("id") or ""),
            requested_quote_amount=request.quote_amount,
            requested_base_amount=request.base_amount,
            filled_base_amount=filled_base,
            filled_quote_amount=filled_quote,
            average_price=average_price,
            message="live order submitted",
            raw=order,
        )
