from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from .config import AppConfig
from .constants import HTTP_HEADERS

logger = logging.getLogger("alpha.llm")


def _extract_json_block(text: str) -> str:
    payload = text.strip()
    if payload.startswith("```"):
        lines = payload.split("\n")
        payload = "\n".join(lines[1:-1]).strip()
    return payload


def _extract_anthropic_text(response_json: dict[str, Any]) -> str:
    for block in response_json.get("content", []):
        if block.get("type") == "text":
            return str(block.get("text", ""))
    return ""


def _extract_openai_text(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    return str(message.get("content", ""))


async def call_llm_json(
    *,
    config: AppConfig,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float = 0,
) -> dict[str, Any] | None:
    provider = config.llm_provider_normalized
    if provider == "openai" and not config.openai_api_key:
        return None
    if provider == "anthropic" and not config.anthropic_api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=30, headers=HTTP_HEADERS) as client:
            if provider == "openai":
                response = await client.post(
                    f"{config.openai_base_url.rstrip('/')}/v1/chat/completions",
                    headers={
                        "authorization": f"Bearer {config.openai_api_key}",
                        "content-type": "application/json",
                    },
                    json={
                        "model": config.openai_model,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                )
                if response.status_code != 200:
                    logger.warning("OpenAI call failed: %s", response.status_code)
                    return None
                text = _extract_openai_text(response.json())
            else:
                response = await client.post(
                    f"{config.anthropic_base_url.rstrip('/')}/v1/messages",
                    headers={
                        "x-api-key": config.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": config.anthropic_model,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_prompt}],
                    },
                )
                if response.status_code != 200:
                    logger.warning("Anthropic call failed: %s", response.status_code)
                    return None
                text = _extract_anthropic_text(response.json())

            payload = _extract_json_block(text)
            return json.loads(payload)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("LLM JSON call failed: %s", exc)
        return None


async def llm_healthcheck(config: AppConfig) -> tuple[bool, str]:
    result = await call_llm_json(
        config=config,
        system_prompt="You return strict JSON only.",
        user_prompt='Return JSON: {"ok": true, "provider": "name"}',
        max_tokens=120,
    )
    if not result:
        return False, "llm call failed"
    if result.get("ok") is True:
        provider = str(result.get("provider") or config.llm_provider_normalized)
        return True, f"llm provider={provider} reachable"
    return False, "llm returned unexpected payload"
