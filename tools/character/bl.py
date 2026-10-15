"""Run a Python file inside the live Blender through the blender-mcp addon's socket.

    python -I bl.py script.py [timeout_seconds]
"""
import json
import socket
import sys

code = open(sys.argv[1], encoding="utf-8").read()
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 170
with socket.create_connection(("127.0.0.1", 9876), timeout=10) as sock:
    sock.settimeout(timeout)
    sock.sendall(json.dumps({"type": "execute_code", "params": {"code": code}}).encode())
    data = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        data += chunk
        try:
            reply = json.loads(data.decode())
            break
        except ValueError:
            continue
    else:
        reply = None
if not data:
    sys.exit("Blender closed the connection without answering")
reply = json.loads(data.decode())
if reply.get("status") == "error":
    sys.exit("BLENDER ERROR: " + str(reply.get("message")))
print(reply.get("result", {}).get("result", reply))
