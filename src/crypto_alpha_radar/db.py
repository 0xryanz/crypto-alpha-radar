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
