from .constants import HOT_NARRATIVES, TIER1_VCS, WEAK_NARRATIVES


def count_vc_tier(vcs: list[str], vc_list: list[str]) -> int:
    count = 0
    vcs_lower = [v.lower() for v in vcs]
    for tier_vc in vc_list:
        if any(tier_vc in vc for vc in vcs_lower):
            count += 1
    return count


def rate_project(
    circ_mcap: float | None,
    fdv: float | None,
    vcs: list[str],
    narrative: str,
    is_darling: bool,
) -> dict[str, str | list[str]]:
    t1 = count_vc_tier(vcs, TIER1_VCS)
    hot = narrative in HOT_NARRATIVES
    weak = narrative in WEAK_NARRATIVES
    circ_mcap = circ_mcap or 0
    fdv = fdv or 0

    warnings = []
    if weak:
        warnings.append(f"⚠️ {narrative} 历史破发率较高")

    if is_darling:
        return {"tier": "S", "reason": "币安亲儿子(YZi/Binance Labs/CZ)", "warnings": warnings}
    if hot and t1 >= 1 and fdv < 500_000_000:
        return {"tier": "S", "reason": f"热叙事({narrative})+ Tier1 VC", "warnings": warnings}
    if t1 >= 2 and circ_mcap < 50_000_000 and fdv < 300_000_000:
        return {"tier": "S", "reason": "≥2家 Tier1 中盘", "warnings": warnings}
    if t1 >= 1 and circ_mcap < 10_000_000 and fdv < 100_000_000:
        return {"tier": "S", "reason": "Tier1 微盘", "warnings": warnings}
    if hot and circ_mcap < 10_000_000 and fdv < 50_000_000:
        return {"tier": "S", "reason": f"热叙事({narrative})微盘", "warnings": warnings}

    if t1 >= 1 and circ_mcap < 20_000_000 and fdv < 200_000_000:
        return {"tier": "A", "reason": "Tier1 小盘", "warnings": warnings}
    if circ_mcap < 50_000_000 and fdv < 500_000_000:
        return {"tier": "B", "reason": "中盘", "warnings": warnings}

    return {"tier": "C", "reason": "大盘/弱信号", "warnings": warnings}
