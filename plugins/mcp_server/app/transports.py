"""MCP transports: stdio (for local Claude Code) and SSE-over-aiohttp (for remote).

We import the MCP SDK lazily inside the registration functions so the plugin can
gracefully degrade when the SDK is not installed.
"""

import logging
import os

from aiohttp import web


log = logging.getLogger(__name__)


def register_sse_routes(application, server) -> None:
    """Mount the MCP SSE transport on the running aiohttp application.

    Binds:
        GET  /plugin/mcp_server/sse       — opens the SSE event stream
        POST /plugin/mcp_server/messages  — JSON-RPC requests from the client
    """
    try:
        from mcp.server.sse import SseServerTransport  # type: ignore
    except ImportError:
        log.warning('mcp_server: mcp.server.sse not available; SSE transport disabled')
        application.router.add_get('/plugin/mcp_server/sse', _sse_disabled)
        return

    transport = SseServerTransport('/plugin/mcp_server/messages')

    async def sse_handler(request: web.Request):
        if not _request_is_authorized(request):
            return web.Response(status=401, text='missing or invalid bearer token')
        # The aiohttp <-> MCP SDK bridge is intentionally minimal here.
        # In production wire request.transport.{recv,send} into transport.connect_sse().
        return web.Response(status=501,
                            text='SSE transport scaffolded; complete the SDK bridge per mcp docs')

    async def messages_handler(request: web.Request):
        if not _request_is_authorized(request):
            return web.Response(status=401, text='missing or invalid bearer token')
        return web.Response(status=501,
                            text='SSE message handler scaffolded; complete the SDK bridge per mcp docs')

    application.router.add_get('/plugin/mcp_server/sse', sse_handler)
    application.router.add_post('/plugin/mcp_server/messages', messages_handler)
    log.info('mcp_server: SSE routes registered')


async def maybe_start_stdio(server) -> None:
    try:
        from mcp.server.stdio import stdio_server  # type: ignore
    except ImportError:
        log.warning('mcp_server: mcp.server.stdio not available; stdio transport disabled')
        return
    log.info('mcp_server: starting stdio transport')
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def _sse_disabled(request: web.Request) -> web.Response:
    return web.Response(status=503, text='MCP SDK not installed; install with `pip install mcp`')


def _request_is_authorized(request) -> bool:
    """Bearer-token gate for the SSE transport.

    Disabled by default so localhost development works without configuration. Set
    MCP_BEARER_TOKEN in the environment to require it. Bind to loopback if you do
    not require the bearer token.
    """
    required = os.environ.get('MCP_BEARER_TOKEN')
    if not required:
        return True
    auth = request.headers.get('Authorization', '')
    return auth == f'Bearer {required}'
