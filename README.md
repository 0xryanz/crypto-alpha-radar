# Crypto Alpha Radar

多源加密机会监控系统：监听 Binance 公告和 Twitter 账号，抽取代币机会，统一进入同一条评级与推送链路。

## 核心能力

- Binance 公告源：高频轮询 + 标题过滤 + 机会入库
- Twitter 账号源：多账号轮询 + 推文机会识别 + 候选入库
- AI 分析：可选 Anthropic / OpenAI（未配置则规则降级）
- 统一聚合：CoinGecko 拉取 FDV/流通市值/供应数据
- 统一评级：S/A/B/C
- 统一推送：Telegram（发现、倒计时、上线跟踪、异动）
- 交易执行（可选）：ccxt 多交易所路由，支持市价买卖（默认 dry-run）

## 安装与运行（uv）

### 1) 安装依赖

```bash
uv sync
```

### 2) 配置环境变量

```bash
cp .env.example .env
```

必填：

- `TG_BOT_TOKEN`
- `TG_CHAT_ID`

Twitter 监听（可选）：

- `TWITTER_ENABLED=true`
- `TWITTER_ACCOUNTS=cz_binance,lookonchain`

Twitter 认证（`twscrape` 必填，非官方 API）：

```bash
cp .twitter_accounts.example.json .twitter_accounts.json
# 填写你的 X 账号登录信息
```

或使用单账号环境变量（见 `.env.example` 里的 `TWITTER_LOGIN_*`）。

### 3) 初始化数据库

```bash
uv run alpha-radar init-db
```

### 4) 验证 Telegram

```bash
uv run alpha-radar test-tg
```

### 5) 验证 Twitter 抓取

```bash
uv run alpha-radar check-twitter
```

### 6) 启动

```bash
uv run alpha-radar run
```

### 7) 代码检查（Lint）

```bash
uv run ruff check .
```

## CLI

```bash
uv run alpha-radar --help
```

常用命令：

- `alpha-radar run`
- `alpha-radar run --no-startup-message`
- `alpha-radar init-db`
- `alpha-radar test-tg --message "..." --silent`
- `alpha-radar check-twitter`
- `alpha-radar check-llm`
- `alpha-radar trade-buy --symbol SOL --usdt 20 --exchange auto`
- `alpha-radar trade-sell --symbol SOL --amount 1 --exchange binance`
- `alpha-radar trade-orders --limit 20`
- `alpha-radar --env-file .env.systemd run`

## 主要配置

- 通用：`DB_PATH` `LOG_LEVEL` `LOG_FILE` `REQUEST_TIMEOUT_SECONDS`
- 公告：`ANNOUNCEMENT_POLL_INTERVAL` `ANNOUNCEMENT_FETCH_LIMIT`
- 聚合：`AGGREGATION_POLL_INTERVAL`
- 监控：`MONITOR_POLL_INTERVAL`
- AI：
  - `LLM_PROVIDER` (`anthropic|openai`)
  - Anthropic: `ANTHROPIC_API_KEY` `ANTHROPIC_BASE_URL` `ANTHROPIC_MODEL`
  - OpenAI: `OPENAI_API_KEY` `OPENAI_BASE_URL` `OPENAI_MODEL`
- Twitter：
  - `TWITTER_ENABLED`
  - `TWITTER_ACCOUNTS`
  - `TWITTER_POLL_INTERVAL`
  - `TWITTER_FETCH_LIMIT`
  - `TWITTER_INCLUDE_REPLIES`
  - `TWITTER_INCLUDE_RETWEETS`
  - `TWITTER_MIN_CONFIDENCE`
- Trading：
  - 开关：`TRADING_ENABLED` `TRADING_DRY_RUN`
  - 路由：`TRADING_EXCHANGES` `TRADING_DEFAULT_QUOTE`
  - 风控：`TRADING_MAX_ORDER_USDT` `TRADING_MAX_SLIPPAGE_BPS`
  - 自动买入：`TRADING_AUTO_BUY_ENABLED` `TRADING_AUTO_BUY_TIERS` `TRADING_AUTO_BUY_USDT`
  - 交易所凭证：`{EXCHANGE}_API_KEY` `{EXCHANGE}_API_SECRET` `{EXCHANGE}_API_PASSWORD`

## 项目结构

```text
src/crypto_alpha_radar/
├── adapters/          # 多数据源采集适配器
├── analyzers/         # 机会分析策略（LLM + 规则）
├── domain/            # 领域模型（SourceSignal/Opportunity）
├── trading/           # ccxt 交易路由与执行
├── pipeline.py        # 事件入库与候选项目生成
├── db.py              # SQLAlchemy ORM 与 repository 方法
├── integrations.py    # Binance/CoinGecko/Anthropic/Telegram API
├── llm_client.py      # Anthropic/OpenAI 统一调用
├── rating.py          # 评级规则
├── formatters.py      # TG 文案
├── service.py         # worker 编排
└── cli.py             # 命令行入口
```

## 说明

- 交易功能默认 `TRADING_DRY_RUN=true`，请先小额验证路由与风控后再开启真实下单

## License

MIT
