import json
import os
import mcp
from mcp.client.stdio import stdio_client
from mcp import StdioServerParameters
from agents import FunctionTool


def _params(session_id: str) -> StdioServerParameters:
    env = {k: v for k, v in os.environ.items() if v is not None}
    env["SESSION_ID"] = session_id
    return StdioServerParameters(command="uv", args=["run", "accounts_server.py"], env=env)


async def list_accounts_tools(session_id: str):
    async with stdio_client(_params(session_id)) as streams:
        async with mcp.ClientSession(*streams) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            return tools_result.tools


async def call_accounts_tool(session_id: str, tool_name, tool_args):
    async with stdio_client(_params(session_id)) as streams:
        async with mcp.ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, tool_args)
            return result


async def read_accounts_resource(name, session_id: str):
    async with stdio_client(_params(session_id)) as streams:
        async with mcp.ClientSession(*streams) as session:
            await session.initialize()
            result = await session.read_resource(f"accounts://accounts_server/{name}")
            return result.contents[0].text


async def read_strategy_resource(name, session_id: str):
    async with stdio_client(_params(session_id)) as streams:
        async with mcp.ClientSession(*streams) as session:
            await session.initialize()
            result = await session.read_resource(f"accounts://strategy/{name}")
            return result.contents[0].text


async def get_accounts_tools_openai(session_id: str):
    openai_tools = []
    for tool in await list_accounts_tools(session_id):
        schema = {**tool.inputSchema, "additionalProperties": False}
        openai_tool = FunctionTool(
            name=tool.name,
            description=tool.description,
            params_json_schema=schema,
            on_invoke_tool=lambda ctx, args, toolname=tool.name, sid=session_id: call_accounts_tool(sid, toolname, json.loads(args)),
        )
        openai_tools.append(openai_tool)
    return openai_tools
