"""Install the Blender skill and MCP bridge.

    python install.py [--dest DIR] [--addon] [--mcp-config]

--dest DIR     skills folder to copy SKILL.md and tools/ into (default: ~/.claude/skills/blender).
               Run from inside the cloned repo, the bridge stays in place and is used directly.
--addon        copy addon/blender_mcp_multi.py into every Blender addons folder found (restart Blender).
--mcp-config   print the command that registers the bridge with your AI tool.
"""
import argparse
import glob
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DEST = os.path.join(os.path.expanduser("~"), ".claude", "skills", "blender")


def copy_skill(dest: str) -> None:
    if os.path.abspath(dest) == HERE:
        print(f"skill already lives at {HERE}")
        return
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(os.path.join(HERE, "SKILL.md"), os.path.join(dest, "SKILL.md"))
    shutil.copytree(os.path.join(HERE, "tools"), os.path.join(dest, "tools"), dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    print(f"skill copied to {dest}")


def install_addon() -> None:
    src = os.path.join(HERE, "addon", "blender_mcp_multi.py")
    found = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender", "*", "scripts", "addons"))
    if not found:
        print("no Blender addons folder found; copy addon/blender_mcp_multi.py into scripts/addons/addon.py by hand")
        return
    for addons in found:
        shutil.copy2(src, os.path.join(addons, "addon.py"))
        print(f"addon installed to {addons} (restart Blender)")


def mcp_command(bridge: str) -> str:
    return (f'uv run --with "mcp>=1.26,<2" --with httpx --with requests --with pydantic '
            f'python "{bridge}"')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--addon", action="store_true")
    ap.add_argument("--mcp-config", action="store_true")
    args = ap.parse_args()

    copy_skill(args.dest)
    if args.addon:
        install_addon()
    bridge = os.path.join(HERE, "mcp", "run.py")
    if args.mcp_config or args.addon:
        print("\nRegister the bridge with your AI tool:")
        print(f"  Claude Code:  claude mcp add blender -- {mcp_command(bridge)}")
        print(f"  Other tools:  command = uv, args = {mcp_command(bridge).split()[1:]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
