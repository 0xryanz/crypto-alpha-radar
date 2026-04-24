from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import asdict, replace

from .adapters import TwitterTimelineAdapter
from .config import AppConfig
from .db import Database
from .formatters import format_trade_result
from .integrations import send_tg
from .llm_client import llm_healthcheck
from .logging_setup import setup_logging
from .service import AlphaMonitorService
from .trading import TradeService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-radar",
        description="Multi-source crypto opportunity monitor and Telegram notifier",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path to env file (.env or .env.systemd). Default: auto-detect in current dir",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override log level from config",
    )

    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run all monitor workers")
    run_parser.add_argument(
        "--no-startup-message",
        action="store_true",
        help="Do not send Telegram startup message",
    )

    subparsers.add_parser("init-db", help="Create or migrate local SQLite tables")

    test_tg_parser = subparsers.add_parser("test-tg", help="Send a Telegram test message")
    test_tg_parser.add_argument(
        "--message",
        default="✅ <b>Crypto Alpha Radar test</b>\nTelegram configuration is valid.",
        help="Custom HTML message body",
    )
    test_tg_parser.add_argument(
        "--silent",
        action="store_true",
        help="Send as a silent notification",
    )

    subparsers.add_parser("check-twitter", help="Fetch once from configured Twitter accounts")
    subparsers.add_parser("check-llm", help="Check configured LLM provider connectivity")

    trade_buy = subparsers.add_parser("trade-buy", help="Place market buy using quote amount")
    trade_buy.add_argument("--symbol", required=True, help="Token symbol, e.g. FOO")
    trade_buy.add_argument("--usdt", required=True, type=float, help="Quote amount in USDT")
    trade_buy.add_argument("--exchange", default="auto", help="Exchange name or auto")
    trade_buy.add_argument("--live", action="store_true", help="Send real order (override dry-run)")
    trade_buy.add_argument("--reason", default="manual_buy", help="Order reason tag")

    trade_sell = subparsers.add_parser("trade-sell", help="Place market sell using base amount")
    trade_sell.add_argument("--symbol", required=True, help="Token symbol, e.g. FOO")
    trade_sell.add_argument("--amount", required=True, type=float, help="Base amount to sell")
    trade_sell.add_argument("--exchange", default="auto", help="Exchange name or auto")
    trade_sell.add_argument("--live", action="store_true", help="Send real order (override dry-run)")
    trade_sell.add_argument("--reason", default="manual_sell", help="Order reason tag")

    trade_orders = subparsers.add_parser("trade-orders", help="List recent trade orders")
    trade_orders.add_argument("--limit", default=20, type=int, help="Number of rows")

    return parser


async def _run(config: AppConfig, send_startup_message: bool) -> int:
    service = AlphaMonitorService(config=config, db=Database(config.db_path))
    await service.run(send_startup_message=send_startup_message)
    return 0


async def _test_tg(config: AppConfig, message: str, silent: bool) -> int:
    ok = await send_tg(message, config=config, silent=silent)
    return 0 if ok else 1


async def _check_twitter(config: AppConfig) -> int:
    adapter = TwitterTimelineAdapter(config=config)
    signals = await adapter.fetch_signals()

    logger = logging.getLogger("alpha.cli")
    logger.info("twitter accounts=%s", ",".join(config.twitter_accounts) if config.twitter_accounts else "")
    logger.info("fetched %s tweet signal(s)", len(signals))
    for signal in signals[:5]:
        logger.info("@%s tweet=%s text=%s", signal.account, signal.external_id, signal.text[:120])
    return 0


async def _check_llm(config: AppConfig) -> int:
    logger = logging.getLogger("alpha.cli")
    ok, message = await llm_healthcheck(config)
    if ok:
        logger.info(message)
        return 0
    logger.error(message)
    return 1


async def _trade_buy(config: AppConfig, symbol: str, usdt: float, exchange: str, live: bool, reason: str) -> int:
    db = Database(config.db_path)
    db.init_db()
    service = TradeService(config=config, db=db)
    result = await service.buy_symbol(
        symbol=symbol,
        quote_amount=usdt,
        preferred_exchange=exchange,
        dry_run=(not live),
        reason=reason,
    )
    logger = logging.getLogger("alpha.cli")
    logger.info("%s", format_trade_result(asdict(result)))
    return 0 if result.ok else 1


async def _trade_sell(
    config: AppConfig,
    symbol: str,
    amount: float,
    exchange: str,
    live: bool,
    reason: str,
) -> int:
    db = Database(config.db_path)
    db.init_db()
    service = TradeService(config=config, db=db)
    result = await service.sell_symbol(
        symbol=symbol,
        base_amount=amount,
        preferred_exchange=exchange,
        dry_run=(not live),
        reason=reason,
    )
    logger = logging.getLogger("alpha.cli")
    logger.info("%s", format_trade_result(asdict(result)))
    return 0 if result.ok else 1


def _trade_orders(config: AppConfig, limit: int) -> int:
    logger = logging.getLogger("alpha.cli")
    db = Database(config.db_path)
    db.init_db()
    rows = db.list_trade_orders(limit=limit)
    logger.info("recent trade orders=%s", len(rows))
    for row in rows:
        logger.info(
            "id=%s status=%s side=%s pair=%s/%s exchange=%s market=%s avg=%s filled=%s cost=%s",
            row.get("id"),
            row.get("status"),
            row.get("side"),
            row.get("base_symbol"),
            row.get("quote_symbol"),
            row.get("exchange"),
            row.get("market_symbol"),
            row.get("average_price"),
            row.get("filled_base_amount"),
            row.get("filled_quote_amount"),
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = AppConfig.from_env(env_file=args.env_file)
    if args.log_level:
        config = replace(config, log_level=args.log_level)

    setup_logging(config.log_level, config.log_file)
    logger = logging.getLogger("alpha.cli")

    command = args.command or "run"
    try:
        if command == "init-db":
            Database(config.db_path).init_db()
            logger.info("database initialized: %s", config.db_path)
            return 0

        if command == "test-tg":
            return asyncio.run(_test_tg(config, args.message, args.silent))

        if command == "check-twitter":
            return asyncio.run(_check_twitter(config))

        if command == "check-llm":
            return asyncio.run(_check_llm(config))

        if command == "trade-buy":
            return asyncio.run(
                _trade_buy(config, args.symbol, args.usdt, args.exchange, args.live, args.reason)
            )

        if command == "trade-sell":
            return asyncio.run(
                _trade_sell(config, args.symbol, args.amount, args.exchange, args.live, args.reason)
            )

        if command == "trade-orders":
            return _trade_orders(config, args.limit)

        no_startup = getattr(args, "no_startup_message", False)
        return asyncio.run(_run(config, send_startup_message=not no_startup))
    except KeyboardInterrupt:
        logger.info("interrupted by user")
        return 130
    except Exception as exc:
        logger.error("fatal error: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
