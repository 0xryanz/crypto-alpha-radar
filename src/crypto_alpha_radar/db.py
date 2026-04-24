from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    create_engine,
    or_,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .timeutils import utc_now_iso


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    launch_time: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tier: Mapped[str] = mapped_column(String, default="PENDING")
    tier_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    narrative: Mapped[str | None] = mapped_column(String, nullable=True)
    narrative_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    vcs_json: Mapped[str] = mapped_column(Text, default="[]")
    is_darling: Mapped[int] = mapped_column(Integer, default=0)
    open_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_supply: Mapped[float | None] = mapped_column(Float, nullable=True)
    circulating_supply: Mapped[float | None] = mapped_column(Float, nullable=True)
    fdv: Mapped[float | None] = mapped_column(Float, nullable=True)
    circulating_mcap: Mapped[float | None] = mapped_column(Float, nullable=True)
    excluded: Mapped[int] = mapped_column(Integer, default=0)
    exclude_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    discovered_at: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String, nullable=True)


class Push(Base):
    __tablename__ = "pushes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    push_type: Mapped[str | None] = mapped_column(String, nullable=True)
    sent_at: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    circulating_mcap: Mapped[float | None] = mapped_column(Float, nullable=True)
    fdv: Mapped[float | None] = mapped_column(Float, nullable=True)


class SourceEvent(Base):
    __tablename__ = "source_events"
    __table_args__ = (UniqueConstraint("source_type", "external_id", name="uq_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    account: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str | None] = mapped_column(String, nullable=True)
    fetched_at: Mapped[str] = mapped_column(String, nullable=False)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class AssetMarketMapping(Base):
    __tablename__ = "asset_market_mappings"
    __table_args__ = (
        UniqueConstraint("base_symbol", "quote_symbol", "exchange", name="uq_asset_market_mapping"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_symbol: Mapped[str] = mapped_column(String, nullable=False)
    quote_symbol: Mapped[str] = mapped_column(String, nullable=False)
    exchange: Mapped[str] = mapped_column(String, nullable=False)
    market_symbol: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class TradeOrder(Base):
    __tablename__ = "trade_orders"
    __table_args__ = (UniqueConstraint("request_id", name="uq_trade_request_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[str] = mapped_column(String, nullable=False)
    base_symbol: Mapped[str] = mapped_column(String, nullable=False)
    quote_symbol: Mapped[str] = mapped_column(String, nullable=False)
    requested_quote_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    requested_base_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange: Mapped[str | None] = mapped_column(String, nullable=True)
    market_symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[int] = mapped_column(Integer, default=1)
    order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    filled_base_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    filled_quote_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


def _project_to_dict(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "symbol": project.symbol,
        "name": project.name,
        "launch_time": project.launch_time,
        "source": project.source,
        "raw_text": project.raw_text,
        "tier": project.tier,
        "tier_reason": project.tier_reason,
        "narrative": project.narrative,
        "narrative_desc": project.narrative_desc,
        "vcs_json": project.vcs_json,
        "is_darling": project.is_darling,
        "open_price": project.open_price,
        "total_supply": project.total_supply,
        "circulating_supply": project.circulating_supply,
        "fdv": project.fdv,
        "circulating_mcap": project.circulating_mcap,
        "excluded": project.excluded,
        "exclude_reason": project.exclude_reason,
        "discovered_at": project.discovered_at,
        "updated_at": project.updated_at,
    }


def _trade_order_to_dict(order: TradeOrder) -> dict[str, Any]:
    return {
        "id": order.id,
        "request_id": order.request_id,
        "side": order.side,
        "base_symbol": order.base_symbol,
        "quote_symbol": order.quote_symbol,
        "requested_quote_amount": order.requested_quote_amount,
        "requested_base_amount": order.requested_base_amount,
        "exchange": order.exchange,
        "market_symbol": order.market_symbol,
        "status": order.status,
        "reason": order.reason,
        "dry_run": order.dry_run,
        "order_id": order.order_id,
        "filled_base_amount": order.filled_base_amount,
        "filled_quote_amount": order.filled_quote_amount,
        "average_price": order.average_price,
        "error_message": order.error_message,
        "raw_json": order.raw_json,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_url = f"sqlite:///{self.db_path}"
        self.engine = create_engine(self.db_url)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _session(self) -> Session:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return self.session_factory()

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self.engine)

    @staticmethod
    def make_project_id(symbol: str, date_str: str) -> str:
        return hashlib.md5(f"{symbol.upper()}_{date_str}".encode()).hexdigest()[:16]

    def project_exists(self, project_id: str) -> bool:
        with self._session() as session:
            stmt = select(Project.id).where(Project.id == project_id).limit(1)
            return session.execute(stmt).scalar_one_or_none() is not None

    def save_project(self, project: dict[str, Any]) -> None:
        with self._session() as session:
            existing = session.get(Project, project["id"])
            if existing is not None:
                return

            now = utc_now_iso()
            model = Project(
                id=project["id"],
                symbol=project["symbol"],
                name=project.get("name"),
                launch_time=project.get("launch_time"),
                source=project.get("source"),
                raw_text=project.get("raw_text"),
                tier=project.get("tier", "PENDING"),
                tier_reason=project.get("tier_reason"),
                narrative=project.get("narrative"),
                narrative_desc=project.get("narrative_desc"),
                vcs_json=project.get("vcs_json", json.dumps(project.get("vcs", []))),
                is_darling=int(project.get("is_darling", False)),
                open_price=project.get("open_price"),
                total_supply=project.get("total_supply"),
                circulating_supply=project.get("circulating_supply"),
                fdv=project.get("fdv"),
                circulating_mcap=project.get("circulating_mcap"),
                excluded=int(project.get("excluded", 0)),
                exclude_reason=project.get("exclude_reason"),
                discovered_at=now,
                updated_at=now,
            )
            session.add(model)
            session.commit()

    def update_project(self, project_id: str, fields: dict[str, Any]) -> None:
        if not fields:
            return

        with self._session() as session:
            model = session.get(Project, project_id)
            if model is None:
                return

            for key, value in fields.items():
                if hasattr(model, key):
                    setattr(model, key, value)
            model.updated_at = utc_now_iso()
            session.commit()

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            model = session.get(Project, project_id)
            if model is None:
                return None
            return _project_to_dict(model)

    def list_pending(self) -> list[dict[str, Any]]:
        with self._session() as session:
            stmt = (
                select(Project)
                .where(Project.excluded == 0)
                .where(Project.tier == "PENDING")
                .order_by(Project.discovered_at)
            )
            projects = session.execute(stmt).scalars().all()
            return [_project_to_dict(project) for project in projects]

    def list_active(self) -> list[dict[str, Any]]:
        with self._session() as session:
            stmt = (
                select(Project)
                .where(Project.excluded == 0)
                .where(Project.tier.not_in(["PENDING", "EXCLUDED", "ERROR"]))
                .where(
                    or_(
                        and_(Project.launch_time.is_not(None), Project.launch_time != ""),
                        Project.source.like("twitter:%"),
                    )
                )
            )
            projects = session.execute(stmt).scalars().all()
            return [_project_to_dict(project) for project in projects]

    def save_source_event(
        self,
        source_type: str,
        external_id: str,
        account: str | None,
        text: str,
        created_at: str | None,
        raw_json: str | None,
    ) -> bool:
        with self._session() as session:
            stmt = (
                select(SourceEvent.id)
                .where(SourceEvent.source_type == source_type)
                .where(SourceEvent.external_id == external_id)
                .limit(1)
            )
            exists = session.execute(stmt).scalar_one_or_none() is not None
            if exists:
                return False

            event = SourceEvent(
                source_type=source_type,
                external_id=external_id,
                account=account,
                text=text,
                created_at=created_at,
                fetched_at=utc_now_iso(),
                raw_json=raw_json,
            )
            session.add(event)
            session.commit()
            return True

    def has_pushed(self, project_id: str, push_type: str) -> bool:
        with self._session() as session:
            stmt = (
                select(Push.id)
                .where(Push.project_id == project_id)
                .where(Push.push_type == push_type)
                .limit(1)
            )
            return session.execute(stmt).scalar_one_or_none() is not None

    def log_push(self, project_id: str, push_type: str, content: str) -> None:
        with self._session() as session:
            push = Push(
                project_id=project_id,
                push_type=push_type,
                sent_at=utc_now_iso(),
                content=content,
            )
            session.add(push)
            session.commit()

    def save_snapshot(self, project_id: str, price: float, mcap: float, fdv: float) -> None:
        with self._session() as session:
            snapshot = Snapshot(
                project_id=project_id,
                timestamp=utc_now_iso(),
                price=price,
                circulating_mcap=mcap,
                fdv=fdv,
            )
            session.add(snapshot)
            session.commit()

    def get_market_mapping(self, base_symbol: str, quote_symbol: str, exchange: str) -> dict[str, Any] | None:
        with self._session() as session:
            stmt = (
                select(AssetMarketMapping)
                .where(AssetMarketMapping.base_symbol == base_symbol.upper())
                .where(AssetMarketMapping.quote_symbol == quote_symbol.upper())
                .where(AssetMarketMapping.exchange == exchange.lower())
                .limit(1)
            )
            mapping = session.execute(stmt).scalar_one_or_none()
            if mapping is None:
                return None
            return {
                "id": mapping.id,
                "base_symbol": mapping.base_symbol,
                "quote_symbol": mapping.quote_symbol,
                "exchange": mapping.exchange,
                "market_symbol": mapping.market_symbol,
                "created_at": mapping.created_at,
                "updated_at": mapping.updated_at,
            }

    def upsert_market_mapping(self, mapping: dict[str, Any]) -> None:
        with self._session() as session:
            stmt = (
                select(AssetMarketMapping)
                .where(AssetMarketMapping.base_symbol == str(mapping["base_symbol"]).upper())
                .where(AssetMarketMapping.quote_symbol == str(mapping["quote_symbol"]).upper())
                .where(AssetMarketMapping.exchange == str(mapping["exchange"]).lower())
                .limit(1)
            )
            existing = session.execute(stmt).scalar_one_or_none()
            now = utc_now_iso()
            if existing is None:
                model = AssetMarketMapping(
                    base_symbol=str(mapping["base_symbol"]).upper(),
                    quote_symbol=str(mapping["quote_symbol"]).upper(),
                    exchange=str(mapping["exchange"]).lower(),
                    market_symbol=str(mapping["market_symbol"]),
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
            else:
                existing.market_symbol = str(mapping["market_symbol"])
                existing.updated_at = now
            session.commit()

    def create_trade_order(self, payload: dict[str, Any]) -> int:
        with self._session() as session:
            now = utc_now_iso()
            model = TradeOrder(
                request_id=str(payload["request_id"]),
                side=str(payload["side"]),
                base_symbol=str(payload["base_symbol"]).upper(),
                quote_symbol=str(payload["quote_symbol"]).upper(),
                requested_quote_amount=payload.get("requested_quote_amount"),
                requested_base_amount=payload.get("requested_base_amount"),
                exchange=str(payload.get("exchange", "")) or None,
                market_symbol=str(payload.get("market_symbol", "")) or None,
                status=str(payload.get("status", "PENDING")),
                reason=payload.get("reason"),
                dry_run=int(payload.get("dry_run", 1)),
                order_id=str(payload.get("order_id", "")) or None,
                filled_base_amount=payload.get("filled_base_amount"),
                filled_quote_amount=payload.get("filled_quote_amount"),
                average_price=payload.get("average_price"),
                error_message=payload.get("error_message"),
                raw_json=(
                    json.dumps(payload.get("raw_json"), ensure_ascii=False, default=str)
                    if payload.get("raw_json") is not None
                    else None
                ),
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.commit()
            return int(model.id)

    def update_trade_order(self, order_pk: int, fields: dict[str, Any]) -> None:
        if not fields:
            return
        with self._session() as session:
            model = session.get(TradeOrder, order_pk)
            if model is None:
                return

            for key, value in fields.items():
                if key == "raw_json" and value is not None:
                    setattr(model, key, json.dumps(value, ensure_ascii=False, default=str))
                elif hasattr(model, key):
                    setattr(model, key, value)
            model.updated_at = utc_now_iso()
            session.commit()

    def list_trade_orders(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._session() as session:
            stmt = select(TradeOrder).order_by(TradeOrder.id.desc()).limit(max(1, int(limit)))
            rows = session.execute(stmt).scalars().all()
            return [_trade_order_to_dict(row) for row in rows]
