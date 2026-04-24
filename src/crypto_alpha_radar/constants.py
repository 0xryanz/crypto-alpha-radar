HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

BINANCE_ANNOUNCEMENT_API = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
COINGECKO_SEARCH_API = "https://api.coingecko.com/api/v3/search"
COINGECKO_COIN_API = "https://api.coingecko.com/api/v3/coins/{coin_id}"

ANNOUNCEMENT_CATALOG_IDS = [48, 161, 93]

TRIGGER_KEYWORDS = [
    "alpha",
    "空投",
    "airdrop",
    "tge",
    "token generation",
    "将上线",
    "will list",
    "will launch",
    "独家",
    "exclusive",
    "binance wallet",
    "hodler",
]

EXCLUDE_KEYWORDS = [
    "delisting",
    "delist",
    "下架",
    "deprecate",
    "退市",
    "maintenance",
    "维护",
    "launchpool",
    "megadrop",
    "buyback",
    "回购",
    "已完成",
    "完成结算",
    "perpetual contract",
    "futures will launch",
    "usdⓢ-margined",
    "coin-margined",
    "margin will add",
    "trading bots services",
    "trading pairs",
]

ALPHA_BOX_KEYWORDS = ["alpha box", "盲盒", "mystery box"]

TIER1_VCS = [
    "binance labs",
    "yzi labs",
    "coinbase ventures",
    "a16z",
    "andreessen horowitz",
    "paradigm",
    "polychain",
    "polychain capital",
    "sequoia",
    "sequoia china",
    "sequoia capital",
    "multicoin",
    "multicoin capital",
    "pantera",
    "pantera capital",
    "dragonfly",
    "dragonfly capital",
    "founders fund",
]

TIER2_VCS = [
    "abcde",
    "iosg",
    "hashkey",
    "okx ventures",
    "sevenx",
    "folius",
    "foresight",
    "hashed",
    "bitkraft",
    "framework",
    "framework ventures",
    "delphi",
    "delphi digital",
    "electric capital",
    "variant",
    "1kx",
    "placeholder",
    "animoca",
    "animoca brands",
    "jump",
    "jump crypto",
    "hack vc",
    "bain capital",
]

HOT_NARRATIVES = ["defi_perp", "ai_agent", "ai_defi", "defai", "zk_proof"]
WEAK_NARRATIVES = ["gamefi", "meme", "social"]
BINANCE_DARLING_KEYWORDS = ["yzi labs", "binance labs"]

TWITTER_OPPORTUNITY_KEYWORDS = [
    "binance",
    "listing",
    "will list",
    "launch",
    "tge",
    "airdrop",
    "token",
    "mainnet",
    "testnet",
    "partnership",
    "raising",
    "funding",
    "seed",
    "backed",
]

TWITTER_EXCLUDE_KEYWORDS = [
    "giveaway",
    "scam",
    "spam",
    "airdrop hunter",
    "pump",
    "signal group",
]

TWITTER_STOP_SYMBOLS = {
    "USD",
    "USDT",
    "USDC",
    "BTC",
    "ETH",
    "BNB",
    "X",
    "RT",
    "IMO",
    "NFA",
    "NFT",
    "AI",
}

TIER_ICONS = {"S": "🟢🟢🟢", "A": "🟡🟡", "B": "🟠", "C": "⚪"}
TIER_LABELS = {
    "S": "S 级(必研究)",
    "A": "A 级(值得看)",
    "B": "B 级(正常)",
    "C": "C 级(了解)",
}
