import logging
from typing import List, Dict, Any
import json
import os
from pathlib import Path
from contextlib import AsyncExitStack

from aworld.mcp.server import MCPServer, MCPServerSse


async def run(mcp_servers: list[MCPServer]) -> List[Dict[str, Any]]:
    openai_tools = []
    for i, server in enumerate(mcp_servers):
        try:
            tools = await server.list_tools()
            for tool in tools:
                required = []
                properties = {}
                if tool.inputSchema and tool.inputSchema.get("properties"):
                    required = tool.inputSchema.get("required", [])
                    _properties = tool.inputSchema["properties"]
                    for param_name, param_info in _properties.items():
                        param_type = param_info["type"] if param_info["type"] != "str" else "string"
                        param_desc = param_info["description"] if param_info["description"] else ""
                        if param_type == "array":
                            # Handle array type parameters
                            item_type = param_info.get("items", {}).get("type", "string")
                            if item_type == "str":
                                item_type = "string"
                            properties[param_name] = {
                                "description": param_desc,
                                "type": param_type,
                                "items": {
                                    "type": item_type
                                }
                            }
                        else:
                            # Handle non-array type parameters
                            properties[param_name] = {
                                "description": param_desc,
                                "type": param_type
                            }
                        if param_info.get("required", False):
                            required.append(param_name)

                openai_function_schema = {
                    "name": f'{server.name}__{tool.name}',
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
                openai_tools.append({
                    "type": "function",
                    "function": openai_function_schema,
                })
            logging.info(f"✅ server #{i + 1} ({server.name}) connected success，tools: {len(tools)}")

        except Exception as e:
            logging.error(f"❌ server #{i + 1} ({server.name}) connect fail: {e}")
            return []

    return openai_tools


async def mcp_tool_desc_transform(tools: List[str] = None) -> List[Dict[str, Any]]:
    """Default implement transform framework standard protocol to openai protocol of tool description."""

    # Priority given to the running path.
    if os.path.exists(os.path.join(os.getcwd(), "mcp.json")):
        config_path = os.path.join(os.getcwd(), "mcp.json")
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.normpath(os.path.join(current_dir, "../config/mcp.json"))

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except Exception as e:
        logging.info(f"load mcp config fail: {e}")
        return []

    mcp_servers_config = config.get("mcpServers", {})

    server_configs = []
    for server_name, server_config in mcp_servers_config.items():
        if tools is None or server_name in tools:
            server_configs.append({
                "name": "mcp__" + server_name,
                "params": {"url": server_config["url"]}
            })

    if not server_configs:
        logging.info("not match mcp server")
        return []

    async with AsyncExitStack() as stack:
        servers = []
        for server_config in server_configs:
            server = MCPServerSse(
                name=server_config["name"],
                params=server_config["params"]
            )
            server = await stack.enter_async_context(server)
            servers.append(server)
        openai_tools = await run(servers)

    return openai_tools
