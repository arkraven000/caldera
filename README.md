[![Release](https://img.shields.io/badge/dynamic/json?color=blue&label=Release&query=tag_name&url=https%3A%2F%2Fapi.github.com%2Frepos%2Fmitre%2Fcaldera%2Freleases%2Flatest)](https://github.com/mitre/caldera/releases/latest)
[![Testing Status](https://github.com/mitre/caldera/actions/workflows/quality.yml/badge.svg?branch=master)](https://github.com/mitre/caldera/actions/workflows/quality.yml?query=branch%3Amaster)
[![Security Status](https://github.com/mitre/caldera/actions/workflows/security.yml/badge.svg?branch=master)](https://github.com/mitre/caldera/actions/workflows/security.yml?query=branch%3Amaster)
[![codecov](https://codecov.io/gh/mitre/caldera/branch/master/graph/badge.svg)](https://codecov.io/gh/mitre/caldera)
[![Documentation Status](https://readthedocs.org/projects/caldera/badge/?version=stable)](http://caldera.readthedocs.io/?badge=stable)

# MITRE Caldera&trade;

MITRE Caldera&trade; is a cyber security platform designed to easily automate adversary emulation, assist manual red-teams, and automate incident response.

It is built on the [MITRE ATT&CK™ framework](https://attack.mitre.org/) and is an active research project at MITRE.

The framework consists of two components:

1) **The core system**. This is the framework code, consisting of what is available in this repository. Included is
an asynchronous command-and-control (C2) server with a REST API and a web interface.
2) **Plugins**. These repositories expand the core framework capabilities and providing additional functionality. Examples include agents, reporting, collections of TTPs and more.

## Resources & Socials
* 📜 [Documentation, training, and use-cases](https://caldera.readthedocs.io/en/latest/)
* 🎬 [Tutorial Videos](https://www.youtube.com/playlist?list=PLF2bj1pw7-ZvLTjIwSaTXNLN2D2yx-wXH)
* ✍️ [Caldera's blog](https://medium.com/@mitrecaldera/welcome-to-the-official-mitre-caldera-blog-page-f34c2cdfef09)
* 🌐 [Homepage](https://caldera.mitre.org)

### User Survey

It is always incredibly helpful for our team to hear from users about their Caldera use cases and the value that Caldera provides for their learning, research, or cyber security work. If you or your team uses Caldera significantly, we would greatly appreciate hearing from you.

📋 **Survey** - https://forms.office.com/g/ByBWxYTf8e

## Plugins

:star: Create your own plugin! Plugin generator: **[Skeleton](https://github.com/mitre/skeleton)** :star:

### Default
These plugins are supported and maintained by the Caldera team.
- **[Access](https://github.com/mitre/access)** (red team initial access tools and techniques)
- **[Atomic](https://github.com/mitre/atomic)** (Atomic Red Team project TTPs)
- **[Builder](https://github.com/mitre/builder)** (dynamically compile payloads)
- **[Caldera for OT](https://github.com/mitre/caldera-ot)** (ICS/OT capabilities for Caldera)
- **[Compass](https://github.com/mitre/compass)** (ATT&CK visualizations)
- **[Debrief](https://github.com/mitre/debrief)** (operations insights)
- **[Emu](https://github.com/mitre/emu)** (CTID emulation plans)
- **[Fieldmanual](https://github.com/mitre/fieldmanual)** (documentation)
- **[GameBoard](https://github.com/mitre/gameboard)** (visualize joint red and blue operations)
- **[Human](https://github.com/mitre/human)** (create simulated noise on an endpoint)
- **[Magma](https://github.com/mitre/magma)** (VueJS UI for Caldera v5)
- **[Manx](https://github.com/mitre/manx)** (shell functionality and reverse shell payloads)
- **[Response](https://github.com/mitre/response)** (incident response)
- **[Sandcat](https://github.com/mitre/sandcat)** (default agent)
- **[SSL](https://github.com/mitre/SSL)** (enable https for caldera)
- **[Stockpile](https://github.com/mitre/stockpile)** (technique and profile storehouse)
- **[Training](https://github.com/mitre/training)** (certification and training course)

### More
These plugins are ready to use but are not included by default and are not maintained by the Caldera team.
- **[Arsenal](https://github.com/mitre-atlas/arsenal)** (MITRE ATLAS techniques and profiles)
- **[BountyHunter](https://github.com/fkie-cad/bountyhunter)** (The Bounty Hunter)
- **[CalTack](https://github.com/mitre/caltack.git)** (embedded ATT&CK website)
- **[SAML](https://github.com/mitre/saml)** (SAML authentication)

## AI Integrations (Anthropic Claude)

This fork adds an opt-in **Anthropic Claude** integration layer so AI consumers — local Claude Code, hosted Claude agents, and Caldera itself — can drive adversary-emulation operations. Three independent variations are shipped side-by-side so you can pick the surface that fits each use-case, and **all three import the same safety module** so policy lives in one place.

| Variation | Where | Best for |
|---|---|---|
| **A — MCP server** | `plugins/mcp_server/` | A local operator running Claude Code on their laptop |
| **B — Standalone client** | `tools/claude_agent/` | Hosted Claude (Claude on the web) or any automation driving Caldera over REST |
| **C — In-server LLM planner** | `plugins/llm_planner/` | Letting Caldera itself decide the next ability each tick, autonomously |

### How it works

**Variation A — MCP server.** The `mcp_server` plugin exposes Caldera as a Model Context Protocol server. Local Claude Code connects (stdio or SSE) and gets read-only tools (`list_operations`, `list_abilities`, `get_facts`, `summarize_operation`) plus a gated mutation flow: `propose_next_link` mints a **single-use 60-second approval token** that `approve_and_execute_link` must consume before the link runs on an agent.

```bash
pip install -r plugins/mcp_server/requirements.txt
MCP_STDIO=1 python3 server.py --insecure --build
claude mcp add caldera --command python3 --args server.py --args --insecure
```

**Variation B — Standalone client.** `tools/claude_agent/` is a self-contained Python module that uses the Anthropic SDK's tool-use loop to drive a remote Caldera over its REST API. **Zero server-side changes.** The ability catalog is sent as a prompt-cached block, so subsequent ticks read the cache rather than re-paying for it.

```bash
pip install -r tools/claude_agent/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-... CALDERA_API_KEY=ADMIN123
python3 -m tools.claude_agent \
  --operation <op-id> --goal "enumerate users and sensitive files" --mode dry-run
```

Three modes: `dry-run` (default — model reasons, nothing executes), `interactive` (y/N/e prompt per mutating call), `auto` (unattended; refuses to start without `--allowlist`).

**Variation C — In-server LLM planner.** `plugins/llm_planner/` registers a `LogicalPlanner` that delegates the per-tick "what next?" decision to Claude. The candidate list is pre-filtered by the allowlist before the model ever sees it, then the prompt forces a structured `choose_next_link` tool call so the model **cannot emit free-text actions** that reach an agent.

```bash
pip install -r plugins/llm_planner/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
# Add 'llm_planner' to plugins: in conf/default.yml, then create an operation
# with planner: llm. Defaults: dry_run=true, allowlist=[discovery,collection].
```

### Shared safety module — `app/ai_safety/`

Every variation imports from one place so policy edits are one-place:

- **`AbilityAllowlist`** — filter by `ability_id` / `tactic` / `technique_id` with explicit deny lists. Deny always wins.
- **`AuditLogger`** — JSONL per operation at `data/ai_audit/<operation_id>.jsonl`. Best-effort writes never raise into the planner loop.
- **`TargetScope`** — restrict to specific agent paws and CIDR ranges.
- **`get_async_client()`** — Anthropic SDK factory; raises `AnthropicNotConfigured` on missing key or missing SDK.
- **`CHOOSE_NEXT_LINK_TOOL` / `CALDERA_TOOL_SPECS`** — JSONSchema tool definitions reused by every variation. A dispatch ↔ spec sync test prevents drift.

### Default safety posture

- **Dry-run by default.** Proposed links are marked `DISCARD`; nothing runs on any agent.
- **Allowlist required for autonomous mode.** Defaults to `tactics: [discovery, collection]`, denies `[impact]`. Auto mode refuses to start without at least one positive constraint.
- **Fail-closed.** Missing `ANTHROPIC_API_KEY`, missing SDK, or Anthropic API error halts the planner cleanly — it does NOT fall back to the atomic planner.
- **Single-use approval tokens** (MCP). 60-second TTL, bound to `(operation, link)`. Replay fails closed.
- **Audit log of every decision** — model reasoning, confidence, ability chosen, allowlist denials, tool errors, and Anthropic token usage.
- **Live execution is opt-in per operation.** Flip `dry_run: false` on the planner params (Variation C), pass `--mode interactive` or `--mode auto` (Variation B), or call `approve_and_execute_link` with a fresh token (Variation A).

### Tests and verification

`tests/ai_safety/` ships **58 passing tests** covering every variation end-to-end with stubbed externals:

```bash
python3 -m pytest tests/ai_safety/ -v --confcutdir=tests/ai_safety
```

For deep-dive docs see:
- [`app/ai_safety/README.md`](app/ai_safety/README.md) — shared safety primitives
- [`plugins/mcp_server/README.md`](plugins/mcp_server/README.md) — Variation A (local Claude Code via MCP)
- [`tools/claude_agent/README.md`](tools/claude_agent/README.md) — Variation B (standalone external client)
- [`plugins/llm_planner/README.md`](plugins/llm_planner/README.md) — Variation C (in-server planner)

> **Authorized use only.** These integrations are intended for adversary-emulation work in lab environments, on systems the operator is explicitly authorized to test. See [Security](#Security) for deployment guidance.

## Requirements

These requirements are for the computer running the core framework:

* Any Linux or MacOS
  * Python 3.10+ (with Pip3)
* Recommended hardware to run on is 8GB+ RAM and 2+ CPUs
* Recommended: [GoLang 1.24+](https://go.dev/doc/install) to dynamically compile GoLang-based agents.
* NodeJS (v16+ recommended for v5 VueJS UI)

## Installation

Note: we HIGHLY recommend installing Caldera in a Python virtual environment to avoid issues with pip packages. You can use an existing environment if you wish or create a new one from scratch:
```Bash
python3 -m venv .calderavenv
source .calderavenv/bin/activate
```

Concise installation steps:
```Bash
git clone https://github.com/mitre/caldera.git --recursive
cd caldera
pip3 install -r requirements.txt
python3 server.py --insecure --build
```

Full steps:
Start by cloning this repository recursively, passing the desired version/release in x.x.x format. This will pull in all available plugins.
```Bash
git clone https://github.com/mitre/caldera.git --recursive --tag x.x.x
```

Next, install the PIP requirements:
```Bash
pip3 install -r requirements.txt
```

Finally, start the server.
```Bash
python3 server.py --insecure --build
```

The `--build` flag automatically installs any VueJS UI dependencies, bundles the UI into a dist directory and is served by the Caldera server. You will only have to use the `--build` flag again if you add any plugins or make any changes to the UI. Once started, log into http://localhost:8888 using the default credentials red/admin. Then go into Plugins -> Training and complete the capture-the-flag style training course to learn how to use Caldera.

If you prefer to not use the new VueJS UI, revert to Caldera v4.2.0. Correspondingly, do not use the `--build` flag for earlier versions as not required.

**Additionally, please note [security recommendations](#Security) for deploying Caldera.**

## Docker Installation

Local build:
```sh
git clone https://github.com/mitre/caldera.git --recursive
cd caldera
docker build --build-arg VARIANT=full -t caldera .
docker run -it -p 8888:8888 caldera
```

Adjust the port forwarding (`-p`) and build args (`--build-arg`) as desired to make ports accessible or change the Caldera variant. The ports that you expose depend on which contacts you plan on using (see `Dockerfile` and `docker-compose.yml` for reference).

Pre-Built Image (from GitHub Container Registry):
```sh
docker run -p 8888:8888 ghcr.io/mitre/caldera:latest
```
This container may be slightly outdated, we recommend building the container yourself.

To gracefully terminate your docker container, do the following:
```sh
# Find the container ID for your docker container running Caldera
docker ps

# Stop the container
docker stop <container ID>
```

There are two variants available, *full* and *slim*. The *slim* variant doesn't include files necessary for the `emu` and `atomic` plugins, which will be downloaded on-demand if the plugins are ever enabled. The *full* variant is suitable for operation in environments without an internet connection. Slim images on GHCR are prefixed with "slim".

**Docker Container Notes**
- The Caldera container will automatically generate keys/usernames/password on first start.
- If you wish to override the default configuration or avoid automatically generated keys/passwords, consider bind-mounting your own configuration file with the `-v <your_path>/conf.yml:/usr/src/app/conf/local.yml` flag.
- Data stored by Caldera is ephemeral by default. If you wish to make it persistent, use docker volumes and/or bind mounts (`-v <path_to_your_data_or_volume_name>:/usr/src/app/data/`). Ensure that the directory structure is the same as in the `data/` directory on GitHub, as Caldera will refuse to create these sub-directories if they are missing. Lastly, make sure that the configuration file is also made persistent to prevent issues with encryption keys.
- The `builder` plugin will not work within Docker.
- If you wish to modify data used by the `atomic` plugin, clone the `Atomic Red Team` repository outside the container, apply your modifications and bind-mount it (`-v`) to `/usr/src/app/plugins/atomic/data/atomic-red-team` within the container.
- If you wish to modify data used by `emu`, clone the `adversary_emulation_library` repository locally and bind-mount it (`-v`) to `/usr/src/app/plugins/emu/data/adversary-emulation-plans`.

**Additionally, please note [security recommendations](#Security) for deploying Caldera.**

### User Interface Development

If you'll be developing the UI, there are a few more additional installation steps.

**Requirements**  
* NodeJS (v16+ recommended)

**Setup**

1. Add the Magma submodule if you haven't already: `git submodule add https://github.com/mitre/magma`
1. Install NodeJS dependencies: `cd plugins/magma && npm install && cd ..`
1. Start the Caldera server with an additional flag: `python3 server.py --uidev localhost`

Your Caldera server is available at http://localhost:8888 as usual, but there will now be a hot-reloading development server for the VueJS front-end available at http://localhost:3000. Both logs from the server and the front-end will display in the terminal you launched the server from.

## Security

The Caldera team highly reccommends standing up the Caldera server on a secure environment/network, and not exposing it to the internet. The Caldera server does not have a hardened and thoroughly pentested web application interface, but only basic authentication and security features. Both MITRE and MITRE's US Government sponsors nearly exclusively only use Caldera on secure environments and do not rely on Caldera's own security protocols for proper cyber security.

### Vulnerability Disclosures

Refer to our [Vulnerability Disclosure Documentation](SECURITY.md) for submitting bugs.

#### Recent Vulnerability Disclosures

`🚨Security Notice🚨`: (17 Feb 2025 10:00 EST) Please pull v5.1.0+ for a recent security patch for [CVE-2025-27364](https://www.cve.org/CVERecord?id=CVE-2025-27364). Please update your Caldera instance, especially if you host Caldera on a publicly accessible network. [Vulnerability walkthrough.](https://medium.com/@mitrecaldera/mitre-caldera-security-advisory-remote-code-execution-cve-2025-27364-5f679e2e2a0e)

## Contributing

Refer to our [contributor documentation](CONTRIBUTING.md).

## Licensing

To discuss licensing opportunities, please reach out to caldera@mitre.org or directly to [MITRE's Technology Transfer Office](https://www.mitre.org/about/corporate-overview/contact-us#technologycontact).

## Caldera Benefactor Program

If you are interested in partnering to support, sustain, and evolve MITRE Caldera&trade;'s open source capabilities, please contact us at caldera@mitre.org.
