# Character tools (worked on the Pumpkin Rabbit, 2026-10-13)

Copies of the scripts that took one character from a bare rig to an approved Walk and Idle. They are worked
examples: the rig is named `PumpkinRabbit_Rig`, the hands mesh `Cube.009`, the file `PumpkinRabbit_ANIM.blend`.
Change those names at the top of a script before using it on another character. SKILL.md, section
"Skinned characters", says when each one is used.

| File | What it does | Runs |
|---|---|---|
| `bl.py` | sends a script to the Blender addon socket (127.0.0.1:9876) when the MCP bridge is dead | `python -I bl.py script.py [timeout]` |
| `look.py` | the bridge's screenshot helper over the same socket | `python -I look.py out.png '<json>'` |
| `q_user_pose.py` | which bones the user posed off the curves, without changing the frame | live |
| `measure.py` | front-view leans of forearm and fingers, bend and twist of a joint off rest | exec into a dict |
| `rig_audit.py` | mirror pairs, joint pivots against skin seams, bend axes, unused deform bones | live, read-only |
| `skin_lab.py` | edge squeeze and stretch round a joint, and the same with bones that do not exist yet | live, read-only |
| `forearm_twist.py` | adds a forearm twist bone, its driver and weights | live |
| `idle_hands.py` | applies a hand-control turn on top of every key, remembers it, replaces it on re-run | live |
| `walk.py` | builds a looping walk from formulas, with weight in the legs and loose parts that swing | live |
| `cloth_pieces.py` | sliced cloth sim, tie chain, bake to shape keys on one cloth clock | live |
| `clip.sh` | sim + tie + bake of one clip | `bash clip.sh Walk '"apron", "straps"'` |
| `run_save.py` | asserts the file's state, then remove-then-save for a nearly full disk | live |
| `render.py` | headless EEVEE preview frames of one clip | `blender -b file --python render.py -- out Clip` |
| `silhouette.py` | headless: the character alone, flat black, transparent film | same |
| `video_track.py` | tracks one colour through a reference clip at 60 fps: step time, bob, sway | `python -I video_track.py clip.mp4` |
