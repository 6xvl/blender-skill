#!/bin/bash
# usage: clip.sh Idle '"apron", "straps"' ['tie_swing keyword arguments' | -]
HERE=$(cd "$(dirname "$0")" && pwd -W)   # this folder, as a Windows path
# simulates the cloth pieces over the clip in slices, swings the tie (unless "-"), then bakes the clip
cat > run_piece.py <<PY
import bpy
p = r"$HERE/cloth_pieces.py"
ns = {"__name__": "cloth_pieces"}
exec(compile(open(p, encoding="utf-8").read(), p, "exec"), ns)
ns["cloth_begin"]($2, clip="$1")
print("DONE" if ns["cloth_step"](20) else "more")
PY
cat > run_step.py <<PY
import bpy
print("DONE" if bpy.app.driver_namespace["cloth_step"](25) else "more")
PY
tie=""; [ "$3" != "-" ] && tie="NS[\"tie_swing\"](\"$1\"${3:+, $3})"
cat > run_bake.py <<PY
import bpy
NS = bpy.app.driver_namespace
$tie
NS["cloth_bake"]("$1")
PY
out=$(python -I "$HERE/bl.py" run_piece.py 120) || { echo "$out"; exit 1; }
for i in $(seq 1 80); do case "$out" in *DONE*) break;; esac; out=$(python -I "$HERE/bl.py" run_step.py 120) || { echo "$out"; exit 1; }; done
echo "$out" | grep -v "^more$\|^DONE$\|^$"
python -I "$HERE/bl.py" run_bake.py 170 | grep -v "^$"
