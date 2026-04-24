from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from ..config import AppConfig
from ..domain import SourceSignal
from ..timeutils import utc_now_naive
from .base import SourceAdapter

logger = logging.getLogger("alpha.adapters.twitter")


class TwitterTimelineAdapter(SourceAdapter):
    source_type = "twitter"

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.poll_interval_seconds = config.twitter_poll_interval
        self._api: Any = None
        self._gather: Any = None
        self._initialized = False
        self._init_failed = False

    async def fetch_signals(self) -> list[SourceSignal]:
        if not self.config.twitter_enabled or not self.config.twitter_accounts:
            return []

        ready = await self._ensure_client()
        if not ready:
            return []

        all_signals: list[SourceSignal] = []
        for account in self.config.twitter_accounts:
            query = f"from:{account}"
            try:
                tweets = await self._gather(
                    self._api.search(query, limit=self.config.twitter_fetch_limit)
                )
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning("twitter scrape failed for @%s: %s", account, exc)
                continue

            for tweet in tweets or []:
                in_reply_to = getattr(tweet, "inReplyToTweetId", None)
                if in_reply_to and not self.config.twitter_include_replies:
                    continue

                retweeted_tweet = getattr(tweet, "retweetedTweet", None)
                if retweeted_tweet and not self.config.twitter_include_retweets:
                    continue

                tweet_id = str(getattr(tweet, "id", "") or "")
                if not tweet_id:
                    continue

                content = self._extract_content(tweet)
                if not content:
                    continue

                created_at = getattr(tweet, "date", None)
                created_at = created_at if isinstance(created_at, datetime) else utc_now_naive()
                url = getattr(tweet, "url", None)

                all_signals.append(
                    SourceSignal(
                        source_type=self.source_type,
                        external_id=tweet_id,
                        text=content,
                        account=account,
                        created_at=created_at,
                        metadata={
                            "tweet_id": tweet_id,
                            "url": str(url) if url else f"https://x.com/{account}/status/{tweet_id}",
                            "in_reply_to": in_reply_to,
                            "is_retweet": bool(retweeted_tweet),
                            "like_count": int(getattr(tweet, "likeCount", 0) or 0),
                            "retweet_count": int(getattr(tweet, "retweetCount", 0) or 0),
                            "provider": "twscrape",
                        },
                    )
                )

        return all_signals

    async def _ensure_client(self) -> bool:
        if self._initialized:
            return True
        if self._init_failed:
            return False

        try:
            from twscrape import API, gather
        except Exception as exc:  # pragma: no cover - optional dependency runtime
            logger.error("twscrape unavailable, twitter source disabled: %s", exc)
            self._init_failed = True
            return False

        credentials = self._load_credentials()
        if not credentials:
            logger.error(
                "twitter auth missing; configure TWITTER_AUTH_FILE or single TWITTER_LOGIN_* credentials"
            )
            self._init_failed = True
            return False

        api = API()
        try:
            for cred in credentials:
                await api.pool.add_account(
                    cred["username"],
                    cred["password"],
                    cred["email"],
                    cred["email_password"],
                )
            await api.pool.login_all()
        except Exception as exc:  # pragma: no cover - network dependent
            logger.error("twscrape login failed: %s", exc)
            self._init_failed = True
            return False

        self._api = api
        self._gather = gather
        self._initialized = True
        logger.info("twscrape client ready; auth_accounts=%s", len(credentials))
        return True

    def _load_credentials(self) -> list[dict[str, str]]:
        if self.config.twitter_auth_file and self.config.twitter_auth_file.exists():
            loaded = self._load_credentials_from_file(self.config.twitter_auth_file)
            if loaded:
                return loaded

        single = {
            "username": self.config.twitter_login_username,
            "password": self.config.twitter_login_password,
            "email": self.config.twitter_login_email,
            "email_password": self.config.twitter_login_email_password,
        }
        if all(single.values()):
            return [single]
        return []

    @staticmethod
    def _load_credentials_from_file(path) -> list[dict[str, str]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - filesystem dependent
            logger.error("failed to read twitter auth file %s: %s", path, exc)
            return []

        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            logger.error("twitter auth file must be JSON object or list")
            return []

        creds: list[dict[str, str]] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                logger.warning("skip invalid twitter auth entry index=%s", index)
                continue

            cred = {
                "username": str(item.get("username", "")).strip(),
                "password": str(item.get("password", "")).strip(),
                "email": str(item.get("email", "")).strip(),
                "email_password": str(item.get("email_password", "")).strip(),
            }
            if all(cred.values()):
                creds.append(cred)
            else:
                logger.warning("skip incomplete twitter auth entry index=%s", index)

        return creds

    @staticmethod
    def _extract_content(tweet: Any) -> str:
        for field in ("rawContent", "renderedContent", "content", "text"):
            value = getattr(tweet, field, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""
