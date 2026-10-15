"""The bridge's own look script, sent straight to the addon socket (the MCP bridge process died).

    python -I look.py out.png '{"mode": "frames", "frames": [1, 31], "view": [0, -1, 0.1], "target": ["Cube.005"], "shading": "solid", "max_size": 1600}'
"""
import glob
import json
import os
import socket
import sys

pkg = max(glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\uv\cache\archive-v0\*\Lib\site-packages\blender_mcp")), key=os.path.getmtime)
sys.path.insert(0, os.path.dirname(pkg) + r"\blender_mcp")
import blender_scripts  # noqa: E402  (a plain module: only needs json)

out = os.path.abspath(sys.argv[1])
args = {"mode": "viewport", "target": None, "views": None, "distance": None, "shading": None, "frames": None,
        "frame_count": 6, "view": None, "image": None, "max_size": 768, **json.loads(sys.argv[2]), "filepath": out}
code = blender_scripts.build(blender_scripts.LOOK, args)
with socket.create_connection(("127.0.0.1", 9876), timeout=10) as sock:
    sock.settimeout(170)
    sock.sendall(json.dumps({"type": "execute_code", "params": {"code": code}}).encode())
    data = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
        try:
            json.loads(data.decode())
            break
        except ValueError:
            continue
reply = json.loads(data.decode())
if reply.get("status") == "error":
    sys.exit("BLENDER ERROR: " + str(reply.get("message")))
info = blender_scripts.parse_result(reply["result"]["result"])
print({k: v for k, v in info.items() if k != "filepath"})
