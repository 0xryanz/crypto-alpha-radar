import re

from .constants import ALPHA_BOX_KEYWORDS, EXCLUDE_KEYWORDS, TRIGGER_KEYWORDS


def is_trigger(title: str) -> tuple[bool, str | None]:
    title_lower = title.lower()
    for keyword in EXCLUDE_KEYWORDS:
        if keyword.lower() in title_lower:
            return False, f"排除: {keyword}"
    for keyword in ALPHA_BOX_KEYWORDS:
        if keyword.lower() in title_lower:
            return False, "Alpha Box 盲盒"
    for keyword in TRIGGER_KEYWORDS:
        if keyword.lower() in title_lower:
            return True, None
    return False, None


def extract_symbol(title: str) -> str | None:
    match = re.search(r"\(([A-Z0-9]{2,10})\)", title)
    if match:
        return match.group(1)

    match = re.search(r"（([A-Z0-9]{2,10})）", title)
    if match:
        return match.group(1)

    return None


def extract_name(title: str) -> str | None:
    patterns = [r"(?:上线|List|list|Launch|launch|featured)\s+([A-Za-z0-9 ]+?)\s*[\(（]"]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None
