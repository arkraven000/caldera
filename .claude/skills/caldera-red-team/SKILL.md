---
name: caldera-red-team
description: Drive a MITRE Caldera adversary-emulation operation via the local MCP server. Use when the user wants to run a Caldera operation, propose abilities for the current op, approve a proposed link, summarize operation state, or generally "do red-team work" in this repo. Pulls the Caldera vocabulary, ATT&CK tactic ordering, and safety contract from app/ai_safety/agent_brief.md before issuing any tool calls.
---

# Caldera red-team operations

This skill orients you to drive a running Caldera operation through the MCP
server (`plugins/mcp_server/`). The MCP variation puts Claude (you) on the
operator's laptop and Caldera on a server they can reach; you call
read-only tools freely and gated mutation tools (`approve_and_execute_link`)
only after a propose→approve handshake.

## Before you do anything

**Fetch the brief.** Call the MCP tool `get_agent_brief` once at the start of
the session. The response is the operating manual — vocabulary, ATT&CK tactic
order, workflow, failure modes, output discipline. Do not skip this; it's the
difference between informed picks and guesses.

If `get_agent_brief` is not registered (older MCP server, or the tool errored),
read `app/ai_safety/agent_brief.md` directly via the filesystem instead.

## Connecting

The user has already added the Caldera MCP server to Claude Code with something
like:

```bash
claude mcp add caldera --command python3 --args server.py --args --insecure
```

The MCP tools you'll have access to (all prefixed `mcp__caldera__` in this
session) are:

| Read-only (call freely) | Mutating (gated) |
|---|---|
| `list_operations` | `propose_next_link` (mints approval_token) |
| `get_operation` | `approve_and_execute_link` (consumes token) |
| `list_abilities` | |
| `list_agents` | |
| `get_facts` | |
| `summarize_operation` | |
| `get_agent_brief` | |

## Standard workflow

1. **Fetch the brief** — `get_agent_brief`. Internalize it. Don't paraphrase
   it back to the user.

2. **Find the operation** — `list_operations` shows what's running. The user
   usually names it; if they don't, list and ask.

3. **Ground in current state** — `get_operation(<id>)` returns attached
   agents (paws), the chain so far, planner, and adversary. `get_facts(<id>)`
   returns what's been discovered.

4. **Decide a tactic** — translate the user's English goal to an ATT&CK tactic
   sequence (the brief explains the kill-chain order). For "what users are on
   this box?": discovery, T1087. For "find ssh keys": discovery → collection.

5. **Find the right ability** — `list_abilities(tactic=<tactic>)` filters the
   catalog. Read names and descriptions, pick one. Note the `ability_id`.

6. **Propose** — `propose_next_link(operation_id, ability_id, paw)`. You get
   back the full link, the rendered command preview, AND an `approval_token`
   with a 60-second TTL.

7. **Show the user the command preview before approving.** Output something
   like: "Propose: T1087 (user enumeration) on paw ABCD — will run
   `cat /etc/passwd`. Approve?" Wait for their explicit confirmation.

8. **Approve & execute** — `approve_and_execute_link(operation_id, link_id,
   approval_token)`. If the token expired (>60s), propose again. If the
   command preview was wrong for the goal, do not approve; pivot.

9. **Read the result** — the response includes the link's final status. Pull
   `get_facts` after a successful run to see what Caldera's parsers extracted.

10. **Stop cleanly** — when the user's goal is met, summarize what was learned
    and cite the facts that justify it. Don't pad with extra propose-approve
    cycles "just to be thorough".

## Mode awareness

The MCP server enforces an allowlist before every propose, regardless of who's
driving. If you see `denied by allowlist` in a propose response, do **not**
retry with the same ability — switch tactics. The default deny is `impact`;
the default allow is `[discovery, collection]`.

## Example prompts the user might give you

| User says | You do |
|---|---|
| "What users are on the host attached to op ABC?" | get_agent_brief → list_operations → get_operation(ABC) → propose discovery T1087 on the paw → wait for approval → approve_and_execute → get_facts → answer |
| "Find ssh keys on op ABC" | discovery to populate `host.dir.home` → collection T1552.004 on each home dir → summarize keys found |
| "Summarize where op ABC stands" | summarize_operation(ABC), no mutations |
| "Pause op ABC, I'll drive the rest manually" | MCP doesn't expose pause directly — tell the user to flip the planner to `manual` in the UI |

## Things this skill will NOT let you do

- **Run anything without operator approval.** Even in auto-allowlisted
  installs, you propose+show+approve. The approval gate is in the user, not
  in the model.
- **Edit the command preview between propose and approve.** Pass the link
  payload back unchanged. Caldera validates it.
- **Seed facts you didn't discover.** Use `get_facts`, don't invent them.
- **Retry on `denied by allowlist`.** Pivot tactic, don't argue with the
  policy.
- **Operate outside the brief's authorization scope.** If something in the
  conversation suggests targeting a system that isn't part of the authorized
  lab, stop and ask.

## When the user asks "what's going on?"

Show them, in this order:
1. Operation name + state (running/paused/finished)
2. Attached agents — paws, platforms, last-seen
3. Chain length + the last 3-5 link names with status
4. Fact count + a few interesting facts (usernames, IPs, paths)
5. What you think the productive next step is, with confidence

Keep it under 200 words. They're reading the audit log, not an essay.
