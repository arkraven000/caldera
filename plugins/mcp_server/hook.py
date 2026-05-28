"""mcp_server plugin entry point.

Exposes Caldera as a Model Context Protocol server so local Claude Code (or any MCP
client) can drive operations. Two transports are supported:

- STDIO: when MCP_STDIO=1, an asyncio task starts the MCP server on stdin/stdout.
  This is the standard way Claude Code connects to a server it launches itself.
- SSE: when an aiohttp server is running (normal Caldera mode), the plugin registers
  GET /plugin/mcp_server/sse and POST /plugin/mcp_server/messages so a remote client
  can connect over HTTP.

The plugin gracefully no-ops if the `mcp` Python SDK is not installed — the rest of
Caldera continues to run.
"""

import asyncio
import logging
import os

name = 'mcp_server'
description = 'MCP bridge for Claude Code and other MCP clients to drive Caldera operations.'
address = '/plugin/mcp_server/gui'
access = None

log = logging.getLogger(__name__)


async def enable(services):
    try:
        from plugins.mcp_server.app.mcp_app import build_mcp_server
        from plugins.mcp_server.app.transports import register_sse_routes, maybe_start_stdio
    except ImportError as exc:
        log.warning('mcp_server disabled: %s. Install with `pip install mcp` to enable.', exc)
        return

    server = build_mcp_server(services)
    register_sse_routes(services['app_svc'].application, server)
    if os.environ.get('MCP_STDIO') == '1':
        asyncio.create_task(maybe_start_stdio(server))
        log.info('mcp_server: stdio transport scheduled (MCP_STDIO=1)')
    log.info('mcp_server: SSE transport mounted at /plugin/mcp_server/sse')
