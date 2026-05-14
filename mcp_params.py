import os
from dotenv import load_dotenv
from market import is_paid_polygon, is_realtime_polygon

load_dotenv()

brave_env = {"BRAVE_API_KEY": os.getenv("BRAVE_API_KEY", "")}
polygon_api_key = os.getenv("POLYGON_API_KEY")


def _accounts_env(session_id: str) -> dict[str, str]:
    """Env for subprocesses that should see the active session's session_id."""
    env = {k: v for k, v in os.environ.items() if v is not None}
    env["SESSION_ID"] = session_id
    return env


def _market_mcp() -> dict:
    if is_paid_polygon or is_realtime_polygon:
        return {
            "command": "uvx",
            "args": ["--from", "git+https://github.com/polygon-io/mcp_polygon@v0.1.0", "mcp_polygon"],
            "env": {"POLYGON_API_KEY": polygon_api_key or ""},
        }
    return {"command": "uv", "args": ["run", "market_server.py"]}


def trader_mcp_server_params(session_id: str) -> list[dict]:
    """MCP servers exposed to a Trader agent: accounts + market data."""
    return [
        {
            "command": "uv",
            "args": ["run", "accounts_server.py"],
            "env": _accounts_env(session_id),
        },
        _market_mcp(),
    ]


def researcher_mcp_server_params(name: str, session_id: str) -> list[dict]:
    """MCP servers exposed to the Researcher sub-agent: fetch, web search, per-session memory."""
    memory_path = f"file:./memory/{session_id}_{name.lower()}.db"
    return [
        {"command": "uvx", "args": ["mcp-server-fetch"]},
        {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env": brave_env,
        },
        {
            "command": "npx",
            "args": ["-y", "mcp-memory-libsql"],
            "env": {"LIBSQL_URL": memory_path},
        },
    ]
