"""Standalone scheduler for the 4 default traders.

This entrypoint is for local dev/CLI (`uv run trading_floor.py`). The hosted
Gradio app drives traders through its own per-session loop in `app.py` — this
module only provides the roster + the simple "run forever every N minutes" loop.
"""

from typing import List
import asyncio
import os

from dotenv import load_dotenv
from agents import add_trace_processor

from traders import Trader
from tracers import LogTracer
from market import is_market_open
from accounts import LOCAL_SESSION_ID
from session import ensure_memory_dir

load_dotenv(override=True)

RUN_EVERY_N_MINUTES = int(os.getenv("RUN_EVERY_N_MINUTES", "60"))
RUN_EVEN_WHEN_MARKET_IS_CLOSED = (
    os.getenv("RUN_EVEN_WHEN_MARKET_IS_CLOSED", "false").strip().lower() == "true"
)
USE_MANY_MODELS = os.getenv("USE_MANY_MODELS", "false").strip().lower() == "true"

names = ["Warren", "George", "Ray", "Cathie"]
lastnames = ["Patience", "Bold", "Systematic", "Crypto"]

if USE_MANY_MODELS:
    model_names = [
        "gpt-4.1-mini",
        "deepseek-chat",
        "gemini-2.5-flash-preview-04-17",
        "grok-3-mini-beta",
    ]
    short_model_names = ["GPT 4.1 Mini", "DeepSeek V3", "Gemini 2.5 Flash", "Grok 3 Mini"]
else:
    model_names = ["gpt-4o-mini"] * 4
    short_model_names = ["GPT 4o mini"] * 4


def create_traders(session_id: str = LOCAL_SESSION_ID) -> List[Trader]:
    return [
        Trader(name, lastname, model_name, session_id=session_id)
        for name, lastname, model_name in zip(names, lastnames, model_names)
    ]


async def run_every_n_minutes():
    ensure_memory_dir()
    add_trace_processor(LogTracer())
    traders = create_traders(LOCAL_SESSION_ID)
    while True:
        if RUN_EVEN_WHEN_MARKET_IS_CLOSED or is_market_open():
            await asyncio.gather(*[trader.run() for trader in traders])
        else:
            print("Market is closed, skipping run")
        await asyncio.sleep(RUN_EVERY_N_MINUTES * 60)


if __name__ == "__main__":
    print(f"Starting scheduler (session=local) to run every {RUN_EVERY_N_MINUTES} minutes")
    asyncio.run(run_every_n_minutes())
