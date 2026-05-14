---
title: Trading Floor
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Four AI traders compete on a simulated stock market.
---

# Trading Floor

A live, multi-agent trading-floor demo built on the OpenAI Agents SDK and MCP.
Four AI personas — Warren, George, Ray, and Cathie — each run their own
research → analysis → trade loop on a simulated portfolio. Watch them think,
research the web, and place orders in real time.

> Each visitor gets an isolated session with their own portfolios, holdings,
> and trade history. Nothing is shared across users.

## Run it locally

```bash
uv sync
uv run trading_floor.py     # CLI scheduler (uncapped, runs forever)
# or
uv run app.py               # Gradio UI on http://localhost:7860
```

Requires Python 3.12, [`uv`](https://docs.astral.sh/uv/), Node 20+ (for the
Brave-search and memory MCP servers), and a `.env` file (see `.env.example`).

## Architecture

- **Trader agent (×4)** — has tools for `buy_shares` / `sell_shares` /
  `change_strategy` (via `accounts_server.py` MCP) and a `Researcher` sub-agent.
- **Researcher sub-agent** — has Brave Search, Fetch, and a persistent
  Memory MCP (libsql) for cross-round recall.
- **Market data** — free end-of-day prices via `market_server.py` by default;
  paid Polygon MCP when `POLYGON_PLAN=paid` or `realtime`.

## Public-app guardrails

The hosted app caps every visitor session at **10 minutes** *or* **10 trading
rounds**, whichever hits first. Set via `SESSION_MAX_MINUTES` and
`MAX_RUNS_PER_SESSION`. The local CLI (`uv run trading_floor.py`) ignores
these caps.

## Deployed at

- Hosted: [https://huggingface.co/spaces/Olu-Victor/trading-floor](https://huggingface.co/spaces/Olu-Victor/trading-floor)
- Source: [https://github.com/Oluwaseyi-A/trading-floor](https://github.com/Oluwaseyi-A/trading-floor)

GitHub `main` auto-deploys to the HF Space via `.github/workflows/deploy-hf.yml`.

## License

MIT
