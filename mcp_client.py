"""Small synchronous wrapper around the FastMCP asynchronous client."""
import asyncio
import json
import os
from typing import Any

from dotenv import load_dotenv
from fastmcp import Client

load_dotenv()


class MCPClient:
    def __init__(self, url: str | None = None):
        self.mode = os.getenv("MCP_MODE", "http").strip().lower()
        if self.mode == "inprocess":
            # Streamlit Community Cloud runs the app without a separate local MCP
            # process. FastMCP's in-memory transport still exercises MCP tool calls.
            from mcp_server import mcp
            self.transport = mcp
            self.url = None
        elif self.mode == "http":
            self.url = url or os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp")
            self.transport = self.url
        else:
            raise ValueError("MCP_MODE must be 'http' or 'inprocess'.")

    async def _call_async(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        async with Client(self.transport) as client:
            result = await client.call_tool(tool_name, arguments)
        structured = getattr(result, "structured_content", None)
        if structured is not None:
            # FastMCP wraps top-level list return values in a result field.
            if isinstance(structured, dict) and set(structured) == {"result"}:
                return structured["result"]
            return structured
        # FastMCP versions can expose JSON results in a text content block.
        for block in getattr(result, "content", []):
            text = getattr(block, "text", None)
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        return result

    def call(self, tool_name: str, **arguments: Any) -> Any:
        return asyncio.run(self._call_async(tool_name, arguments))
