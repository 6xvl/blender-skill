"""Blender MCP bridge with multi-instance support and self-update.

- Lists every open Blender that runs the MCP addon (registry files plus a port scan) and lets
  each Claude session pick one: list_blenders / use_blender(port).
- Updates itself from git on start when this folder is a clone. Set BLENDER_MCP_NO_UPDATE=1 to skip.
- Telemetry is off by default here. Set BLENDER_MCP_ALLOW_TELEMETRY=1 to turn it back on.

Run through the installer's printed command, or directly:
    uv run --with "mcp>=1.26,<2" --with httpx --with requests --with pydantic python mcp/run.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
REGISTRY = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "blender-mcp", "instances")


def _log(msg: str) -> None:
    print(f"[blender-mcp] {msg}", file=sys.stderr)


def self_update() -> None:
    """Fast-forward this checkout from its remote. Silent and non-fatal when offline or not a clone."""
    if os.environ.get("BLENDER_MCP_NO_UPDATE") or not os.path.isdir(os.path.join(REPO, ".git")):
        return
    git = shutil.which("git")
    if not git:
        return
    try:
        before = subprocess.run([git, "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
        subprocess.run([git, "-C", REPO, "fetch", "--quiet"], capture_output=True, timeout=15)
        merged = subprocess.run([git, "-C", REPO, "merge", "--ff-only", "--quiet", "@{u}"], capture_output=True, text=True, timeout=15)
        after = subprocess.run([git, "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
        if merged.returncode == 0 and after != before:
            _log(f"updated {before[:7]} -> {after[:7]}; restart Claude to load the new bridge")
            _sync_addon()
    except (OSError, subprocess.SubprocessError):
        pass


def _sync_addon() -> None:
    """Copy the addon into Blender's addons folder when the repo copy is newer. Restart Blender to load it."""
    src = os.path.join(REPO, "addon", "blender_mcp_multi.py")
    base = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")
    if not os.path.isfile(src) or not os.path.isdir(base):
        return
    for version in sorted(os.listdir(base)):
        dest_dir = os.path.join(base, version, "scripts", "addons")
        if not os.path.isdir(dest_dir):
            continue
        dest = os.path.join(dest_dir, "addon.py")
        if not os.path.exists(dest) or os.path.getmtime(src) > os.path.getmtime(dest):
            shutil.copy2(src, dest)
            _log(f"addon copied to Blender {version}; restart Blender to load it")


self_update()
os.environ.setdefault("BLENDER_MCP_DISABLE_TELEMETRY", "" if os.environ.get("BLENDER_MCP_ALLOW_TELEMETRY") else "1")
sys.path.insert(0, HERE)

import blender_mcp.server as server  # noqa: E402


def _alive(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=0.5):
            return True
    except OSError:
        return False


def _current_port() -> int:
    conn = server._blender_connection
    if conn is not None:
        return conn.port
    _, port = server.resolve_connection(server.CLI_HOST, server.CLI_PORT)
    return port


def _instances() -> list[dict]:
    out = []
    if os.path.isdir(REGISTRY):
        for name in sorted(os.listdir(REGISTRY)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(REGISTRY, name), encoding="utf-8") as f:
                    info = json.load(f)
            except (OSError, ValueError):
                continue
            port = int(info.get("port", 0))
            info["alive"] = _alive(port)
            info["active"] = port == _current_port()
            out.append(info)
    # The registry is not always written, so also probe the default port range.
    known = {int(i.get("port", 0)) for i in out}
    for port in range(server.DEFAULT_PORT, server.DEFAULT_PORT + 20):
        if port not in known and _alive(port):
            out.append({"port": port, "file": "(no registry entry)", "alive": True, "active": port == _current_port()})
    return out


@server.mcp.tool()
def list_blenders() -> str:
    """List open Blenders running the MCP addon: port, open file, Blender version, and which one this session uses."""
    items = _instances()
    if not items:
        return "No Blender instances found. Open Blender with the MCP addon enabled."
    lines = []
    for i in items:
        mark = "*" if i["active"] else " "
        state = "up" if i["alive"] else "down"
        lines.append(f"{mark} port {i['port']}  {state}  Blender {i.get('blender', '?')}  pid {i.get('pid')}  {i.get('file', '?')}")
    return "\n".join(lines) + "\n(* = this session)"


@server.mcp.tool()
def use_blender(port: int) -> str:
    """Point this session at the Blender on `port` (see list_blenders). Resets the connection."""
    if not _alive(port):
        return f"Nothing is listening on port {port}. Run list_blenders to see what is up."
    server.CLI_PORT = port
    server._blender_connection = None
    return f"This session now uses the Blender on port {port}."


if __name__ == "__main__":
    server.main()
