from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from .adapters import BinanceAnnouncementAdapter, SourceAdapter, TwitterTimelineAdapter
from .analyzers import OpportunityAnalyzer
from .config import AppConfig
from .db import Database
from .formatters import (
    format_anomaly,
    format_countdown,
    format_discovery,
    format_launch,
    format_periodic,
)
from .integrations import fetch_coingecko, llm_extract, send_tg
from .pipeline import SignalIngestionPipeline
from .rating import rate_project
from .timeutils import utc_now_naive


class AlphaMonitorService:
    def __init__(self, config: AppConfig, db: Database) -> None:
        self.config = config
        self.db = db
        self.logger = logging.getLogger("alpha.service")
        self.pipeline = SignalIngestionPipeline(db=db, analyzer=OpportunityAnalyzer(config=config))
        self.adapters = self._build_adapters()

    def _build_adapters(self) -> list[SourceAdapter]:
        adapters: list[SourceAdapter] = [BinanceAnnouncementAdapter(config=self.config)]
        if self.config.twitter_enabled and self.config.twitter_accounts:
            adapters.append(TwitterTimelineAdapter(config=self.config))
        return adapters

    async def source_worker(self, adapter: SourceAdapter) -> None:
        self.logger.info(
            "source worker started: %s (interval=%ss)",
            adapter.source_type,
            adapter.poll_interval_seconds,
        )
        while True:
            try:
                signals = await adapter.fetch_signals()
                for signal in signals:
                    await self.pipeline.process_signal(signal)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.error("source worker error [%s]: %s", adapter.source_type, exc, exc_info=True)

            await asyncio.sleep(adapter.poll_interval_seconds)

    async def aggregation_worker(self) -> None:
        self.logger.info("aggregation worker started, interval=%ss", self.config.aggregation_poll_interval)
        while True:
            try:
                pending = self.db.list_pending()
                for project in pending:
                    symbol = project["symbol"]
                    try:
                        self.logger.info("aggregating $%s", symbol)

                        coingecko = await fetch_coingecko(symbol, self.config)
                        await asyncio.sleep(1)

                        llm = await llm_extract(
                            project.get("raw_text", ""),
                            symbol,
                            self.config,
                            name=project.get("name") or "",
                            cg_data=coingecko,
                            source=project.get("source") or "unknown",
                        )
                        await asyncio.sleep(1)

                        if llm.get("exclude_reason") in ("already_tge", "meme_only"):
                            self.db.update_project(
                                project["id"],
                                {
                                    "excluded": 1,
                                    "exclude_reason": llm["exclude_reason"],
                                    "tier": "EXCLUDED",
                                },
                            )
                            self.logger.info("$%s excluded: %s", symbol, llm["exclude_reason"])
                            continue

                        is_darling = llm.get("is_darling", False)
                        vcs = llm.get("vcs", [])
                        narrative = llm.get("narrative", "unknown")
                        rating = rate_project(
                            coingecko.get("mcap", 0),
                            coingecko.get("fdv", 0),
                            vcs,
                            narrative,
                            is_darling,
                        )

                        self.db.update_project(
                            project["id"],
                            {
                                "tier": rating["tier"],
                                "tier_reason": rating["reason"],
                                "narrative": narrative,
                                "narrative_desc": llm.get("narrative_desc", ""),
                                "vcs_json": json.dumps(vcs),
                                "is_darling": int(is_darling),
                                "open_price": coingecko.get("price"),
                                "total_supply": coingecko.get("total_supply"),
                                "circulating_supply": coingecko.get("circ_supply"),
                                "fdv": coingecko.get("fdv"),
                                "circulating_mcap": coingecko.get("mcap"),
                            },
                        )

                        full_project = self.db.get_project(project["id"])
                        if full_project and not self.db.has_pushed(project["id"], "discovery"):
                            message = format_discovery(full_project)
                            silent = rating["tier"] in ("B", "C")
                            success = await send_tg(message, self.config, silent=silent)
                            if success:
                                self.db.log_push(project["id"], "discovery", message)
                                self.logger.info("discovery pushed: $%s [%s]", symbol, rating["tier"])

                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        self.logger.error("aggregation failed for %s: %s", symbol, exc, exc_info=True)
                        self.db.update_project(project["id"], {"tier": "ERROR", "tier_reason": str(exc)[:100]})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.error("aggregation loop error: %s", exc, exc_info=True)

            await asyncio.sleep(self.config.aggregation_poll_interval)

    async def post_launch_monitor(self) -> None:
        self.logger.info("post-launch monitor started, interval=%ss", self.config.monitor_poll_interval)
        while True:
            try:
                projects = self.db.list_active()
                for project in projects:
                    try:
                        await self._monitor_project(project)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        self.logger.error("monitor project failed for %s: %s", project.get("symbol"), exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.error("post-launch loop error: %s", exc, exc_info=True)

            await asyncio.sleep(self.config.monitor_poll_interval)

    async def _monitor_project(self, project: dict) -> None:
        source = str(project.get("source") or "")
        if source.startswith("twitter:") and not project.get("launch_time"):
            await self._monitor_twitter_project(project)
            return

        await self._monitor_launch_project(project)

    async def _monitor_launch_project(self, project: dict) -> None:
        project_id = project["id"]
        symbol = project["symbol"]
        launch_time = project.get("launch_time", "")
        if not launch_time:
            return

        try:
            launch = datetime.fromisoformat(launch_time.replace("Z", "").split("+")[0])
        except Exception:
            return

        now = utc_now_naive()
        delta_seconds = (launch - now).total_seconds()

        if 3 * 3600 - 300 <= delta_seconds <= 3 * 3600 + 300:
            if not self.db.has_pushed(project_id, "t_minus_3h"):
                text = format_countdown(project, int(delta_seconds / 60))
                ok = await send_tg(text, self.config, silent=project.get("tier") in ("B", "C"))
                if ok:
                    self.db.log_push(project_id, "t_minus_3h", text)

        elif 30 * 60 - 150 <= delta_seconds <= 30 * 60 + 150:
            if not self.db.has_pushed(project_id, "t_minus_30m"):
                text = format_countdown(project, int(delta_seconds / 60))
                ok = await send_tg(text, self.config, silent=False)
                if ok:
                    self.db.log_push(project_id, "t_minus_30m", text)

        elif -300 <= delta_seconds <= 0:
            if not self.db.has_pushed(project_id, "at_launch"):
                coingecko = await fetch_coingecko(symbol, self.config)
                if coingecko.get("price"):
                    text = format_launch(
                        project,
                        coingecko["price"],
                        coingecko.get("mcap", 0),
                        coingecko.get("fdv", 0),
                    )
                    ok = await send_tg(text, self.config, silent=False)
                    if ok:
                        self.db.log_push(project_id, "at_launch", text)
                        self.db.save_snapshot(
                            project_id,
                            coingecko["price"],
                            coingecko.get("mcap", 0),
                            coingecko.get("fdv", 0),
                        )

        elif 0 < -delta_seconds <= 2.5 * 3600:
            minutes_after = int(-delta_seconds / 60)
            await self._track_periodic_price(project=project, project_id=project_id, symbol=symbol, minutes_after=minutes_after)

    async def _monitor_twitter_project(self, project: dict) -> None:
        discovered_at = project.get("discovered_at")
        if not discovered_at:
            return

        try:
            discovered = datetime.fromisoformat(discovered_at.replace("Z", "").split("+")[0])
        except Exception:
            return

        minutes_after = int((utc_now_naive() - discovered).total_seconds() / 60)
        if minutes_after < 0 or minutes_after > 150:
            return

        await self._track_periodic_price(
            project=project,
            project_id=project["id"],
            symbol=project["symbol"],
            minutes_after=minutes_after,
            push_prefix="twitter_post_30m_",
        )

    async def _track_periodic_price(
        self,
        project: dict,
        project_id: str,
        symbol: str,
        minutes_after: int,
        push_prefix: str = "post_30m_",
    ) -> None:
        for index, target in enumerate([30, 60, 90, 120], start=1):
            if abs(minutes_after - target) <= 5:
                push_type = f"{push_prefix}{index}"
                if self.db.has_pushed(project_id, push_type):
                    break

                coingecko = await fetch_coingecko(symbol, self.config)
                if not coingecko.get("price"):
                    break

                open_price = project.get("open_price") or coingecko["price"]
                change = ((coingecko["price"] - open_price) / open_price * 100) if open_price else 0

                text = format_periodic(
                    project,
                    index,
                    coingecko["price"],
                    coingecko.get("mcap", 0),
                    change,
                )
                ok = await send_tg(
                    text,
                    self.config,
                    silent=project.get("tier") in ("B", "C") and index > 1,
                )
                if ok:
                    self.db.log_push(project_id, push_type, text)
                    self.db.save_snapshot(
                        project_id,
                        coingecko["price"],
                        coingecko.get("mcap", 0),
                        coingecko.get("fdv", 0),
                    )

                if change >= 100 and not self.db.has_pushed(project_id, "anomaly_double"):
                    alert = format_anomaly(project, "double", coingecko["price"], change)
                    if await send_tg(alert, self.config):
                        self.db.log_push(project_id, "anomaly_double", alert)
                elif change <= -50 and not self.db.has_pushed(project_id, "anomaly_halve"):
                    alert = format_anomaly(project, "halve", coingecko["price"], change)
                    if await send_tg(alert, self.config):
                        self.db.log_push(project_id, "anomaly_halve", alert)
                break

    async def run(self, send_startup_message: bool = True) -> None:
        self.db.init_db()
        self.logger.info("database=%s", self.db.db_path)

        if send_startup_message and self.config.startup_message:
            startup_msg = "🎉 <b>Crypto Alpha Radar 启动</b>\n\n📡 多源监听中...\n🔔 发现机会会立即推送"
            ok = await send_tg(startup_msg, self.config)
            if ok:
                self.logger.info("telegram startup ping succeeded")
            else:
                self.logger.warning("telegram startup ping failed")

        source_tasks = [
            asyncio.create_task(self.source_worker(adapter), name=f"source:{adapter.source_type}")
            for adapter in self.adapters
        ]

        tasks = source_tasks + [
            asyncio.create_task(self.aggregation_worker(), name="aggregator"),
            asyncio.create_task(self.post_launch_monitor(), name="monitor"),
        ]

        enabled_sources = [adapter.source_type for adapter in self.adapters]
        self.logger.info("alpha radar started")
        self.logger.info("sources=%s", ",".join(enabled_sources))
        self.logger.info("llm=%s", "enabled" if self.config.llm_enabled else "fallback_rules")
        self.logger.info("telegram=%s", "enabled" if self.config.tg_bot_token else "disabled")

        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
