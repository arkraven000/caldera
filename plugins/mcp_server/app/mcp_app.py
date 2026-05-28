"""Construct the MCP server and register Caldera tools."""

import logging
import os

from app.ai_safety import AbilityAllowlist, load_agent_brief
from plugins.mcp_server.app.tools import CalderaMCPTools


log = logging.getLogger(__name__)


def _load_allowlist_from_env() -> AbilityAllowlist:
    """Quick env-driven allowlist for first-run; production should load from conf/ai.yml."""
    tactics = [t.strip() for t in os.environ.get('MCP_ALLOWLIST_TACTICS', 'discovery,collection').split(',') if t.strip()]
    deny_tactics = [t.strip() for t in os.environ.get('MCP_DENY_TACTICS', 'impact').split(',') if t.strip()]
    return AbilityAllowlist(tactics=tactics, deny_tactics=deny_tactics)


def build_mcp_server(services):
    """Return an MCP FastMCP server with Caldera tools registered.

    The mcp SDK is imported lazily so the plugin can fail closed (and the rest of
    Caldera keep running) when the SDK is not installed.
    """
    from mcp.server.fastmcp import FastMCP  # type: ignore

    allowlist = _load_allowlist_from_env()
    audit_root = os.environ.get('MCP_AUDIT_DIR', 'data/ai_audit')
    require_approval = os.environ.get('MCP_REQUIRE_APPROVAL', '1') == '1'
    tools_facade = CalderaMCPTools(services, allowlist=allowlist, audit_root=audit_root,
                                   require_approval=require_approval)

    mcp = FastMCP('caldera-mcp')

    @mcp.tool()
    async def list_operations() -> list:
        """List all operations on the Caldera server."""
        return await tools_facade.list_operations()

    @mcp.tool()
    async def get_operation(operation_id: str) -> dict:
        """Get a single operation's state (agents, recent chain, planner)."""
        return await tools_facade.get_operation(operation_id)

    @mcp.tool()
    async def list_abilities(tactic: str = None, technique_id: str = None) -> list:
        """List ATT&CK abilities, optionally filtered by tactic or technique_id."""
        return await tools_facade.list_abilities(tactic=tactic, technique_id=technique_id)

    @mcp.tool()
    async def list_agents(operation_id: str = None) -> list:
        """List deployed agents, optionally restricted to a single operation."""
        return await tools_facade.list_agents(operation_id=operation_id)

    @mcp.tool()
    async def get_facts(operation_id: str) -> list:
        """List facts (discovered + seeded) for an operation."""
        return await tools_facade.get_facts(operation_id)

    @mcp.tool()
    async def propose_next_link(operation_id: str, ability_id: str, paw: str) -> dict:
        """Build a runnable link without executing it. Returns a one-shot approval_token
        (60s TTL) the client passes to approve_and_execute_link to actually run."""
        return await tools_facade.propose_next_link(operation_id, ability_id, paw)

    @mcp.tool()
    async def approve_and_execute_link(operation_id: str, link_id: str,
                                       approval_token: str) -> dict:
        """Execute a previously proposed link. Requires a valid approval_token from
        propose_next_link. Allowlist + audit log are always enforced."""
        return await tools_facade.approve_and_execute_link(operation_id, link_id, approval_token)

    @mcp.tool()
    async def summarize_operation(operation_id: str) -> dict:
        """One-shot natural-language summary of operation progress (read-only)."""
        return await tools_facade.summarize_operation(operation_id)

    @mcp.tool()
    async def get_agent_brief() -> str:
        """Return the Caldera red-team agent brief — vocabulary, ATT&CK tactic
        ordering, workflow, failure modes, and safety contract. Read this once
        at the start of every session before driving an operation. The brief
        is the operating manual every variation shares; both the standalone
        client and the in-server planner load it automatically, but the MCP
        variation hosts Claude on the client side so the client must fetch it."""
        return load_agent_brief() or '(agent_brief.md missing on the Caldera server)'

    return mcp
