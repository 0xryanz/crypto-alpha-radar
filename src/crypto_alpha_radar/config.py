from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _to_int(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_float(value: str | None, default: float) -> float:
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _to_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return tuple()
    parts = []
    for item in value.split(","):
        clean = item.strip().lstrip("@").lower()
        if clean:
            parts.append(clean)
    return tuple(parts)


def _to_upper_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return tuple()
    parts = []
    for item in value.split(","):
        clean = item.strip().upper()
        if clean:
            parts.append(clean)
    return tuple(parts)


def _to_path(value: str | None, cwd: Path) -> Path | None:
    if not value:
        return None
    parsed = Path(value.strip())
    return parsed if parsed.is_absolute() else (cwd / parsed).resolve()


def _strip_wrapped(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_wrapped(value.strip())
        if key:
            os.environ.setdefault(key, value)


@dataclass(slots=True)
class AppConfig:
    db_path: Path
    tg_bot_token: str
    tg_chat_id: str
    anthropic_api_key: str
    anthropic_base_url: str
    anthropic_model: str
    llm_provider: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    announcement_poll_interval: int
    aggregation_poll_interval: int
    monitor_poll_interval: int
    announcement_fetch_limit: int
    request_timeout_seconds: int
    log_level: str
    log_file: Path | None
    startup_message: bool
    twitter_enabled: bool
    twitter_accounts: tuple[str, ...]
    twitter_poll_interval: int
    twitter_fetch_limit: int
    twitter_include_replies: bool
    twitter_include_retweets: bool
    twitter_min_confidence: float
    twitter_auth_file: Path | None
    twitter_login_username: str
    twitter_login_password: str
    twitter_login_email: str
    twitter_login_email_password: str
    trading_enabled: bool
    trading_dry_run: bool
    trading_exchanges: tuple[str, ...]
    trading_default_quote: str
    trading_max_order_usdt: float
    trading_auto_buy_enabled: bool
    trading_auto_buy_tiers: tuple[str, ...]
    trading_auto_buy_usdt: float
    trading_allowed_symbols: tuple[str, ...]
    trading_blocked_symbols: tuple[str, ...]
    trading_max_slippage_bps: int

    @property
    def llm_provider_normalized(self) -> str:
        provider = self.llm_provider.strip().lower()
        if provider in {"anthropic", "openai"}:
            return provider
        if self.openai_api_key and not self.anthropic_api_key:
            return "openai"
        return "anthropic"

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider_normalized == "openai":
            return bool(self.openai_api_key.strip())
        return bool(self.anthropic_api_key.strip())

    def exchange_credentials(self, exchange: str) -> dict[str, str]:
        prefix = exchange.strip().upper()
        return {
            "apiKey": os.environ.get(f"{prefix}_API_KEY", "").strip(),
            "secret": os.environ.get(f"{prefix}_API_SECRET", "").strip(),
            "password": os.environ.get(f"{prefix}_API_PASSWORD", "").strip(),
        }

    @classmethod
    def from_env(cls, env_file: str | None = None, working_dir: Path | None = None) -> "AppConfig":
        cwd = (working_dir or Path.cwd()).resolve()

        if env_file:
            env_path = Path(env_file)
            if not env_path.is_absolute():
                env_path = cwd / env_path
            load_env_file(env_path)
        else:
            for candidate in (cwd / ".env", cwd / ".env.systemd"):
                if candidate.exists():
                    load_env_file(candidate)
                    break

        db_path = Path(os.environ.get("DB_PATH", str(cwd / "data" / "alpha.db")))
        if not db_path.is_absolute():
            db_path = (cwd / db_path).resolve()

        raw_log_file = os.environ.get("LOG_FILE", "").strip()
        log_file: Path | None = None
        if raw_log_file:
            parsed_log = Path(raw_log_file)
            log_file = parsed_log if parsed_log.is_absolute() else (cwd / parsed_log).resolve()

        return cls(
            db_path=db_path,
            tg_bot_token=os.environ.get("TG_BOT_TOKEN", "").strip(),
            tg_chat_id=os.environ.get("TG_CHAT_ID", "").strip(),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            anthropic_base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip(),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514").strip(),
            llm_provider=os.environ.get("LLM_PROVIDER", "anthropic").strip(),
            openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com").strip(),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini").strip(),
            announcement_poll_interval=_to_int(os.environ.get("ANNOUNCEMENT_POLL_INTERVAL"), 30),
            aggregation_poll_interval=_to_int(os.environ.get("AGGREGATION_POLL_INTERVAL"), 15),
            monitor_poll_interval=_to_int(os.environ.get("MONITOR_POLL_INTERVAL"), 120),
            announcement_fetch_limit=_to_int(os.environ.get("ANNOUNCEMENT_FETCH_LIMIT"), 20),
            request_timeout_seconds=_to_int(os.environ.get("REQUEST_TIMEOUT_SECONDS"), 15),
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            log_file=log_file,
            startup_message=_to_bool(os.environ.get("STARTUP_MESSAGE"), True),
            twitter_enabled=_to_bool(os.environ.get("TWITTER_ENABLED"), False),
            twitter_accounts=_to_list(os.environ.get("TWITTER_ACCOUNTS")),
            twitter_poll_interval=_to_int(os.environ.get("TWITTER_POLL_INTERVAL"), 45),
            twitter_fetch_limit=_to_int(os.environ.get("TWITTER_FETCH_LIMIT"), 8),
            twitter_include_replies=_to_bool(os.environ.get("TWITTER_INCLUDE_REPLIES"), False),
            twitter_include_retweets=_to_bool(os.environ.get("TWITTER_INCLUDE_RETWEETS"), False),
            twitter_min_confidence=_to_float(os.environ.get("TWITTER_MIN_CONFIDENCE"), 0.6),
            twitter_auth_file=_to_path(os.environ.get("TWITTER_AUTH_FILE"), cwd),
            twitter_login_username=os.environ.get("TWITTER_LOGIN_USERNAME", "").strip(),
            twitter_login_password=os.environ.get("TWITTER_LOGIN_PASSWORD", "").strip(),
            twitter_login_email=os.environ.get("TWITTER_LOGIN_EMAIL", "").strip(),
            twitter_login_email_password=os.environ.get("TWITTER_LOGIN_EMAIL_PASSWORD", "").strip(),
            trading_enabled=_to_bool(os.environ.get("TRADING_ENABLED"), False),
            trading_dry_run=_to_bool(os.environ.get("TRADING_DRY_RUN"), True),
            trading_exchanges=_to_list(os.environ.get("TRADING_EXCHANGES", "binance")),
            trading_default_quote=(os.environ.get("TRADING_DEFAULT_QUOTE", "USDT").strip().upper() or "USDT"),
            trading_max_order_usdt=_to_float(os.environ.get("TRADING_MAX_ORDER_USDT"), 50.0),
            trading_auto_buy_enabled=_to_bool(os.environ.get("TRADING_AUTO_BUY_ENABLED"), False),
            trading_auto_buy_tiers=_to_upper_list(os.environ.get("TRADING_AUTO_BUY_TIERS", "S,A")),
            trading_auto_buy_usdt=_to_float(os.environ.get("TRADING_AUTO_BUY_USDT"), 20.0),
            trading_allowed_symbols=_to_upper_list(os.environ.get("TRADING_ALLOWED_SYMBOLS")),
            trading_blocked_symbols=_to_upper_list(os.environ.get("TRADING_BLOCKED_SYMBOLS")),
            trading_max_slippage_bps=_to_int(os.environ.get("TRADING_MAX_SLIPPAGE_BPS"), 80),
        )
