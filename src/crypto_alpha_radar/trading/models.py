from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TradeSide = Literal["buy", "sell"]


@dataclass(slots=True)
class TradeRequest:
    side: TradeSide
    base_symbol: str
    quote_symbol: str
    quote_amount: float | None = None
    base_amount: float | None = None
    preferred_exchange: str | None = None
    dry_run: bool | None = None
    reason: str = "manual"


@dataclass(slots=True)
class RouteQuote:
    exchange: str
    market_symbol: str
    bid: float | None
    ask: float | None
    last: float | None
    quote_volume: float | None

    @property
    def buy_price(self) -> float | None:
        return self.ask or self.last

    @property
    def sell_price(self) -> float | None:
        return self.bid or self.last


@dataclass(slots=True)
class TradeResult:
    ok: bool
    status: str
    side: TradeSide
    base_symbol: str
    quote_symbol: str
    exchange: str
    market_symbol: str
    dry_run: bool
    order_id: str | None
    requested_quote_amount: float | None
    requested_base_amount: float | None
    filled_base_amount: float | None
    filled_quote_amount: float | None
    average_price: float | None
    message: str
    raw: dict[str, Any]
