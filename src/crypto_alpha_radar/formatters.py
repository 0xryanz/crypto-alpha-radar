import json

from .constants import TIER1_VCS, TIER_ICONS, TIER_LABELS


def format_mcap(value: float | None) -> str:
    if not value:
        return "N/A"
    if value >= 1e9:
        return f"${value / 1e9:.1f}B"
    if value >= 1e6:
        return f"${value / 1e6:.1f}M"
    if value >= 1e3:
        return f"${value / 1e3:.0f}K"
    return f"${value:.0f}"


def format_price(value: float | None) -> str:
    if not value:
        return "N/A"
    if value >= 1:
        return f"${value:.2f}"
    if value >= 0.01:
        return f"${value:.4f}"
    return f"${value:.6f}"


def format_discovery(project: dict) -> str:
    tier = project.get("tier", "C")
    icon = TIER_ICONS.get(tier, "⚪")
    label = TIER_LABELS.get(tier, "")
    symbol = project["symbol"]
    name = project.get("name") or ""
    vcs = (
        json.loads(project.get("vcs_json", "[]"))
        if isinstance(project.get("vcs_json"), str)
        else project.get("vcs", [])
    )

    lines = [
        f"{icon} <b>Alpha 首发 · ${symbol}</b> {icon}",
        f"📋 {label}",
        "",
        f"<b>{name}</b>" if name else "",
    ]

    if project.get("narrative_desc"):
        lines.append(f"💡 {project['narrative_desc']}")
    if project.get("narrative") and project["narrative"] != "unknown":
        lines.append(f"🏷 叙事: {project['narrative']}")
    lines.append("")

    if project.get("fdv"):
        lines.append(f"📊 FDV: {format_mcap(project['fdv'])}")
    if project.get("circulating_mcap"):
        lines.append(f"📊 流通市值: {format_mcap(project['circulating_mcap'])}")
    if project.get("open_price"):
        lines.append(f"💰 预估开盘价: {format_price(project['open_price'])}")
    if project.get("total_supply") and project.get("circulating_supply"):
        ratio = project["circulating_supply"] / project["total_supply"] * 100
        lines.append(f"📦 初始流通: {ratio:.1f}%")

    if vcs:
        lines.append("")
        lines.append("🏛 <b>机构</b>")
        for vc in vcs[:5]:
            is_tier1 = any(tier1 in vc.lower() for tier1 in TIER1_VCS)
            lines.append(f"  {'⭐' if is_tier1 else '·'} {vc}")

    if project.get("is_darling"):
        lines.append("")
        lines.append("🔥 <b>币安亲儿子</b>")

    if project.get("tier_reason"):
        lines.append("")
        lines.append(f"🎯 {project['tier_reason']}")

    lines.append("")
    lines.append(f"<i>📌 来源: {project.get('source', 'binance')}</i>")
    if project.get("raw_text"):
        lines.append(f"<i>{project['raw_text'][:120]}</i>")

    return "\n".join(line for line in lines if line is not None)


def format_countdown(project: dict, minutes: int) -> str:
    icon = TIER_ICONS.get(project.get("tier", "C"), "⚪")
    time_text = f"{minutes // 60}h{minutes % 60}m" if minutes >= 60 else f"{minutes}m"
    lines = [
        f"{icon} <b>倒计时提醒</b>",
        f"<b>${project['symbol']}</b> · {project.get('name', '')}",
        f"⏰ 距上线还有 <b>{time_text}</b>",
    ]
    if project.get("fdv"):
        lines.append(f"FDV: {format_mcap(project['fdv'])}")
    if minutes <= 30:
        lines.append("🔔 <b>准备下单</b>")
    return "\n".join(lines)


def format_launch(project: dict, price: float, mcap: float, fdv: float) -> str:
    lines = [
        f"🚀 <b>${project['symbol']} 已上线</b>",
        f"开盘价: <b>{format_price(price)}</b>",
        f"流通市值: <b>{format_mcap(mcap)}</b>",
        f"FDV: <b>{format_mcap(fdv)}</b>",
    ]
    return "\n".join(lines)


def format_periodic(project: dict, index: int, price: float, mcap: float, change_pct: float) -> str:
    arrow = "📈" if change_pct > 0 else "📉"
    minutes = 30 * index
    lines = [
        f"⏱ <b>${project['symbol']} · +{minutes}min</b>",
        f"流通市值: {format_mcap(mcap)} ({arrow} {change_pct:+.1f}%)",
        f"当前价: {format_price(price)}",
    ]
    if change_pct >= 100:
        lines.append("💡 <b>已翻倍，考虑分批止盈</b>")
    elif change_pct <= -30:
        lines.append("⚠️ 跌幅较大，评估是否止损")
    return "\n".join(lines)


def format_anomaly(project: dict, anomaly_type: str, price: float, change_pct: float) -> str:
    emoji = {"double": "🚀", "halve": "🔻"}.get(anomaly_type, "⚡")
    desc = {"double": "市值翻倍", "halve": "市值腰斩"}.get(anomaly_type, "异动")
    return (
        f"{emoji} <b>${project['symbol']} {desc}</b>\n"
        f"变化: {change_pct:+.1f}%\n"
        f"当前价: {format_price(price)}"
    )


def format_trade_result(result: dict) -> str:
    status = result.get("status", "UNKNOWN")
    side = str(result.get("side", "")).upper()
    symbol = result.get("base_symbol", "")
    quote = result.get("quote_symbol", "")
    exchange = result.get("exchange", "")
    market = result.get("market_symbol", "")

    side_label = "买入" if side == "BUY" else "卖出"
    lines = [
        f"💱 <b>交易{side_label}</b> · {status}",
        f"交易对: <b>{symbol}/{quote}</b>",
    ]

    if exchange:
        lines.append(f"交易所: {exchange}")
    if market:
        lines.append(f"市场: {market}")

    if result.get("filled_base_amount"):
        lines.append(f"成交数量: {result['filled_base_amount']:.8f} {symbol}")
    if result.get("filled_quote_amount"):
        lines.append(f"成交金额: {result['filled_quote_amount']:.4f} {quote}")
    if result.get("average_price"):
        lines.append(f"成交均价: {format_price(result['average_price'])}")

    message = result.get("message")
    if message:
        lines.append(f"说明: {message}")
    return "\n".join(lines)
