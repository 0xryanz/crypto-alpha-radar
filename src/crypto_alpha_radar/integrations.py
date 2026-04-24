from __future__ import annotations

import asyncio
import logging

import httpx

from .config import AppConfig
from .constants import (
    ANNOUNCEMENT_CATALOG_IDS,
    BINANCE_ANNOUNCEMENT_API,
    BINANCE_DARLING_KEYWORDS,
    COINGECKO_COIN_API,
    COINGECKO_SEARCH_API,
    HTTP_HEADERS,
    TWITTER_EXCLUDE_KEYWORDS,
    TWITTER_OPPORTUNITY_KEYWORDS,
)
from .llm_client import call_llm_json

logger = logging.getLogger("alpha.integrations")


async def send_tg(text: str, config: AppConfig, silent: bool = False) -> bool:
    if not config.tg_bot_token or not config.tg_chat_id:
        logger.error("TG_BOT_TOKEN or TG_CHAT_ID is missing")
        return False

    url = f"https://api.telegram.org/bot{config.tg_bot_token}/sendMessage"
    payload = {
        "chat_id": config.tg_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_notification": silent,
    }

    try:
        async with httpx.AsyncClient(timeout=config.request_timeout_seconds, headers=HTTP_HEADERS) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                logger.error("TG send failed %s: %s", response.status_code, response.text[:200])
                return False
            return True
    except Exception as exc:  # pragma: no cover - network dependent
        logger.error("TG send error: %s", exc)
        return False


async def fetch_announcements(config: AppConfig) -> list[dict]:
    all_articles: list[dict] = []
    for catalog_id in ANNOUNCEMENT_CATALOG_IDS:
        params = {
            "type": 1,
            "catalogId": catalog_id,
            "pageNo": 1,
            "pageSize": config.announcement_fetch_limit,
        }
        try:
            async with httpx.AsyncClient(timeout=config.request_timeout_seconds, headers=HTTP_HEADERS) as client:
                response = await client.get(BINANCE_ANNOUNCEMENT_API, params=params)
                response.raise_for_status()
                data = response.json()
                for catalog in data.get("data", {}).get("catalogs", []):
                    for article in catalog.get("articles", []):
                        article["_catalog_id"] = catalog_id
                        all_articles.append(article)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("Failed to fetch catalog %s: %s", catalog_id, exc)

    seen_codes: set[str] = set()
    unique_articles: list[dict] = []
    for article in all_articles:
        code = article.get("code")
        if code and code not in seen_codes:
            seen_codes.add(code)
            unique_articles.append(article)
    return unique_articles


async def fetch_coingecko(symbol: str, config: AppConfig) -> dict:
    result = {
        "found": False,
        "price": None,
        "fdv": None,
        "mcap": None,
        "total_supply": None,
        "circ_supply": None,
        "chain": None,
        "contract": None,
    }
    try:
        async with httpx.AsyncClient(timeout=config.request_timeout_seconds, headers=HTTP_HEADERS) as client:
            response = await client.get(COINGECKO_SEARCH_API, params={"query": symbol})
            if response.status_code != 200:
                return result

            coins = response.json().get("coins", [])
            coin_id = None
            for coin in coins:
                if coin.get("symbol", "").upper() == symbol.upper():
                    coin_id = coin["id"]
                    break

            if not coin_id:
                return result

            response2 = await client.get(
                COINGECKO_COIN_API.format(coin_id=coin_id),
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                },
            )

            if response2.status_code == 429:
                await asyncio.sleep(5)
                response2 = await client.get(
                    COINGECKO_COIN_API.format(coin_id=coin_id),
                    params={
                        "localization": "false",
                        "tickers": "false",
                        "market_data": "true",
                        "community_data": "false",
                        "developer_data": "false",
                    },
                )

            if response2.status_code != 200:
                return result

            data = response2.json()
            market_data = data.get("market_data", {})
            result.update(
                {
                    "found": True,
                    "price": (market_data.get("current_price") or {}).get("usd"),
                    "fdv": (market_data.get("fully_diluted_valuation") or {}).get("usd"),
                    "mcap": (market_data.get("market_cap") or {}).get("usd"),
                    "total_supply": market_data.get("total_supply"),
                    "circ_supply": market_data.get("circulating_supply"),
                    "categories": data.get("categories", []),
                    "description": (data.get("description") or {}).get("en", "")[:500],
                }
            )

            platforms = data.get("platforms", {})
            for chain, address in platforms.items():
                if address:
                    result["chain"] = chain
                    result["contract"] = address
                    break
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("CoinGecko lookup failed for %s: %s", symbol, exc)

    return result


async def llm_extract(
    raw_text: str,
    symbol: str,
    config: AppConfig,
    name: str = "",
    cg_data: dict | None = None,
    source: str = "unknown",
) -> dict:
    fallback = {
        "narrative": "unknown",
        "narrative_desc": "",
        "vcs": [],
        "is_darling": False,
        "exclude_reason": None,
    }

    cg_data = cg_data or {}
    categories = cg_data.get("categories", [])
    description = cg_data.get("description", "")

    darling_categories = [
        category
        for category in categories
        if any(keyword in category.lower() for keyword in ["yzi labs", "binance labs"])
    ]
    if darling_categories:
        fallback["is_darling"] = True

    if not config.llm_enabled:
        text = raw_text.lower()
        for keyword in BINANCE_DARLING_KEYWORDS:
            if keyword in text:
                fallback["is_darling"] = True

        category_text = " ".join(categories).lower()
        if "defi" in category_text:
            fallback["narrative"] = "defi"
        elif "ai" in category_text:
            fallback["narrative"] = "ai_agent"
        elif "gaming" in category_text or "gamefi" in category_text:
            fallback["narrative"] = "gamefi"
        elif "meme" in category_text:
            fallback["narrative"] = "meme"
        elif "rwa" in category_text or "real world" in category_text:
            fallback["narrative"] = "rwa"
        return fallback

    extra_context = ""
    if categories:
        extra_context += f"\nCoinGecko分类: {', '.join(categories)}"
    if description:
        extra_context += f"\n项目描述: {description[:300]}"
    if cg_data.get("found"):
        extra_context += (
            "\n市场数据: "
            f"FDV=${cg_data.get('fdv', 0):,.0f}, "
            f"MCap=${cg_data.get('mcap', 0):,.0f}, "
            f"价格=${cg_data.get('price', 0)}"
        )
        if cg_data.get("chain"):
            extra_context += f", 链={cg_data['chain']}"

    system_prompt = "你是加密货币研究员，从项目信号和市场数据中提取关键信息。只返回JSON，无其他文字。"
    user_prompt = f"""分析这个加密项目信号：
来源: {source}
代币: {symbol}, 项目名: {name or "未知"}
信号原文: {raw_text}
{extra_context}

返回JSON:
{{
  "narrative": "defi_perp|ai_agent|ai_defi|defai|zk_proof|infra|defi|rwa|gamefi|meme|social|stablecoin|unknown",
  "narrative_desc": "一句话中文描述这个项目做什么、有什么特点",
  "vcs": ["从CoinGecko分类和公告中提取的投资机构列表"],
  "is_darling": true/false,
  "exclude_reason": null|"already_tge"|"meme_only"
}}

判断规则:
- narrative: 选最主要的一个类别
- vcs: CoinGecko分类里如果有 "XXX Portfolio" 就提取XXX作为机构
- is_darling: 如果有YZi Labs/Binance Labs投资 或 CZ/何一站台 则true
- exclude_reason: 只有当项目在其他主要CEX(如Coinbase/OKX/Bybit)上线超过3个月才算"already_tge"。如果只是在DEX或刚在币安上线，不算already_tge。CoinGecko有价格数据不代表already_tge。纯meme无叙事则"meme_only"
"""

    parsed = await call_llm_json(
        config=config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=800,
    )
    if not isinstance(parsed, dict):
        return fallback
    return parsed


async def llm_extract_tweet(
    text: str,
    account: str,
    candidate_symbols: list[str],
    config: AppConfig,
) -> dict:
    fallback = {
        "is_opportunity": False,
        "symbol": candidate_symbols[0] if candidate_symbols else "",
        "name": "",
        "launch_time": None,
        "reason": "fallback_rules",
        "confidence": 0.0,
        "exclude_reason": None,
    }

    text_lower = text.lower()
    if any(keyword in text_lower for keyword in TWITTER_EXCLUDE_KEYWORDS):
        fallback["exclude_reason"] = "excluded_keyword"
        return fallback

    matched_keywords = [keyword for keyword in TWITTER_OPPORTUNITY_KEYWORDS if keyword in text_lower]
    if matched_keywords and candidate_symbols:
        fallback.update(
            {
                "is_opportunity": True,
                "confidence": 0.62,
                "reason": f"keyword_match:{matched_keywords[0]}",
            }
        )

    if not config.llm_enabled:
        return fallback

    prompt = f"""你是加密货币机会筛选器。请基于推文判断是否值得作为监控候选。
作者: @{account}
候选代币: {', '.join(candidate_symbols) if candidate_symbols else '无'}
推文: {text}

返回严格JSON：
{{
  "is_opportunity": true/false,
  "symbol": "候选中最可能的symbol，若无则空字符串",
  "name": "项目名或空",
  "launch_time": "ISO时间或null",
  "reason": "简短中文原因",
  "confidence": 0.0-1.0,
  "exclude_reason": null|"noise"|"not_crypto"|"low_signal"
}}
"""

    parsed = await call_llm_json(
        config=config,
        system_prompt="你只输出JSON，不输出任何额外文本。",
        user_prompt=prompt,
        max_tokens=400,
    )
    if not isinstance(parsed, dict):
        return fallback

    parsed.setdefault("confidence", 0.0)
    parsed.setdefault("reason", "")
    parsed.setdefault("symbol", "")
    parsed.setdefault("name", "")
    parsed.setdefault("launch_time", None)
    parsed.setdefault("exclude_reason", None)
    parsed["is_opportunity"] = bool(parsed.get("is_opportunity", False))
    return parsed
