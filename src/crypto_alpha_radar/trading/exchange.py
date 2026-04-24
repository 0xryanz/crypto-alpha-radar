from __future__ import annotations

from typing import Any

from ..config import AppConfig


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class CCXTExchangeClient:
    def __init__(self, exchange_name: str, config: AppConfig) -> None:
        self.exchange_name = exchange_name.strip().lower()
        self.config = config
        self._exchange = self._create_exchange()
        self._markets_loaded = False

    def _create_exchange(self):
        try:
            import ccxt  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency runtime
            raise RuntimeError("ccxt is not installed") from exc

        exchange_cls = getattr(ccxt, self.exchange_name, None)
        if exchange_cls is None:
            raise ValueError(f"exchange not supported by ccxt: {self.exchange_name}")

        credentials = self.config.exchange_credentials(self.exchange_name)
        params: dict[str, Any] = {
            "enableRateLimit": True,
            "timeout": max(3000, int(self.config.request_timeout_seconds * 1000)),
        }
        if credentials.get("apiKey") and credentials.get("secret"):
            params["apiKey"] = credentials["apiKey"]
            params["secret"] = credentials["secret"]
        if credentials.get("password"):
            params["password"] = credentials["password"]

        return exchange_cls(params)

    def close(self) -> None:
        close_fn = getattr(self._exchange, "close", None)
        if callable(close_fn):
            close_fn()

    def load_markets(self) -> None:
        if self._markets_loaded:
            return
        self._exchange.load_markets()
        self._markets_loaded = True

    def find_spot_markets(self, base_symbol: str, quote_symbol: str) -> list[str]:
        self.load_markets()
        base = base_symbol.upper()
        quote = quote_symbol.upper()

        candidates: list[str] = []
        for market in self._exchange.markets.values():
            if not market:
                continue
            if bool(market.get("active")) is False:
                continue

            market_base = str(market.get("base") or "").upper()
            market_quote = str(market.get("quote") or "").upper()
            if market_base != base or market_quote != quote:
                continue

            if market.get("swap") or market.get("future") or market.get("option"):
                continue

            symbol = str(market.get("symbol") or "").strip()
            if not symbol:
                continue
            if ":" in symbol:
                continue
            candidates.append(symbol)

        unique = sorted(set(candidates))
        if len(unique) <= 1:
            return unique

        exact = [item for item in unique if item.upper() == f"{base}/{quote}"]
        return exact or unique

    def fetch_ticker(self, market_symbol: str) -> dict[str, float | None]:
        ticker = self._exchange.fetch_ticker(market_symbol)
        return {
            "bid": _to_float(ticker.get("bid")),
            "ask": _to_float(ticker.get("ask")),
            "last": _to_float(ticker.get("last")),
            "quoteVolume": _to_float(ticker.get("quoteVolume")),
        }

    def create_market_buy_by_quote(
        self,
        market_symbol: str,
        quote_amount: float,
        reference_price: float,
        slippage_bps: int,
    ) -> dict[str, Any]:
        if quote_amount <= 0:
            raise ValueError("quote amount must be positive")
        if reference_price <= 0:
            raise ValueError("invalid reference price")

        slippage = max(0.0, min(slippage_bps / 10000.0, 0.5))
        base_amount = (quote_amount / reference_price) * (1 - slippage)
        if base_amount <= 0:
            raise ValueError("calculated buy amount is invalid")

        create_cost_fn = getattr(self._exchange, "create_market_buy_order_with_cost", None)
        if callable(create_cost_fn):
            return create_cost_fn(market_symbol, quote_amount)

        options = getattr(self._exchange, "options", {}) or {}
        requires_price = bool(options.get("createMarketBuyOrderRequiresPrice"))
        if requires_price:
            return self._exchange.create_order(market_symbol, "market", "buy", base_amount, reference_price)

        return self._exchange.create_market_buy_order(market_symbol, base_amount)

    def create_market_sell(self, market_symbol: str, base_amount: float) -> dict[str, Any]:
        if base_amount <= 0:
            raise ValueError("base amount must be positive")
        return self._exchange.create_market_sell_order(market_symbol, base_amount)
