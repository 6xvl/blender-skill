# blender-skill

A Claude skill for scripting Blender (rigging, animation, export) plus a multi-instance Blender MCP bridge that updates itself.

## Install

Clone once, then run the installer. It copies the skill, installs the Blender addon, and prints the MCP command.

```bash
git clone https://github.com/6xvl/blender-skill && cd blender-skill && python install.py --addon
```

Then register the bridge with your AI tool:

| Tool | One-line command |
|---|---|
| Claude Code | `claude mcp add blender -- uv run --with "mcp>=1.26,<2" --with httpx --with requests --with pydantic python "/path/to/blender-skill/mcp/run.py"` |
| Codex / other MCP clients | Add a server with command `uv` and args `run --with "mcp>=1.26,<2" --with httpx --with requests --with pydantic python /path/to/blender-skill/mcp/run.py` |
| Skill only (Codex or any agent that reads SKILL.md) | `python install.py --dest /path/to/your/skills/blender` |

The `--dest` path for Codex and other agents depends on where they load skills from. Point it at that folder.

## Use it

1. Open Blender. The addon starts its MCP server on the first free port from 9876 up.
2. In your AI session, ask for `list_blenders`. It shows every open Blender and marks the one this session uses.
3. Call `use_blender(port)` to switch. Each session can point at a different Blender.

Set `BLENDER_MCP_NO_UPDATE=1` to stop the bridge pulling updates on start. Set `BLENDER_MCP_ALLOW_TELEMETRY=1` to turn upstream telemetry back on (it is off by default).

## Layout

- `SKILL.md`: the Blender workflow reference the agent reads.
- `mcp/run.py`: the bridge. Lists and switches between Blender instances, self-updates from git, and copies the addon when it changes.
- `mcp/blender_mcp/`: the vendored MCP package (MIT, see `mcp/LICENSE-mcp-for-blender.txt`).
- `addon/blender_mcp_multi.py`: the Blender addon with per-process port allocation and a registry file.
- `tools/`: helper scripts used by the skill.
- `install.py`: copies the skill and addon, prints the registration command.

## Updating

The bridge runs `git fetch` and a fast-forward merge each time it starts, then copies a newer addon into Blender. Restart Claude and Blender after an update to load them.
