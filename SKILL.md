---
name: blender
description: "Use for ANY headless Blender work driven by a script: rigging, animating, scaling, converting, inspecting, and exporting to FBX/glTF for Roblox, Unity, Unreal or a game engine. Triggers on 'rig this', 'animate this in Blender', 'make the door open', 'set the pivot', 'the origin is wrong', 'add keyframes', 'bpy keyframe', 'make it move', 'export as fbx', 'export for roblox', 'scale this model', 'make it 2x character size', 'convert this blend', 'inspect this .blend', 'what's in this model', 'render it', 'render faster', 'cutscene', 'first person holding a prop', 'make a seamless loop', 'it looks like it's floating', 'fix the weight paint', 'the wrist is twisted', 'add a twist bone', 'IK hands', 'cloth sim', 'make the apron move', 'walk cycle', 'idle animation', 'make him feel heavy', 'loosen the ears', 'silhouette render', 'the blender MCP is down', or any request to read, change or export a .blend without opening the GUI. Covers armature vs node-transform rigs, pivot placement from real hinge hardware, the Blender 5.x action/slot API, world-vs-local space, engine-ready scaling, FBX export traps, skinned characters (rig audit, IK hands, twist bones, skin weights, looping cloth baked to shape keys, heavy walk and idle, reference video, silhouette renders; tools in tools/character), and verification that proves the result."
---

# Blender from a script

Measure the model, place pivots on the real hardware, pose it, verify numerically, render
proof. Never author a pivot, an angle, or a scale factor from a mental picture.

Covers rigging and animation (steps 1-9) and getting the result out to an engine
(**Export and scale**, near the end). Both halves share one rule: **an operator that
returns FINISHED has not necessarily done anything.** Blender silently no-ops in several
places that matter, listed below, and each one produced a file that looked fine and was
not.

## Run Blender headless

```bash
blender.exe -b "file.blend" -noaudio --python script.py
```

Find the executable before you start. A machine often has more than one version, and
**a newer .blend cannot be opened by an older Blender** — Blender 4.3 reading a 5.0 file
reports `incomplete header, may be from a newer version`. Match the version the user
saves with.

```bash
blender.exe --version
```

On a machine with both: one Blender 5.2 LTS and one 4.3 install is common. Run `--version` on each.
User preferences and add-ons live in `%APPDATA%\Blender Foundation\Blender\<version>\`,
NOT in the install directory -- the `<version>` folder under the install is bundled program
files, and copying one version's over another's corrupts the install.
Check the .blend's own version
(the GUI title bar, or just try to open it) and use the matching one. A 5.0 file opened in
4.3 reports `incomplete header, may be from a newer version`.

Working reference from a real job -- read a rig, scale it to an engine's size, export every
action, and prove the motion survived: `<project>\export_example\`
(`export_roblox.py`, `verify_export.py`, plus the probes that found each trap below).

`-b` gives no GUI and no OpenGL context, so `bpy.ops.render.opengl` and most `bpy.ops`
calls that need a screen area fail. Everything below is context-free API that works
headless.

## Version traps, all verified by probe

| Thing | Blender 4.2 - 4.5 | Blender 5.0 |
|---|---|---|
| EEVEE engine enum | `BLENDER_EEVEE_NEXT` | `BLENDER_EEVEE` |
| `Action.fcurves` | works | **removed**, raises `AttributeError` |
| Material transparency | `mat.blend_method = 'BLEND'` | `mat.surface_render_method = 'BLENDED'` |
| `Mesh.calc_normals_split()` | removed in 4.1 | gone; split normals always evaluated, read `loop.normal` |

Many builds ship **without FFMPEG**: `image_settings.file_format = 'FFMPEG'` raises
`enum "FFMPEG" not found`. Render a PNG sequence and encode outside Blender.

Probe any uncertain enum instead of guessing — the error lists the valid set:

```python
try:
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
except TypeError as e:
    print(e)          # prints every accepted value
```

Editing geometry on a mesh with `has_custom_normals` needs care: bmesh does not carry
custom split normals through `from_mesh`/`to_mesh`. Capture them first, keyed by vertex
position so index shifts do not matter, and restore with `normals_split_custom_set` after.
Where one position holds several normals, pick the candidate with the largest dot product
against the loop's face normal.

## Step 1: which kind of rig is this

Decide this before touching anything. The two kinds need completely different work.

```python
print([o.name for o in bpy.data.objects if o.type == 'ARMATURE'])
print(len([o for o in bpy.data.objects if o.type != 'MESH']), "non-mesh nodes")
```

**Skinned armature.** Bones, vertex groups, an Armature modifier. Typical of game FBX
exports. Animate pose bones. Rigging work means adding bones and painting weights.

**Node transform.** Named empties each parenting one mesh, no armature at all. Typical of
Sketchfab, Collada and glTF scene graphs. Animate object transforms. Rigging work means
fixing origins.

Do not add an armature to a node-transform model just because bones feel more proper. The
node structure already is the rig, and object pivots export fine to FBX and glTF. Add an
armature only when the target engine requires skinned bones.

## Step 2: pivots are the whole job on a node-transform rig

Imported node-transform models usually put **every origin at (0,0,0)**. Rotating any part
then swings it around the centre of the model. Five rules, each learned by getting it
wrong first.

### Pin the axis to the hardware, then let the part go where it swings

Do not solve for a pivot that makes the closed pose land nicely. That inverts cause and
effect and leaves the axis floating in mid air. A hinge is fixed hardware; the door is
wherever the hinge takes it. Concretely: choose the axis from geometry, make the shut pose
the rest state, and accept the open pose that results.

### Find the real hinge hardware before choosing

Game models often model the pin and socket. Find them with a loose-part scan of the
part's own mesh. The hinge pin is a small component that rises above the part's main body:

```python
def components(ob):
    bm = bmesh.new(); bm.from_mesh(ob.data); bm.verts.ensure_lookup_table()
    M, seen, out = ob.matrix_world, set(), []
    for v in bm.verts:
        if not v.link_faces or v.index in seen:
            continue
        stack, grp = [v], []
        seen.add(v.index)
        while stack:
            c = stack.pop(); grp.append(c)
            for e in c.link_edges:
                o = e.other_vert(c)
                if o.index not in seen and o.link_faces:
                    seen.add(o.index); stack.append(o)
        out.append([M @ x.co for x in grp])
    bm.free(); return out

parts = components(door_mesh)
main_top = max(p.z for p in max(parts, key=len))     # top of the biggest component
pin = [p for g in parts for p in g if p.z > main_top + 0.001]
```

On a real bus the pins sat **0.05 inboard of the door posts**. Rigging on the post looked
entirely plausible and was wrong on all four leaves. The hardware is the ground truth.

### Move the mesh origin too, not only the parent empty

Clicking a part in the viewport selects the **mesh**, not its parent empty, so the rotate
gizmo appears at the mesh's own origin. Setting the empty alone leaves the gizmo at the
model centre and the rig looks broken even when the animation is correct.

```python
def set_pivot(node, pos):
    kids = [(c, c.matrix_world.copy()) for c in node.children]
    m = node.matrix_world.copy(); m.translation = pos
    node.matrix_world = m
    bpy.context.view_layer.update()
    for c, mw in kids:
        c.matrix_world = mw                      # geometry stays put
    bpy.context.view_layer.update()
    for c in node.children_recursive:            # and the meshes get the same origin
        if c.type != "MESH":
            continue
        local = c.matrix_world.inverted() @ pos
        c.data.transform(Matrix.Translation(-local))
        mc = c.matrix_world.copy(); mc.translation = pos
        c.matrix_world = mc
    bpy.context.view_layer.update()
```

### Put the origin on the hardware, including the right height

For a vertical hinge the pivot's Z does not change the motion at all, but the origin
should still sit on the real pin. A rig is read by people; an origin at the part's
mid-height reads as wrong even when it animates identically.

### Rotating about your own origin cannot translate you

This is the lever that turns a promise into a guarantee. If the origin is the pivot, key
`rotation_euler` **only** and never touch `location`. Then translation is structurally
impossible rather than merely intended, and you can prove it:

```
worst deviation from the shut pose at frame 1:  0.000000000
worst origin movement across the animation:     0.000000000
```

## Step 3: world space versus local space

`rotation_euler` and `location` are in the **parent's** space. Collada and glTF imports
hang everything off a converted root with its own rotation, so writing a local Y rotation
does not rotate about world Y.

Symptom: a lid that should lift reports `+0.000` movement, or a part swings on an axis you
did not choose. Build the world matrix and assign it instead:

```python
def world_pose(node, rest_mw, axis, deg):
    """Rotate about a WORLD axis through the node's own origin."""
    t = rest_mw.translation.copy()
    node.matrix_world = (Matrix.Translation(t)
                         @ Matrix.Rotation(math.radians(deg), 4, axis)
                         @ Matrix.Translation(-t) @ rest_mw)
    bpy.context.view_layer.update()
```

Keyframe after posing this way and the stored local euler comes out correct automatically.

## Step 4: reading a skinned armature

```python
arm = bpy.data.objects["ARM"]
M = arm.matrix_world

for b in arm.data.bones:                                  # hierarchy and world pivots
    print(b.name, b.parent.name if b.parent else "-",
          [round(v, 3) for v in (M @ b.head_local)],
          [round(v, 3) for v in (M @ b.tail_local)])

b = arm.data.bones["hinge_bone"]                          # which local axis is the hinge
print((M.to_3x3() @ b.matrix_local.to_3x3()).col[2])      # local Z in world terms

for ob in bpy.data.objects:                               # which bones actually deform
    if ob.type == "MESH":
        print(ob.name, [g.name for g in ob.vertex_groups])
```

Bone local **Y always runs head to tail**. Local X and Z are set by roll. A vertical hinge
is only local Z if the bone lies horizontally with zero roll. Check, do not assume.

- **A non-connected child bone orbits its parent's HEAD.** If `child.head != parent.tail`
  the child is a free offset child. Rotating the parent swings the child and everything it
  deforms around the parent's head. That is how one bone becomes a hinge and its child
  becomes the panel.
- **Only bones in a vertex group move geometry.** Bones with no group are drivers, and
  rotating one still moves the mesh through its weighted children.
- When adding bones, take the vertices away from their old group. Two groups at weight 1.0
  normalise to 0.5 each and the part moves half way.

## A file with several scenes is several rigs

Animators hand off files where each take is its own SCENE, each with its own copy of the
armature. One character file arrived as five scenes, five armatures, one clip each.
Three traps follow from that shape and all three are silent.

**`frame_set` only evaluates the ACTIVE scene.** Reading poses from an armature that lives
in another scene returns its STATIC pose on every frame. The loop runs, the numbers come
out, the comparison reports a clean match, and it measured nothing. This produced the worst
verification failure of that job: a harness reporting 0.0000 deviation on clips that were
in fact broken.

```python
owner = next(s for s in bpy.data.scenes if arm.name in {o.name for o in s.objects})
bpy.context.window.scene = owner          # BEFORE any frame_set
```

**The scene range is the clip; the action range is not.** They disagree, and the scene range
is what the animator set and what their playblast shows. Measured on that file: Run's action
ran to frame 317 while its scene ended at 300, and the Jumpscare's action stopped at 355
while its scene held to 366. Trusting the action range shipped Run 0.28 s long and the
Jumpscare 0.18 s short.

**The per-scene rigs are not interchangeable.** Their rest skeletons hashed identical, but
their CONSTRAINT stacks differed -- one carried two extra `COPY_ROTATION` on the hands. So
no single constrained rig plays every clip faithfully: moving one clip onto another rig
moved the hands 1.59 torso-lengths. Compare constraints, not just bones, before assuming two
rigs are the same.

### Baking across rigs: record armature space, write it back with `pose_bone.matrix`

The way to get one rig carrying every clip is to record each clip from ITS OWN rig with its
own constraints live, then replay it onto one rig whose constraints are removed.

```python
frames[f] = {pb.name: pb.matrix.copy() for pb in rig.pose.bones}   # armature space
...
pb.matrix = frames[f][pb.name]        # re-derives local transform vs the CURRENT parent
bpy.context.view_layer.update()       # per bone, parents before children
```

`pose_bone.matrix` is armature space, so it transfers between rigs with the same rest
skeleton, and assigning it re-derives the local transform against whatever the new parent
is. That is what makes it survive a re-root.

**A baked key is local to its parent, so reparenting a bone silently invalidates every key
on it.** Re-rooting first and then writing recorded matrices works. Writing keys and then
reparenting put the feet 2.2 torso-lengths out. Order matters, and nothing warns.

Walk the hierarchy parents-first when writing, and call `view_layer.update()` between bones
-- a child read before its parent is committed resolves against a stale matrix.

## Control rigs: the boxes and circles on an animator's rig

Measured on a third-party character rig (2026-09-18) and checked against the Blender
5.2 manual. Probe: `ik2.py` in your scratch folder.

**Names.** A bone the animator grabs is a *control bone*. The box or circle drawn for it is
its *custom shape* (bone widget): another object used as a template, viewport only, never
rendered, and the template object's own transform is ignored. The set of controls is the
*control rig*; a skeleton with none is the *deform rig* or export skeleton.

| Control | Constraint that uses it | Sits on | What moving it does |
|---|---|---|---|
| IK target (IK handle) | `IK`, `subtarget` | the LAST bone of the chain (lower arm, lower leg) | the chain rotates so its tip reaches the target |
| Pole target | `IK`, `pole_subtarget` | same constraint | sets the roll of the chain: where the elbow or knee points |
| Look-at / eye target | `DAMPED_TRACK` | each eye bone | the eye's track axis (Y for a bone) points at it, swing only, no roll |
| FK control | none | the bone itself | you rotate it directly (jaw, fingers, ears) |

How the IK constraint reads, from the manual:

- It lives on the chain's TIP bone and rotates `chain_count` bones walking up the parents.
  1 is the bone alone, 2 is the bone and its parent, **0 is every ancestor to the root**.
- `use_tail` puts the end of the chain at the tip bone's tail. So an IK on `Lower Arm` with
  chain 2 solves upper arm + lower arm and the HAND is not in the chain. This rig gives the
  hand a `COPY_ROTATION` from the same target bone, so one box places and turns the hand.
- `pole_angle` is a per-chain offset that makes the solved plane line up with the bones'
  roll. Here it was 76.6, 102.1, -137.9, -130.0 on the four limbs. It is rig-specific; never
  copy it to another rig, and a wrong one shows as a limb twisted about its own length.
- IK ignores its place in the constraint stack and always runs after the other constraints
  on the bones it affects. To constrain something to the IK result, copy onto a second chain.
- Stretch only happens on bones whose `ik_stretch` is above 0, whatever `use_stretch` says.
  Here `use_stretch` was on and every `ik_stretch` was 0: no stretch.
- Joint limits for IK are the bone's own `use_ik_limit_*` / `lock_ik_*` (the Blocky Rig set
  them on elbows and knees). A `LIMIT_ROTATION` constraint is a separate thing the IK solver
  does not see.

**IK/FK switching is the constraint's influence.** In the Walk scene both arm IKs were at
influence 0 (arms keyed by hand, FK) and both leg IKs at 1 (feet planted). Read `c.influence`
per scene before saying a limb "is IK". The influence can be keyed, so sample it per frame if
a clip switches midway.

**Targets and poles have no parent, on purpose.** That is what keeps a foot planted while
the hips move. It is also why a rig like this has many root bones: this one had 8 (`Pelvis`,
`View Target`, two hand targets, two knee poles, two foot targets). See "Studio needs exactly
ONE root bone" below for what that does to an export.

**`use_deform` does not tell you what a control is.** All 13 controls here had
`use_deform = True`. Tell controls from deform bones by weights: a control has 0 weighted
vertices and no weighted descendant. `Jaw` and `Upper Mouth` carried a shape AND weights
(924 and 1,702 verts): a deform bone used as its own FK control. Do not delete by "has a
custom shape".

**A target can be a real bone, and then the limb is not one chain.** The Pumpkin Rabbit
(a 13-IK rig with no custom shapes at all, bones unnamed)
aims each arm chain (3 bones) at the HAND bone, which carries the fingers and is parented to
the chest, not the forearm. Legs aim at the foot bone, parented to `RootBone`. Poles are
children of those hand and foot bones, so they travel with the limb. Its 8 fingers are
2-bone IK chains with targets under the palm, and the spine is one 4-bone chain with no
pole. So "delete the IK targets" would delete hands and feet here: delete by weights, and
count a bone as live if any MESH is bone-parented to it or to a descendant (the rabbit has
11 such meshes). A rig can also have full IK and zero widgets; look for constraints, not shapes.

**Every scene's armature repeats the setup.** Five Bon armatures, 13 shapes and 4 IK each.
An edit to one is not an edit to the others.

### Building one on a rig that has none

1. Controls are extra bones: no parent (or parented to a master/root control), `use_deform`
   off, in their own bone collection so they can be hidden.
2. IK target at the wrist or ankle; pole out in front of the knee, behind the elbow.
3. `IK` on the lower limb bone: target, pole, `chain_count = 2`. Then tune `pole_angle`
   until the REST pose does not move when the constraint turns on. Measure it: the deformed
   mesh with the constraint on and off must match at rest.
4. `COPY_ROTATION` from the target onto the hand or foot.
5. `DAMPED_TRACK` (track Y) on each eye to its own target, both targets under one master.
6. Give each control a custom shape, scaled to bone length.

### Getting it out again

Controls are for authoring. The export is the baked result: record every bone's
armature-space matrix per frame with constraints live, remove the constraints, delete the
unweighted controls, write the matrices back. That sequence is "The order of operations that
actually ships" below; the facts in this section are why each step exists.

## Step 5: keyframing

```python
pb = arm.pose.bones["hinge_bone"]
pb.rotation_mode = "QUATERNION"
pb.rotation_quaternion = Quaternion((0, 0, 1), math.radians(90))
pb.keyframe_insert("rotation_quaternion", frame=48)
```

Insert on the data path that matches `rotation_mode`. Setting `rotation_quaternion` while
the bone is in `XYZ` mode writes a value nothing reads, and the bone never moves.

Clear an existing action before rebuilding, or old keys survive underneath:

```python
arm.animation_data.action = None      # armature
obj.animation_data_clear()            # plain object
```

### Actions have slots in Blender 4.4+

An action no longer holds F-curves directly. It holds layers, each layer holds strips,
each strip holds one channelbag per slot:

```python
def get_fcurves(obj):
    ad = obj.animation_data
    act = ad.action
    if hasattr(act, "fcurves"):          # 4.3 and older
        return act.fcurves
    return act.layers[0].strips[0].channelbag(ad.action_slot).fcurves
```

`keyframe_insert` is unchanged and creates the layer, strip and slot for you.

## Step 6: choose the pose by measurement

```python
def world_box(ob):
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    co = [ev.matrix_world @ v.co for v in ev.data.vertices]
    return (Vector((min(c[i] for c in co) for i in range(3))),
            Vector((max(c[i] for c in co) for i in range(3))))
```

`evaluated_get(depsgraph)` is required. Raw `ob.data.vertices` holds the rest pose and
never changes, so reading it makes every angle look identical. For a keyed animation call
`scene.frame_set(f)` first.

Report a **continuous measure with units**, never pass/fail. A boolean hides a panel that
moved 2 cm.

### The failure mode is the dimension you left out

A score that omits a property will confidently pick a wrong answer that looks perfect on
everything it does measure. Two real misses:

- A door score checked X coverage and thickness but not **Y position**. The doors closed
  0.075 inside the body while coverage read 0.104 of 0.111 and spill read 0.000.
- A swing-direction score judged each leaf alone and gave **both leaves of one doorway the
  same sign**. A pair always mirrors.

So: list every property the right answer must have and score all of them. Sanity check
symmetry, because mirrored parts must get mirrored answers.

### Prefer a reference over a heuristic

If the model already contains the answer, score against it. Ripped models often ship parts
in a non-rest state, and that authored pose tells you which way a part opens. Measure it in
the source file and match it, rather than inventing a "looks open" score.

### Derive when you can, but check it is the right quantity

PCA gives a plane normal exactly. On a door leaf it returned 93.4 degrees off the body,
while the correct swing was 90: the 3.4 was the leaf's own **tilt**, not the hinge angle.
The number was exact and the wrong quantity.

Cross-check a derived value against a measured one. Here the flattest closed pose, where
the bounding box thickness returns to the part's true thickness, marks the true angle.

### Suspect the harness before the finding

Comparing two candidate pivots 0.012 apart produced results 0.8 apart. Impossible, and the
cause was the test, not the model: `set_pivot` rewrites the **children's** matrices, so
resetting only the parent between runs left them displaced.

Reset everything a test touched, or reload the file per test. If a result would be a big
finding, try to break it first. Never report a comparison you have not proven ran clean.

## Step 7: verify before claiming it works

Print the worst value across the whole frame range for the two or three numbers that would
expose a broken rig:

- **Interpenetration.** Gap between parts that must not overlap; negative means they pass
  through each other.
- **Shell penetration.** Does anything cross outside the body it lives in.
- **End state.** At the final frame, is the thing actually open, clear, aligned.
- **Invariants.** Anything that must not change, printed to full precision.

```
WORST leaf-to-leaf gap +0.001 m   WORST outside-skin 0.000 m
worst origin movement across the animation: 0.000000000
```

Make the script refuse to save when a check fails. A rig that silently saves broken is
worse than one that stops.

### What a pose comparison cannot see

A pose check samples bone positions at integer frames, relative to a root, normalised by a
reference length. That is a good metric and it is blind to more than it looks. Over one
export job it reported `MATCHES` while the file was, in turn, ten times too fast, skinned
wrong, and leaf-boned -- because each defect lives in a dimension the metric drops:

| defect | why the pose check misses it |
|---|---|
| wrong declared frame rate | frame 150 is compared to frame 150 at any rate |
| twitch between keys | integer frames are exact by construction where keys exist |
| un-normalised skin weights | it measures BONES; weights only move VERTICES |
| bone roll / axis orientation | positions match while local axes differ |
| whole-rig yaw, root motion | normalising against the root subtracts it |
| scale | dividing by a reference length cancels it |

So pair it with checks in the dropped dimensions: assert clip DURATION in seconds, sample
between keys, compare the deformed MESH not the skeleton, and print the declared frame rate
and unit scale read back from the WRITTEN file. A metric that cannot fail is not
verification.

**Suspect the harness when the result is surprisingly clean, not only when it is bad.** Both
`0.000002` and a wild number are evidence that something about the measurement needs
checking.

## Step 8: timing and easing

```python
sc.render.fps = 24
sc.frame_start, sc.frame_end = 1, 190
```

Real motion is not one key to another. Break the move into sub-keys:

1. a small break-away at the start (a seal releasing, slack taking up)
2. the fast middle
4. a decelerating approach to the stop
5. a settle or small rebound after contact

Overlapping action: a secondary part should lead or lag the primary by a few frames rather
than moving in lockstep. Stagger repeated parts (a row of windows) instead of moving them
together.

```python
for fc in get_fcurves(obj):
    for kp in fc.keyframe_points:
        kp.interpolation = "BEZIER"
        kp.easing = "EASE_IN_OUT"
        kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
    fc.update()
```

`interpolation` is `CONSTANT | LINEAR | BEZIER | SINE | QUAD | CUBIC | QUART | QUINT |
EXPO | CIRC | BACK | BOUNCE | ELASTIC`. `easing` is `AUTO | EASE_IN | EASE_OUT |
EASE_IN_OUT`. Mechanisms want `BEZIER` plus honest sub-keys. `LINEAR` is correct for a
constantly spinning wheel and wrong for anything a motor accelerates. Call `fc.update()`
after editing keys or the handles stay stale.

## Step 9: render proof

```python
sc.render.engine = 'BLENDER_EEVEE'      # 'BLENDER_EEVEE_NEXT' on 4.2-4.5
sc.eevee.taa_render_samples = 8
sc.render.resolution_x, sc.render.resolution_y = 640, 420
sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(animation=True)
```

Headless renders have no world, so the result is black. Add one:

```python
w = bpy.data.worlds.new("w"); w.use_nodes = True
w.node_tree.nodes["Background"].inputs[1].default_value = 2.5
sc.world = w
```

Aim the camera at the moving part, not the whole model:

```python
cam.location = target + Vector((1.9, -3.4, 0.9))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
```

Encode outside Blender, then build a contact sheet and **actually look at it**. A strip of
key frames shows a wrong axis or a stuck part instantly, and it costs one render. Reading
bounding boxes is not a substitute for looking when the question is "does this look right".

```bash
ffmpeg -y -framerate 24 -i "frames/f_%04d.png" -c:v libx264 -pix_fmt yuv420p out.mp4
```

### An all-magenta render is three separate bugs

Headless renders of a ripped file came back 100% magenta, and each cause alone was enough:

* **`scene.render.use_sequencer`** left True with strips in the VSE makes
  `bpy.ops.render.render` return the SEQUENCER output, not the 3D view. Set it False.
* **Packed images report `has_data == False` headless** until something touches their
  pixels, and render as missing-texture magenta. Poke `im.pixels[0]`, or unpack to disk.
* The camera or the scene was not the active one.

Also: a take that renders empty may not be hidden -- check whether it is LINKED to a scene
collection at all. Four of five takes in that file lived in orphan collections, visible in
the outliner and in no scene.

## Editing a Blender session live, over MCP

Headless is not the only option. If the `blender` MCP is connected to a GUI session,
`execute_blender_code` runs arbitrary Python **in that open file**, and the user watches the
viewport update. That removes the edit-save-reopen loop entirely, which on a long job is most
of the wall clock.

Probe before assuming it is there:

```python
mcp__blender__get_addon_status()     # capabilities, protocol version, blender version
mcp__blender__get_scene_info()       # or just execute_code and print bpy.data.filepath
```

**It can do more than headless, not less.** Verified in a live 5.2.2 session: GUI mode,
`bpy.ops.object.mode_set` works without a context override, `bpy.ops.ed.undo` exists, and
every editor area is reachable. The operators that fail in `-b` because there is no screen
are exactly the ones that work here.

What changes, and each one has bitten:

* **Edits live in memory until saved.** A crash or a close-without-saving loses them. When
  something is worth keeping, save it explicitly (`bpy.ops.wm.save_mainfile()`) or tell the
  user to. Headless scripts that end in `save_as_mainfile` have no such gap.
* **The user's session is authoritative and it is not yours.** They may be mid-edit, in pose
  mode, on another frame. Read the state before writing; do not assume the active object,
  mode or frame.
* **A long loop freezes their UI.** A 366-frame bake that is fine headless makes Blender look
  hung. Keep live edits short and push batch work to a background run.
* **`get_viewport_screenshot` shows what they are actually looking at**, which beats asking
  them to describe it. Use it to verify a change rather than claiming one.

**Choose by the job, not by habit.** Live for iteration, inspection, and anything where the
answer is "does this look right". Headless for renders, batch bakes, exports, and anything
that must be reproducible from a clean file.

**A GUI session and a headless write to the same file will fight.** The open session holds
the pre-edit data and overwrites your save the moment the user presses Ctrl+S. Either work
live, or work headless with the file closed -- never both at once.

## A GUI session open on the file will undo your work

The user often has the .blend open while you write to it headlessly. That session holds
the old data and overwrites your save the moment they press Ctrl+S. It also makes them
report that your fix did not work, because their window still shows the previous version.

```powershell
Get-Process blender | Select-Object Id, StartTime, MainWindowTitle
```

Compare `StartTime` against the file's mtime before debugging anything else. A window
title starting with `*` has unsaved changes. Tell the user to revert or reopen; never
assume they are looking at what you saved.

When the user has hand-placed a pose and saved it, **that pose is authoritative**. Read it
out of their file and build on it. Do not rebuild from the source model, which silently
discards their work.

## Finding parts in a ripped model

Enumerate the space. Never grep for the name you expect.

An empty search result is a fact about the query. To claim a part does not exist, list
every component in the region it would occupy and show it is not among them. A bus turned
out to have no wiper geometry at all, and proving that meant listing every loose part in
the windscreen zone, not searching for "wiper".

Confirm whether a source file even has animation before promising any:

```bash
strings -n 6 model.fbx | grep -oE "AnimationStack|AnimationCurve|Deformer|LimbNode" | sort | uniq -c
```

`LimbNode` and `Deformer` with **no** `AnimationStack` means a skeleton and skin weights
but zero animation. The rig is usable; the motion has to be authored.

Naming conventions worth reading: `tag_*` bones are attachment points, not deformers.
`*_jnt` are working joints. `*_end` are leaf tips. Separate meshes named `_open` and
`_closed` for the same part are **state swaps**, not animation targets; keyframe
`hide_viewport` / `hide_render` instead of trying to rotate them into place.

Two exports of the same asset can differ only in leaf bones. Hash the geometry before
redoing work on the "new" one:

```python
h = hashlib.sha256()
for v in ob.data.vertices:
    h.update(("%.5f %.5f %.5f|" % (v.co.x, v.co.y, v.co.z)).encode())
```

## Export and scale

```python
bpy.ops.export_scene.fbx(filepath="out.fbx", bake_anim=True,
                         bake_anim_use_all_actions=False, add_leaf_bones=False,
                         bake_anim_simplify_factor=0.0, path_mode='COPY',
                         embed_textures=True, object_types={'ARMATURE', 'MESH'})
bpy.ops.export_scene.gltf(filepath="out.glb", export_animations=True)
```

`add_leaf_bones=False` matters: FBX otherwise appends `_end` bones that pollute the
skeleton on import. `bake_anim_simplify_factor=0.0` turns off key reduction, which
otherwise quietly resamples the motion. Object-transform animation exports through both
formats without an armature.

For a game engine, export the rig once with no animation, then one file per action, each
still carrying the skeleton and skinned mesh. Roblox's animation importer wants the rig in
the clip file, not the clip alone.

### A hidden object cannot be selected, and the exporter will not tell you

`hide_get()` is the eye icon and is **separate from `hide_viewport`**. A hidden object
silently refuses `select_set(True)`, so `use_selection=True` exports whatever is left. A
rabbit rig exported this way produced a 5 MB FBX containing **two meshes and zero bones**,
and `export_scene.fbx` returned `{'FINISHED'}`.

```python
want = [arm.name] + mesh_names
for o in bpy.context.view_layer.objects:
    o.select_set(False)
for n in want:
    o = bpy.data.objects[n]
    o.hide_set(False)          # eye icon
    o.hide_viewport = False    # monitor icon: a different flag
    o.select_set(True)
got = sorted(o.name for o in bpy.context.view_layer.objects if o.select_get())
assert got == sorted(want), f"selection is {got}"
```

Then check the file, because size proves nothing:

```python
blob = open(path, 'rb').read()
assert blob.count(b'LimbNode') and blob.count(b'Deformer'), "FBX has no skeleton"
```

### Scale: measure a reference in the file, never recall a constant

If the target size is "2x a character", find a character. The .blend held a Roblox R6
zombie; it measured **5.1012**, which both gives the factor and proves the file is in
studs. A remembered "R6 is 5 studs" would have been close enough to hide a unit error.

```python
avatar = zombie_max_z - zombie_min_z          # 5.1012
k = (avatar * 2) / rabbit_bind_pose_height    # 10.2024 / 94.8336 = 0.107582
```

Measure the **bind pose**, with the action detached and every `pb.matrix_basis` reset. A
frame of idle is 0.7% off; a jumpscare where the character rears up is 28% off.

### FBX throws away armature object scale

Measured three ways on the same rig:

| Mechanism | In Blender | Re-imported | Verdict |
|---|---|---|---|
| `arm.scale = k` | 10.2485 | **95.2622** | discarded |
| `global_scale=k` on export | 95.2622 | 10.2485 | survives, as a scale on the root node |
| bake into bone + vertex data | 10.2485 | 10.2485 | every node at scale 1 |

Bake it. Then nothing is left for the target engine to interpret, which matters when you
cannot test that engine's importer.

### Baking scale means rescaling location curves at BOTH levels

`transform_apply` scales bones and geometry and leaves every translation channel in
pre-bake units. Two levels carry translation and the naive filter catches only one:

```python
# 'location'.endswith('.location') is False.
# Miss the object level and root travel stays ~9x too large while the body looks right.
if fc.data_path != 'location' and not fc.data_path.endswith('.location'):
    continue
for kp in fc.keyframe_points:
    kp.co.y *= k
    kp.handle_left.y *= k
    kp.handle_right.y *= k
fc.update()
```

### transform_apply is a silent no-op on an animated transform

With an action assigned it returns `{'FINISHED'}` and changes nothing. Detach first, and
assert the bone data actually moved:

```python
arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
was = arm.data.bones[0].head_local.z
arm.scale = (k, k, k)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
assert abs(arm.data.bones[0].head_local.z / was - k) < 1e-4, "apply did nothing"
```

An early probe compared "bake" against "bake + rescale" with the action attached, so
**both arms were unbaked** and the numbers were meaningless. Suspect the harness first.

### Export ALL actions into ONE file, with Blender's default animation settings

Exporting one clip per FBX seems tidier and it is what broke a rig that
otherwise worked. Measured on the same model, same rig, four export variants:

| variant | LimbNode | AnimationStack | usable in Studio |
|---|---|---|---|
| all actions, Blender defaults | 216 | **35**, each named after its clip | yes |
| one clip, Blender defaults | 216 | **0** | no animation at all |
| one clip, `add_leaf_bones=False` | 168 | **0** | no animation at all |
| one clip + all my overrides | 168 | 1, named `Scene` | Studio could not use it |

Three things in that table:

* **`bake_anim_use_all_actions=False` with `bake_anim_use_nla_strips` left at its
  default writes NO ANIMATION**, and still produces a plausible 64 MB file with
  a full skeleton. Silent, and invisible to any check that only counts bones.
* A single-clip export names its stack `Scene`. The all-actions export names
  each stack after its action (`…/@Idle`, `…/@walkF`), and importers key on
  those names.
* `add_leaf_bones=False` drops 48 bones versus what Blender natively exports.
  The general advice to disable it is wrong when the target engine expects the
  skeleton Blender normally writes.

So for a character: one file, `bake_anim_use_all_actions=True`, everything else
default apart from the unit scale. Confirm by counting `AnimationStack` in the written
bytes — one per clip.

**`add_leaf_bones` is per-target, not a universal.** The table above is one model. On a
later Roblox job `add_leaf_bones=True` added 18 phantom bones and Roblox's own docs
(create.roblox.com/docs/art/characters/export-settings) specify **off**; turning it off was
correct there and the rig imported clean. Read the target engine's documented settings
rather than carrying a number over from the last job.

### Setting `fps` is not setting the frame rate

Blender's real rate is `fps / fps_base`, and `fps_base` is rarely 1.0 in files that came
from someone else. Assigning `scene.render.fps = 60` to a scene whose `fps_base` is `0.1`
gives **600 fps**, and the FBX exporter writes exactly what Blender reports. Every clip
then plays 10x too fast in the engine while the .blend looks perfect, because inside
Blender the keys are still one per frame.

This is symmetrical and bites both ways: reading `fps` alone on that same file says 6 fps
and invites retiming clips 10x too slow.

```python
scn.render.fps = 60
scn.render.fps_base = 1.0                       # both, always
assert abs(scn.render.fps / scn.render.fps_base - 60) < 1e-6
```

Frame-indexed verification cannot see this. Comparing frame 150 to frame 150 matches
perfectly at any declared rate, so the check has to assert playback DURATION in seconds
against the source, not pose equality per frame.

### Normalise skin weights before export, or the engine deforms differently than Blender

The armature modifier normalises weights when it evaluates, so a vertex whose weights sum
to 3.18 looks perfect in the viewport. The FBX carries the raw authored values, and an
engine that skins from them moves that vertex 218% of the way. Measured on a ripped
character: 1894 of 9980 vertices off, spanning 0.0044 to 3.1788.

Cap influences to the engine's limit FIRST (Roblox allows 4), then rescale, or dropping a
bone unbalances an already-normalised vertex.

```python
ws = sorted(((g.group, g.weight) for g in v.groups if g.weight > 1e-6),
            key=lambda gw: -gw[1])[:4]
total = sum(w for _, w in ws)
for gi, w in ws:
    me.vertex_groups[gi].add([v.index], w / total, "REPLACE")
```

### Sample BETWEEN keyframes to see a twitch

A pose comparison on integer frames is exact by construction wherever keys exist, so it
reports a clean match while playback stutters. Walk the timeline in quarter-frame steps and
report the largest single-step movement of any bone against the median. Real animation is
continuous; a spike is the defect. The same harness run on the source gives the baseline to
compare against, which is what turns "max step 0.16" into a verdict.

### An action that keys a deleted bone is dropped from the FBX, silently

Restructuring a rig leaves F-curves pointing at bones that no longer exist. The FBX exporter
does not warn, does not error, and does not export that action AT ALL -- it skips it and
writes a plausible file at a plausible size. Four of five clips vanished from a 17 MB export
this way.

```python
live = {b.name for b in arm.data.bones}
for fc in list(curves(act)):
    if 'pose.bones["' in fc.data_path and fc.data_path.split('"')[1] not in live:
        bag.fcurves.remove(fc)        # 550 orphaned curves on that job
```

Count `AnimationStack` in the written bytes and compare against your CLIP TABLE, never
against `len(bpy.data.actions)` -- when a stale filter had deleted every clip, that check
compared 0 against 0 and passed.

### A multi-material mesh leaves as several meshes

Engines that allow one material per mesh (Roblox states this explicitly) get one mesh per
material, because the FBX exporter splits the object. A 3-material body exported as three
meshes with 9980 / 414 / 200 vertices. That is correct and expected -- but plan for it, and
check each resulting piece separately for weights and influence counts rather than checking
"the mesh".

### Repairing a twitch: measure in the frame of reference the motion belongs to

A hand gripping a head that is being swung shows large WORLD rotation every frame, and a real
wrist fling is buried inside it. Express the hand in the head's space and the picture is
unambiguous, because a gripping hand should not move at all there:

```python
rel = head_world.inverted() @ hand_world
```

Measured that way on a finisher: the right hand sat at **0.1 degrees mean with zero frames
over 20**, the left at 3.4 with excursions to 175. The good hand is the control -- the target
is not a guess, it is what the animation already achieves elsewhere.

Four things that made earlier attempts fail:

* **Position is blind to rotation.** Both files measured identical hand POSITIONS and I
  declared the frames clean. A hand can spin 150 degrees about its own axis while its wrist
  never moves. Measure the quantity the defect lives in.
* **A fling is a bump, not a spike.** The deviation went 6.8, 13.9, 43.0, 39.5, 11.5. Clipping
  the two frames over a threshold left 13.9 next to a repaired ~0 -- a seam I created. Use a
  continuous map with no threshold: `out = LIMIT * tanh(dev / LIMIT)` passes small values
  through untouched and asymptotes large ones, so no frame can become an edge.
* **In-place sequential smoothing propagates the error.** Repairing frame 39 used frame 40 as
  a neighbour while 40 was still corrupt. Detect against a SNAPSHOT taken before any write,
  and repair consecutive bad frames as a RUN, interpolated from the clean key before to the
  clean key after -- a three-frame fling has no good neighbour on either side, only the run
  boundary does.
* **Distinguish a fling from fast motion by where it ENDS.** Both deviate hard from the
  midpoint. A fling returns; real motion travels. Compare the excursion against the net
  rotation across the run. The exception is a bone in contact -- something welded to another
  object has no reason to travel, so the test is inverted for it.

**Baking a constraint freezes whatever its target was doing.** Eyes on a DAMPED_TRACK to a
view-target bone measured 42.9 degrees off the thing they were supposed to watch, and 155
degrees off at one frame -- looking backwards. Reinstating the behaviour as keys means
reapplying the constraint's own rule (minimal rotation onto the target), plus an anatomical
clamp, or you get pupils in the back of the skull on the frames where the head faces away.

### When several settings changed at once, bisect; do not reason

Four export options were changed together and the result broke, so no single
one was implicated. Writing four variants that each vary one thing found the
answer in a single pass, where three rounds of reasoning about which option
"should" matter had found nothing. If the user's own naive export works and
yours does not, the difference is in your settings — start by reproducing
theirs exactly, then add back one change at a time.

### The FBX unit is a separate fact from the vertex numbers, and it is what the engine reads

Blender's default `apply_scale_options='FBX_SCALE_NONE'` writes
`UnitScaleFactor 1.0` — centimetres — while the vertex data stays at Blender
size. Roblox then imports the model about **100x too large**. Its own docs say
so: *"when exporting from Blender using its default .fbx settings, models often
import at an unexpectedly large scale in Roblox Studio"*, and name
`FBX Unit Scale` as *"the recommended way to export .fbx files at the same
scale"* ([create.roblox.com/docs/art/blender#adjust-scale-fbx]).

Measured on one rig, exported four ways — the geometry is byte-identical and
only the declared unit moves:

| option | UnitScaleFactor | raw vertex height |
|---|---|---|
| `FBX_SCALE_NONE` (default) | 1.0 (cm) | 9.1822 |
| `FBX_SCALE_CUSTOM` | 1.0 (cm) | 9.1822 |
| `FBX_SCALE_UNITS` | **100.0** (m) | 9.1822 |
| `FBX_SCALE_ALL` | 100.0 (m) | 9.1822 |

So: `global_scale=1.0, apply_scale_options='FBX_SCALE_UNITS'`, and in Studio's
import dialog set **File Geometry → Scale Unit = Stud**.

### A Blender round trip cannot validate an export's scale

This is the trap that shipped the bug above. Blender's FBX importer undoes its
own exporter's unit convention, so export → re-import → measure returns the
right height **whichever flag was used**. The check passed on 34 clips at
0.000028 studs while every file was wrong for the target engine.

Verify the unit by reading it out of the file. It sits in
`GlobalSettings/Properties70` as `UnitScaleFactor`, and a small binary-FBX
walker gets it without Blender in the loop — see
`check_fbx_units.py` (a small FBX walker you write once, see tools\), which also pulls the raw
`Vertices` arrays so the declared unit and the actual geometry are both checked
against what was intended.

**The general rule: a verifier that shares a convention with the thing it
verifies proves nothing.** Ask what the *consumer* reads, and read that.

### "The animations face the wrong way" is usually a constant yaw on a control bone

A ripped rig often has a non-deforming control bone above the deforming chain
carrying a **fixed rotation in every clip** — the animator worked with the
character turned. The bind pose faces one way, every animation snaps 90 deg to
another, and in-engine it reads as "the animation's forward is the model's
left".

Measure before touching anything: sample the control bone's yaw on **every frame
of every clip**. If it is constant *within* each clip, it is a facing offset and
removing it is a per-curve constant, not a resample. On one rig, 31 of 34 clips
sat at exactly 90.000 deg, with three at 45 deg / -179.888 deg — those three were
deliberate directional variants, so subtracting the same constant from all 34
preserved their relative offsets. Report odd ones; do not silently normalise
them.

**Pre-multiply the correction.** `fix @ q` removes the yaw in the parent/world
frame; `q @ fix` removes it in the bone's own frame. For a pure-Z quaternion the
two agree, which hides the bug — 33 clips were identical either way, and the one
clip whose control bone had a 0.178 deg off-axis component was left with 0.005
studs of residual until the order was fixed.

Also check the engine's mesh limits while you are there. Roblox: "Individual
meshes can not exceed 20,000 triangles" and "A vertex can not be influenced by
more than 4 bones or joints"
(`create.roblox.com/docs/art/modeling/specifications`). Split an oversized mesh
by face index rather than decimating — lossless, and the halves keep their
vertex groups.

### Verify a rig edit against the MESH, not against two bones

Checking "which way does the body face" by taking the vector between two
symmetric bones (the upper legs) reported up to **97 degrees of error on clips
that were perfectly fine** — because the legs swing through the stride, so the
metric measures gait, not facing.

The check that cannot be fooled: assert the edit is exactly the transform you
intended and nothing else. Sample every deformed vertex before and after, apply
the intended transform to the "before" set, and compare.

```python
Rz = Matrix.Rotation(radians(-90), 4, 'Z')
worst = max(((Rz @ a) - b).length for a, b in zip(before, after))
```

That both proves the fix landed and proves it disturbed nothing else. It caught
the pre/post-multiply bug above, which every angle-based metric had passed.

### Exporting a character for Roblox: the origin goes at the HIPS, not the feet

Standing a character's feet on z=0 is the intuitive move and it is wrong for a
Roblox character. Three sources agree:

* `create.roblox.com/docs/art/characters/specifications` — "The LowerTorso and
  Root bone or joint position must be set to **0, 0, 0**." The R15 hierarchy is
  `Root -> HumanoidRootNode -> LowerTorso -> {UpperTorso, LeftUpperLeg,
  RightUpperLeg}`.
* devforum 258555 (official announcement) — "the bottom of the HumanoidRootPart
  is aligned with the **hip joints** ... `Humanoid.HipHeight` will now more
  closely reflect the **leg length**."
* devforum 4747045 (solved) — Studio "is defaulting the root bone [to] spine1
  which is not in the middle of the ground"; the fix is a root bone at the world
  origin at hip height, and "instead of keeping your character floored in
  blender instead move it to center gravity location".

**Studio takes the top of the bone hierarchy as the character root.** A rig
topped by non-deforming control bones parked at the feet — very common in game
rips, here `ORIGIN -> Rotate` at 0.7% of the character's height — puts
HumanoidRootPart on the floor, and the Humanoid then lifts the whole character
by HipHeight. The symptom is a character that floats with its collision box at
its ankles.

So before exporting: make the hip bone the single root, delete the control and
camera bones, and translate so that bone's rest head is at (0,0,0). Feet end up
at about -(leg length), which is what a Roblox character looks like in Blender.

Re-rooting means re-baking, because the control bones are usually animated
(here `ORIGIN` rotated; `Rotate` was static and could just go). Record the hip
bone's armature-space `matrix` per frame per clip, unparent it, delete the old
parents and their F-curves, then write the recorded matrices back as
location/rotation/scale keys. Verified at 0.000001 studs over 34 clips —
`reroot.py` (a re-root script, see tools\character\).

Check the result on the exported file: the rig FBX's lowest vertex should be
**-(leg length)**, not 0. Zero means the origin is on the floor again.

Getting the export right is only half of it. Studio then needs the root part
renamed to `HumanoidRootPart`, the Humanoid reparented so it rescans, RigType
set to R15, and HipHeight set LAST from
`(root centre above the feet) - RootPart.Size.Y/2`. Until `Humanoid.RootPart`
is non-nil, HipHeight does nothing at all and the character falls through the
floor. Full trace: the Roblox DevForum threads cited above.

### Translate a skeleton with `Armature.transform()`, never a loop over edit_bones

To sit a model's feet on z=0, the offset has to go into mesh vertices **and**
bone rest positions, because the exported rest data is what the engine gets.
Moving the armature object and calling `transform_apply(location=True)` is not
enough: Blender's world-space read said the feet were at 0.000000 while the
written FBX still carried the old -0.0730, since the deformed mesh follows the
bones but the exported mesh data had not moved.

And the obvious way to move the bones is wrong:

```python
for eb in arm.data.edit_bones:      # WRONG
    eb.head.z += dz
    eb.tail.z += dz
```

`use_connect` children are dragged by their parent's tail and then shifted
again by their own edit. On one 84-bone rig, 26 bones were connected and **45
ended up displaced by up to 2*dz**. The rest pose still looked perfect, so a
bind-pose check passed; every posed frame was off by ~0.2 studs.

```python
shift = Matrix.Translation((0, 0, dz))
for me in {o.data for o in meshes}:
    me.transform(shift)
heads = {b.name: b.head_local.copy() for b in arm.data.bones}
arm.data.transform(shift)                     # coherent across the hierarchy
assert all(abs((b.head_local.z - heads[b.name].z) - dz) < 1e-5
           for b in arm.data.bones)
```

Safe only when the armature is at location 0 / scale 1 and the meshes have
identity local matrices, which is true right after the scale bake. Assert it.

### Keep ONE copy of the target numbers

The exporter and the verifier both knowing "1.8x" meant changing the target to
2.0 in one file left the other measuring against the old number and declaring
all 34 clips broken by ~1.1 studs. Nothing was wrong with the files. Write the
derived values (`k`, target height, ground offset) to a small JSON as the export
runs and have the verifier read it — a verifier holding its own copy of a
constant tests the constant, not the export.

### Verify an export by re-importing and comparing the deformed MESH

Bones and bounding boxes both lie. A bone-head comparison flagged fingers and toes as
broken; the bounding box called the same file perfect. Vertices are what ships.

```python
ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
verts = [ev.matrix_world @ v.co for v in ev.data.vertices]   # per frame
```

**Blender's FBX round trip shifts the animation by exactly one frame.** Unaligned it
reported 5.4 studs of error on a 10-stud character and read as catastrophic corruption;
aligned, the residual was 0.000029 studs. Search offsets `-1, 0, +1`, use the best, and
print which one won so the shift stays visible rather than silently absorbed.

### When scaled output looks broken, run the unscaled control

The same clip exported at scale 1.0 failed identically, 61.85 studs against 6.65 —
exactly proportional. That one run proved the scaling innocent and redirected the hunt to
the round trip, which is where the real cause was. Without it the obvious move is to keep
rewriting correct scaling code.

### A camera that looks at a moving target: transport the roll, never recompute it

Building each frame's orientation independently from an up hint produces two failures that
look like different bugs and are the same one. Measured on a POV camera tracking a head:

| | worst rotation per frame | flips |
|---|---|---|
| per-frame hint | 175.2 deg | 5 |
| transported | 12.8 deg | 0 |

`to_track_quat`, or any `look_at`, needs an up vector. Derive it fresh each frame and the roll
is an independent choice every frame, so it wanders with whatever you derived it from, and
**inverts** wherever the view direction nearly parallels the hint. That parallel case is not
exotic: it happens every time the camera looks along the axis you chose as up.

Carry the up vector forward instead and re-project it perpendicular to the new view:

```python
up = prev_up - fwd * prev_up.dot(fwd)      # parallel transport
up.normalize()
right = fwd.cross(up).normalized()
up = right.cross(fwd).normalized()
```

Now frame-to-frame roll is the minimum possible and a flip is structurally impossible --
there is no independent choice left to get wrong. Add a weak lerp toward world up to hold a
horizon, and disable that lerp near vertical where world up is degenerate, which is the exact
case that broke the naive version.

**Then the first frame decides every frame.** Transport means frame 1's roll propagates
through the whole clip. On that job frame 1 looked dead vertical, the fallback hint picked
arbitrarily, and the subject was upside down for 40 frames until the level-pull righted him.
Seed the first frame from something meaningful -- the SUBJECT's own up axis, so they are
upright by construction -- and verify it:

```python
local = cam_q.inverted() @ subject_up
assert local.y > 0, "subject renders upside down"
```

### Close-range lighting: the falloff, not the exposure

Lighting a face 0.5 units from the lamp is not lighting a room. Irradiance goes as 1/r^2, so
values that are sane at room scale blow out completely up close. A first attempt at 260 W
clipped the subject's teeth to pure white; the usable range turned out to be **1.5 to 5**.
Sweep by an order of magnitude, not by 20%.

For a torch-in-hand look, put a SPOT at the camera, aimed where the camera aims, and let the
CONE do the work while the world sits near black (0.01). Then the falloff frames the shot
rather than the exposure.

Two placement facts:

* **A very wide cone with high blend covers the frame as a gradient** with no visible circle
  -- 115 degrees at 0.92 blend. A narrow cone reads as a spotlight, which is a different look
  and usually the wrong one for a POV.
* **Put the lamp slightly AHEAD of the camera.** Held exactly at the eye, whatever is nearest
  the camera -- the viewer's own shoulders, a held prop -- is the closest surface in the cone
  and eats the beam, leaving the subject dark. A few centimetres forward gets past it.

**Flicker is dropouts, not noise.** Jitter every frame reads as a rendering fault. A failing
contact is steady, then gone for one to four frames, then back. Seed the RNG so a re-render
reproduces the flicker the user already approved.

## Shipping a skinned rig to Roblox

Everything here was paid for on one rig that looked **perfect in Blender and exploded in
Studio** -- hands scattered, shoulders dislocated. That gap is the whole lesson: Blender
composes a transform chain consistently for both bones and vertices, so the viewport is always
right. The engine does not have to, and Roblox does not.

**Read the spec before debugging.** `create.roblox.com/docs/art/modeling/specifications` states
requirements that no Blender check will ever flag:

* **Transformations** -- all bones "must be frozen and have scale values set to 1, 1, 1 and
  rotation values set to 0, 0, 0".
* **Root joint** -- the root bone should be at 0, 0, 0.
* **No Root influences** -- do not weight the root bone.
* **Max influences** -- 4 bones per vertex.
* **Single track animation** -- officially one clip per file. Several animation stacks in one
  FBX do import in practice; this is the documented position, not a measured limit.

### Every exported node must be scale 1, and a MISMATCH is what tears the skin

The single highest-value check. Re-import the FBX and print the object transforms:

```python
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=path)
for o in bpy.data.objects:
    if o.type in ("ARMATURE", "MESH"):
        print(o.type, o.name, [round(v, 5) for v in o.scale])
```

The working export and the broken one -- same rig, same geometry, same bones:

| File | Armature scale | Mesh scale | In Studio |
|---|---|---|---|
| known-good | 1.0 | 1.0 | correct |
| broken | **0.80836** | **0.20351** | hands and shoulders come apart |

Three factors were in play: armature object 0.2061, mesh object 0.296, and a 0.6876
`matrix_parent_inverse` on top. Blender multiplies them out identically for the armature and
the mesh, so nothing looks wrong at any zoom level. Roblox applies node scale to the skeleton
and to the vertices along different paths, and any disagreement tears the mesh.

Bake it out with `transform_apply`, rescale the location curves (BOTH levels -- see the
earlier section), and export with `global_scale=1.0`.

### transform_apply refuses multi-user data, and that is how the freeze silently stops

```
Error: Cannot apply to a multi user: Object "Armature.004", Armature "Armature.004", aborting
```

The trap that cost the most time, because the cause sat three steps from the symptom.
Splitting clips into per-clip scenes gave each scene its own armature OBJECT pointing at the
SAME armature DATA, and its own mesh object on the same mesh data. Multi-user data makes
`transform_apply` a no-op, so the scale never froze, so Roblox blew the rig apart. The user
guessed this before I did -- "we made animations into separate scenes, that's all I can think
of that might've broke it".

Purge the duplicates before the freeze; by then the poses are already recorded:

```python
keep = {arm.name} | {m.name for m in meshes_of(arm)}
for o in [x for x in list(bpy.data.objects)
          if x.type in ("ARMATURE", "MESH") and x.name not in keep]:
    bpy.data.objects.remove(o, do_unlink=True)
assert arm.data.users == 1, "armature data still shared"
```

### Studio needs exactly ONE root bone

An IK-driven rig usually has many. This one had **eight**: `Pelvis` plus seven unweighted IK
targets, pole targets and an eye target. Studio takes the top of the hierarchy as the character
root, so an eight-root skeleton has no character root at all -- and four of the strays were arm
bones, which is why the arms were what visibly failed.

Delete a bone only when neither it nor any descendant carries weight, re-parent whatever roots
remain, then assert:

```python
weighted = set()
for m in meshes_of(arm):
    names = [g.name for g in m.vertex_groups]
    for v in m.data.vertices:
        for g in v.groups:
            if g.weight > 0.0001:
                weighted.add(names[g.group])
doomed = [b.name for b in arm.data.bones
          if b.name not in weighted
          and not any(c.name in weighted for c in b.children_recursive)]
# delete in EDIT mode, re-parent the surviving roots under ROOT
assert [b.name for b in arm.data.bones if b.parent is None] == [ROOT]
```

**Re-parenting invalidates every key underneath it.** A pose key is local to its parent, so
moving a stray under the root silently corrupts its descendants -- measured once as the feet
landing 2.2 torso-lengths out. Record each affected bone's ARMATURE-SPACE matrix per frame
first, restructure, then write the matrices back: assigning `pb.matrix` re-derives the local
transform against the new parent. Walk parents before children and call `view_layer.update()`
between bones, or a child is keyed against a stale parent.

### Deleting bones leaves dead fcurves that collapse the export to ONE clip

After deleting 11 bones, all five actions still carried channels aimed at them -- 550 fcurves.
The FBX writer then exported only the currently-assigned action. The tell: the survivor changes
with whatever you assigned last. It was Walk, then Idle, purely from reordering.

```python
def drop_dead_curves(act, live):
    bags = []
    try:
        bags.append(act.fcurves)                  # 4.3 and older
    except AttributeError:
        for lay in act.layers:
            for st in lay.strips:
                for bag in st.channelbags:
                    bags.append(bag.fcurves)
    for coll in bags:
        for fc in list(coll):
            m = re.match(BONE_PATH_RE, fc.data_path)    # pose.bones["NAME"]
            if m and m.group(1) not in live:
                coll.remove(fc)
```

`bpy.data.actions.new("Idle")` when an `Idle` already exists silently becomes **`Idle.001`**.
The rebuilt clips then ship under the wrong names while the originals stay behind still full of
dead curves. That combination produced **zero** animation stacks. Remove the source actions once
their poses are recorded.

Count what is in the file; never trust the operator's return value:

```python
raw = open(path, "rb").read()
assert raw.count(b"AnimationStack") >= len(clips)
for name in clips:
    assert raw.count(name.encode()), "clip %s missing" % name
```

### UnitScaleFactor decides whether Roblox imports you 100x too large

`apply_scale_options` is not cosmetic. `FBX_SCALE_NONE` bakes the scale into the transforms and
leaves `UnitScaleFactor` at **1.0** -- "these coordinates are metres" -- so Roblox reads one
unit as one metre and the model arrives **exactly 100x** too big (measured 1020.02 studs
against an intended 10.2002). `FBX_SCALE_UNITS` writes **100**.

```python
import struct
raw = open(path, "rb").read()
i = raw.find(b"UnitScaleFactor")
print(struct.unpack_from("<d", raw, i + 43)[0])      # want 100.0
```

### Unweighted and unnormalised vertices are invisible in Blender

Blender leaves an unweighted vertex at its rest position, so it looks attached. Roblox sends it
to the model origin. Blender also normalises weights on the fly for display; Roblox uses them
raw. This rig had **1894 vertices whose weights did not sum to 1**, the shoulder bones among
them, and the viewport showed nothing wrong.

```python
for v in me.data.vertices:
    s = sum(g.weight for g in v.groups if g.group in bone_group_indices)
    assert s > 1e-6, "vertex %d has no weights" % v.index
    assert abs(s - 1.0) < 1e-4, "vertex %d sums to %f" % (v.index, s)
```

### Splitting a mesh into many MeshParts is not free

Roblox rebuilds the rig per MeshPart. A 14-part anatomical split measured **perfect** in
Blender -- rest skeleton 0.00% off, face count exact to the original -- and still came apart in
Studio, where the same geometry as 3 parts did not. If you split, keep an unsplit export as a
control and compare both in Studio before believing the split is innocent.

### Verify against the REST pose, and distrust a metric the known-good file fails

Two harnesses lied during this debug, both mine:

* Comparing a round-tripped FBX against a pose the FBX does not contain produced a convincing
  "finger drift, worsening down each chain, up to 48%". Pure artifact.
* A centroid metric reported **41 bones off** for the file that provably works and **32** for
  the file that was broken.

The second is the general tell: **when your metric ranks the known-good artifact worse, the
metric is wrong, not the artifact.** Stop and fix the harness.

Rest pose is the trustworthy comparison, because no pose ambiguity is left in it:

```python
arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis.identity()
bpy.context.view_layer.update()
# compare each bone's head distance from the root, normalised by the median ratio
```

On this rig that reported 0.00% error across all 74 bones for both files -- correctly saying the
skeleton was never the problem, and sending me to the object transforms instead.

### Never inherit a scale constant from another rig

A hardcoded `TARGET_STUDS / BIND_HEIGHT` copied from a different character shipped a **17.28**
stud model where 10.20 was wanted. Measure the rest height of the rig in front of you, every run:

```python
lo, hi = 1e18, -1e18
for m in meshes_of(arm):
    ev = m.evaluated_get(bpy.context.evaluated_depsgraph_get())
    for v in ev.data.vertices:
        z = (ev.matrix_world @ v.co).z
        lo, hi = min(lo, z), max(hi, z)
k = TARGET_STUDS / (hi - lo)
print("rest height %.4f -> k %.4f -> %.4f studs" % (hi - lo, k, (hi - lo) * k))
```

### The order of operations that actually ships

1. **Record** every clip's pose, per frame, as armature-space matrices. This also bakes the
   IK/constraint result, so constraints can then be removed.
2. **Purge** duplicate objects so no datablock is multi-user.
3. **Restructure**: delete unweighted control bones, re-parent to one root.
4. **Rewrite** the recorded matrices onto the restructured rig, parents before children.
5. **Derive** the scale from a measured reference in THIS file, freeze it with
   `transform_apply`, rescale location curves at both levels.
6. **Normalise** weights, cap influences at 4.
7. **Export** with `global_scale=1.0`, `apply_scale_options="FBX_SCALE_UNITS"`.
8. **Verify the written bytes**: unit factor, stack count, clip names, bone count, and a
   re-import showing every node at scale 1.

## Exporting from a file you do not own

The right call when the asset is someone else's and they will keep editing it: never fork
it. Read their .blend headless, write only the FBX, keep zero local edits -- then their next
version drops straight in. Verify that with a hash:

```bash
md5sum their.blend        # before and after the export run; must be identical
```

The risk this creates is different from drift, and worse, because it is quiet. An exporter
hardcodes scene names, clip names and a frame rate. If they rename a scene, change a range,
or **add a sixth animation**, the script exports the five it knows about and reports success.
You ship a file silently missing their new work.

So fingerprint the source and diff it before every export: per scene the effective fps, frame
range, bone count, a hash of the rest skeleton including parenting, a hash of the geometry,
and the SET of scene names. Fail loudly and name the difference:

```
SOURCE CHANGED -- 2 difference(s). Re-exporting blind would be a guess:
  Run   effective_fps  30.0 -> 60.0   (timing would be wrong)
  Run   frame_end      240 -> 300     (clip length changed)
```

Test the detector against a deliberately stale baseline. A change detector that has only ever
returned "no change" is untested. Worked implementation:
`tools\source_check.py` (a fingerprint checker, see tools\).

## Reference motion for character work

Retarget a walk cycle where a clip fits. Where none does (a stylised heavy character), build it
from formulas timed against a reference video: see "A walk built from formulas". **Mixamo** (free rigged characters and
animations, FBX), the **CMU Motion Capture Database** (thousands of BVH clips),
**Bandai Namco Research** (3,000+ free BVH moves), **Rokoko** (free tier plus a Blender
plugin). Import BVH with `bpy.ops.import_anim.bvh` and retarget.

Mechanical motion has no equivalent library and is authored from measurements, which is
what the rest of this skill covers.

## Other tools in this space

Scripting `bpy` directly is the reliable path and the only one that works headless.
**blender-mcp** (`github.com/ahujasid/blender-mcp`) drives a *running* Blender over a
socket, which is good for live iteration but needs the GUI open and has no animation tools
in the free version. **BlenderLLM** targets CAD modelling, not animation. **SceneCraft**
(arXiv 2403.01248) contributes the transferable idea: write code, render, read the render,
iterate.

## Character cutscenes and fast renders

Full lessons: the `roblox` skill's `blender-cutscene.md` (first-person R6 prop shot, 12 rounds of corrections).

- **Animate the prop first, then put the hands on it.** Key the prop's world path, bake the hands onto grip points on it, and aim the head ahead of them. One arm acts; the other joins only for a two-handed hold, as a true mirror across the body plane.
- **One hand holding a prop = the prop is LOCKED to that hand** (fixed offset taken at the grab frame: tape = hand @ offset). Never give a one-hand-held prop its own keyed path with the fist merely aimed at a grip point: it rotates on its own and reads as floating (user: "it feels like it has its own movement not parented to left arm"). Where the prop path must be exact (insert into a slot), invert it: arm = prop @ offset^-1. Only a two-hand hold may be prop-driven. Check: hand-to-prop relative transform drift < 2 mm / 1 deg over the hold.
- **Find which way a part faces from its mesh** (the open boundary loop, the wide end of a cone). Guessing a local axis aimed a lamp light the wrong way.
- **Don't move the user's set dressing** to improve a shot, and **don't render until asked**.
- **A rigid fist grips by overlap.** The grip point goes inside the prop (~4 cm), so the prop sinks into the brick; count the prop's vertices inside the fist's box to prove it. Hold a two-hand look by the bottom corners so the label shows.
- **A seamless loop has to freeze everything else.** Flat handles at the loop ends, noise faded to ~0 at the start, and a STEPPED hold on every other animated thing (off-camera rigs carrying lights included). Verify with a rendered-frame diff, not only the poses.
- **EEVEE for previews, Cycles for finals.** EEVEE: 6 min vs 63, set `eevee.light_threshold = 0.0001`, but the user saw it as pixelated with lighting pops. Cycles final: 64 spp + denoise + persistent data, cull off, PNG frames resumable, 30 fps via `frame_step = 2` + shutter 1.0, encode with exact `-frames:v`. Check the Cycles preferences use the GPU (the compute device can be NONE). Render with CLI overrides so the .blend isn't touched. Preview 2 s before the full run.

## Skinned characters: skin, IK, cloth and a walk that reads heavy

Learned on one character (Pumpkin Rabbit, Blender 5.2.2, 2026-10-13) taken from a bare rig to an
approved Walk and Idle. Every rule below was wrong first, or is a measured number. The scripts
are in `tools/character/` next to this file (`README.md` there lists them). They are worked
examples with that character's names at the top (`PumpkinRabbit_Rig`, `Cube.009`): change the
names, keep the method.

### Working order, set by the user

- **Pose change: a plain solid screenshot from the user's angle first.** No cloth sim and no
  render on a pose nobody has looked at. A 157 s sim ran on hands that were visibly broken.
- **Animation change: rebuild it live and stop.** No cloth bake, no save, no render until the
  user has watched it and said so. A render request covers that one version only.
- **A limit of your own that fails means the pose is wrong.** Never raise it to pass.
- **When the user shows you a control, use that control.** Their own pose is the reference; a
  drawing is a look, not a set of angles (stroke angles measured off concept art broke the hands).
- "Check" means report. Changing rest bones or weights of approved work needs a go.
- One glitch reported means fix the whole class, and show before and after from their angle in
  solid shading. Creases show there, not in the textured render.

### When the MCP bridge is dead, the addon socket is not

The `blender` MCP server can fail to connect while the addon inside Blender still listens on
`127.0.0.1:9876`. Talk to it directly:

```bash
python -I tools/character/bl.py script.py 170        # run a file inside the open Blender
python -I tools/character/look.py out.png '{"mode": "frames", "frames": [1, 31], "view": [0, -1, 0.1], "target": ["Cube.005"], "shading": "solid", "max_size": 1600}'
```

`look.py` modes are `viewport`, `views`, `frames`; `target` takes object names. Traps:

- **It clips at the near side of the target's box.** One empty as a target cuts holes in the
  mesh. Aim at two empties set about 1.3 apart either side of the thing.
- A call that runs long drops the connection. Slice long work (see cloth) and never send
  anything while a sliced job is between slices.
- Stash functions in `bpy.app.driver_namespace` to call them again from the next script.
- Edit mode from a socket script needs a context override:
  `with bpy.context.temp_override(window=w, area=view3d, region=its WINDOW region):`.

### Reading a pose the user left on screen

They pose a control and do not key it. **Any `frame_set` wipes it.** Read without changing the
frame, store at full precision, then key it.

```python
for pb in bpy.context.selected_pose_bones or []:      # 'Bone' has no .select in 5.x
    print(pb.name, list(pb.rotation_quaternion), list(pb.location))
```

`q_user_pose.py` prints every bone whose live value differs from its curve at the current frame.
Apply the result as a constant turn on top of every key (`step @ key`), remember the turn on the
action as a custom property, and take the old one off first, so a re-run replaces it and the
existing sway survives (`idle_hands.py`).

### Audit the rig before animating it

`rig_audit.py`, read-only, rest pose. What it found on a rig that looked clean:

- **Left and right rolls do not match**: thumbs 55-73 degrees apart, hips 89, ears 30-45,
  shoulders 26. The same local rotation does different things on each side.
  **Never copy a quaternion across sides.** Give the turn in body axes and convert per bone:
  `left_rest.inverted() @ FLIP @ right_rest @ turn @ right_rest.inverted() @ FLIP @ left_rest`
  with `FLIP = Matrix.Diagonal((-1, 1, 1))`.
- Left and right weights differ too (one side blended, the other hard). Compare per pair.
- 14 of 79 deform bones carried no skin. Dead weight for an engine with a bone budget.
- Joint pivots against the centre of the skin ring they bend (elbows were 0.03 of the radius
  off: fine). Check before blaming a pivot for a bad bend.
- Which axis each finger and the jaw really bends about, per side (fingers curled on local Z,
  + on the right and - on the left). Measure it; see the `character-animation` skill's
  `rig_profile.py`, and judge the cumulative angle at the end of a chain, not the local value.
- Modifier order. Subsurf BEFORE Armature means the armature bends the subdivided mesh with
  interpolated weights, so a forearm of four rings is all the skin there is.

Mirroring the rolls only helps hand-posing with paste-flipped. It is not needed for scripted
animation; the user skipped it.

### IK: the hand's heading belongs to the box

Typical set-up: the lower arm has `IK` (chain 2) to an `IK Hand` control with a pole, and the
hand bone has `COPY_ROTATION` from that control in world space. Legs the same.

- **Pose a hand by rotating the IK hand box. Do not move wrist targets or poles to fit a pose.**
  The hand keeps its heading while the forearm rolls underneath it, and all of that roll lands
  in the wrist: pulling the elbows in 3 units rolled the forearm 49 degrees.
- Moving the arms moves anything pinned to them, so it costs a cloth bake. Turning the box costs
  nothing.
- Feet: flat for the whole time they are planted, tipped only in the air. Print slip per frame
  against the ground speed (0.0002 on the approved walk) and that no sole goes under the floor.

### Wrist wringing means there is no forearm twist bone

With no twist bone an 89 degree hand turn landed on two rings 0.2 long: edges squeezed to 0.35
of rest and stretched to 2.12. Linear blend between two bones turned by an angle shrinks the
skin to `cos(angle / 2)` at the half-way weights (89 degrees = 0.71), so split the turn until no
step is large.

Fix, `forearm_twist.py` (idempotent): one bone per side, child of the lower arm, in line with it
and with the same roll, deform on, carrying a share of the hand's twist.

```python
pb.rotation_mode = "XYZ"
driver = arm.driver_add(pb.path_from_id("rotation_euler"), 1).driver
driver.type = "SCRIPTED"
var = driver.variables.new()
var.name, var.type = "twist", "TRANSFORMS"
t = var.targets[0]
t.id, t.bone_target = arm, "Hand.R"
t.transform_type, t.rotation_mode, t.transform_space = "ROT_Y", "SWING_TWIST_Y", "LOCAL_SPACE"
driver.expression = "twist * 0.7"       # LOCAL_SPACE includes the hand's constraint
```

Weights move by height along the forearm with a smoothstep between two skin rings; the lower arm
keeps the rest. **Start the twist zone below anything pinned to the forearm** (straps, cuffs,
bone-parented props), or they need a new bake. Then assert each twist bone turns
`share x hand twist` within 1.5 degrees. Result: worst squeeze 0.35 -> 0.55, edges under 0.7 of
rest 26 -> 4, worst stretch 2.12 -> 1.48. The shoulder wants the same thing (48 degrees there).

### Prove a skin fix on paper before building it

`skin_lab.py`, read-only. Work the linear blend out by hand on the evaluated mesh:

```python
skin = {n: pose[n].matrix @ bones[n].matrix_local.inverted() for n in group_names}
rest = [blend(w, skin).inverted() @ p for w, p in zip(weights, posed)]     # undo the skinning
# a bone that does not exist yet is just one more matrix:
skin["T0"] = pose[la].matrix @ Matrix.Rotation(share * twist, 4, "Y") @ bones[la].matrix_local.inverted()
```

Re-blend with the candidate weights and print edge length over rest length: shortest, longest,
count under 0.7, count over 1.4. Try several shares and ring heights in one run, pick by the
numbers, then build once.

### Creases in skinned clothing are weight blends, not cloth

A crease in a bib was a chest-to-spine blend only 0.4 tall: 40 degrees of bend per unit, edges
squashed to 25%. The body under it has the same weights and a Subsurf hides it. Fix: re-split
each vertex's spine weight by world height, smoothstep over about 0.65 either side of each
joint, on every worn piece together so they stay on each other (`spine_blend` in
`cloth_pieces.py`). 40 -> 9.8 degrees per unit. Measure sliding against the body before and
after as well.

### Cloth over a looping clip: simulate once, bake to shape keys

"Make it follow the legs" with weights or a shrinkwrap was rejected twice. What works
(`cloth_pieces.py`, driven by `clip.sh`):

1. Simulate in slices of about 25 s (`cloth_begin`, then `cloth_step` until it returns True).
   One long call drops the socket. Touch nothing in Blender between slices.
2. Warm up before recording and print the cycle-to-cycle gap. An apron needed 4 cycles
   (0.199 -> 0.003). Ease the last 40 frames onto frame 1.
3. Record one cycle of evaluated verts with Subsurf and Solidify off, undo the skinning per
   vertex (the inverse blend above) and store ABSOLUTE shape keys.
4. Heavy fabric is tension 600 with bending 40. Proof it does not stretch: free edges stay
   0.99-1.01 of rest length.
5. Pin by height with a smooth blend. Rows modelled tighter to the body than the collision
   margin (waist 0.10 against a margin of 0.30) go in `vertex_group_object_collisions`, or pin
   and collider fight and the edge crumples.
6. Clip check: verts, face centres and edge midpoints against the evaluated body, every third
   frame. Open meshes report false "inside", and an arm resting over the bib is not clipping:
   look at depth and at which bone owns the covering faces.

Traps, each one cost a bake:

- **Cycle modifiers added to a live action do not reach the evaluated copy while anything else
  holds the action.** The skeleton stopped after one pass and the cloth settled dead still. Write
  the looping pose from the curves yourself with the action off, and `action.update_tag()`.
- **A number that is too clean is the tell** ("strays 0.00"). The check that catches a frozen
  bake: fully pinned verts of the recording against plain skinning, asserted.
- Simulate with keys present by locking to Basis (`show_only_shape_key`, index 0). Add every key
  while the Key is still relative; an absolute key is filed at the current `eval_time`.

### One cloth clock for every clip

Shape-key actions ignore the armature's action, so the walk's cloth swung during the idle. Each
piece's Key is `[Basis, Walk shapes, Idle shapes]`, and its `eval_time` follows one custom
property on the armature that each clip's action keys (LINEAR, with a CYCLES modifier).
Switching the action switches all the cloth.

```python
arm["cloth_time"] = 0.0
arm.update_tag(); bpy.context.view_layer.update()   # or the driver is invalid for good
keys.use_relative = False
d = keys.driver_add("eval_time").driver
d.type = "SUM"
v = d.variables.new(); v.type = "SINGLE_PROP"
v.targets[0].id, v.targets[0].data_path = arm, '["cloth_time"]'
```

- The shape count follows the cycle length (94 frames at every 2nd = 48 shapes). Anything that
  asserts a count must compute it; a hard-coded 53 failed the save after a retime.
- Retiming a clip: move the last `cloth_time` key to the new end, or the cloth pops at the loop
  until it is baked again.

### A thick strip is a chain, not cloth

Blender cloth on a closed thick mesh (a tie) is a rigid beam or a balloon; seven parameter sets
failed. Use a hanging chain from the knot: 6 links, follow-the-leader, 4 substeps, a plane
constraint so it cannot pass behind its modelled pose, rigid edgeways and soft front to back;
skin the verts to the links and bake like cloth (`tie_swing`). Give springs in gravity units
(`k * dt^2`). Measure the tip against the KNOT: a "+-0.24 swing" was only the torso tilting under
a tie that never moved.

### A walk built from formulas

`walk.py` writes the whole cycle from functions of phase, on the reference clip's own clock
(120 frames, two steps, a foot down for 62), and plays it in `LOOP` frames. Legs are keyed every
frame, everything else every other frame. It prints its own proof on every build: loop seam,
foot slip, knee range, head bob and sway. To change speed, change `LOOP` and read the cycle
length from the action everywhere downstream; do not retime the formulas.

An idle keys legs, toes, thumbs and jaw still, so the walk cannot leak into it when the action
is switched.

### Heavy is in the legs, not in a shake

Three versions of "he stomps, so he shakes" were rejected as robotic: a ringing shake through
the whole body (period 20 frames, decay 8), the same at a third strength, and a fast shudder
(period 7, decay 5). What was approved:

- **No footfall shake on torso or head at all.** A heavy body sinks; it does not rattle.
- **The legs carry the weight**: sit lower, bob more, reach the low point a third into the step,
  then rise slowly. No bounce.
- **Only loose parts answer a footfall**, each with one slow swing and a small return, each with
  its own delay and its own period. One wave on every part at once moves him like a block.
- A big mass swings slowly and dies in one swing. A fast wobble says small, stiff or mechanical.
- Then shorten the cycle about 10% (104 -> 94), or the slow rise makes him "feel slower".

```python
DROP, BOB, HEAVY, EARLY, SHAKE = 0.43, 0.17, 0.3, 0.35, 1.0

def up(p):                       # pelvis height: short fall, low point early, long slow rise
    since = TAU * (2 * p + 0.033)
    return math.cos(since + HEAVY * math.sin(since) + EARLY * (1 - math.cos(since)))

def jolt(p, late, swing):        # loose parts only: frames after the footfall, period in frames
    t = ((2 * p) % 1.0) * T / 2 - late
    t += T / 2 if t < 0 else 0
    return SHAKE * math.exp(-t / (0.42 * swing)) * math.sin(TAU * t / swing)
```

Periods that read right on a character about 16 units tall (clip frames): ears 34, arms 28,
jaw 26, fingers 22; delays 3 to 8 frames, later further down a chain. Wrists drag about 7
degrees behind the arm swing, and fingers curl a beat behind the hand, index to pinky. Chest and
head get a degree or so of counter-nod off `up()` with a small lag, nothing more.

### Reading a reference video

- Contact sheets with time stamps: 4 fps for the whole clip, 15 fps cropped for one cycle.
- Real numbers from one distinct colour tracked at 60 fps (`video_track.py`: ffmpeg rawvideo
  into numpy, mask, mean position, autocorrelation for the period). One clip gave: step 1.0 s,
  bob 8% of height, sway 14%, a 32-frame rise against a 24-frame drop.
- Mask the editor's own UI out (a toolbar button of the same colour was tracked first).
- Say what the frames cannot show. No shake could be confirmed, and the audio was not heard.

### Save, preview and teaser renders

- **Assert the state before saving** (`run_save.py`): right file path, the action and frame
  range it should open on, no cloth modifier left on, every Key absolute with a valid driver and
  the computed shape count.
- Nearly full disk: Blender writes a temp copy beside the file, so check free space, remove the
  file, then `save_as_mainfile`. Render frames go to a scratch folder on another drive.
- Previews headless with CLI overrides so the .blend is untouched (`render.py`: EEVEE, 64
  samples, simplify on). Encode outside Blender; ffmpeg's `drawtext` needs an explicit
  `fontfile='C\:/Windows/Fonts/arial.ttf'` on Windows or it segfaults.
- **Silhouette for a teaser** (`silhouette.py`): hide everything not parented to the rig, set
  `view_layer.material_override` to a black emission, `film_transparent`, RGBA PNG, then
  composite over any backdrop in ffmpeg (`color=0x8a1414` plus `vignette=PI/4`).

## Seeing two meshes overlap: colour-coded x-ray

Use this when one mesh may poke through another (a neck through a collar, a sleeve through a
jacket). Solid shading hides the overlap; this shows it.

1. Hide every mesh except the two you compare (`hide_viewport = True`). Store the names so you
   can restore them.
2. Colour the objects, not the materials: `obj.color = (r, g, b, 1)`. Set the viewport to
   `shading.type = 'SOLID'`, `shading.color_type = 'OBJECT'`, `show_xray = True`,
   `xray_alpha = 0.35`.
3. Aim the view with the lesson formula (`view_rotation = fwd.to_track_quat('-Z', 'Y')`, check
   the dot product is 1.0), then take a screenshot. Look at the worst pose, not the rest pose.
4. Put the colours and visibility back afterwards from the stored values.

Measured on PumpkinRabbit (neck tube red, collar blue): the tube's lower back sat outside the
collar at frame 107. The x-ray view showed it without guessing.

## Checklist

1. Confirm the Blender version and that it can open the file. Check for an open GUI session.
2. List the SCENES before anything else. Several scenes means several rigs, several frame
   rates and several ranges; switch the active scene before any `frame_set`.
3. Identify the rig type: armature or node transform.
4. Enumerate the parts. Find the real hinge hardware; do not assume the pivot.
5. Set pivots on the hardware, on the empty **and** its meshes.
6. Work in world space; never write local eulers on an imported hierarchy.
7. Score candidate poses on every property the answer must have, and check symmetry.
8. Verify worst-case numbers across the range, and refuse to save on failure.
9. Render, build a contact sheet, look at it.
10. Report which numbers were checked and which were not.

Exporting as well:

11. Never write to the user's .blend while their GUI holds it. Work on a copy.
12. Unhide, select, and **assert the selection took** before any `use_selection` export.
13. Take the scale factor from a reference object measured in the file, at bind pose.
14. Bake scale into bone and vertex data; rescale object **and** pose-bone location curves.
15. Re-import and compare deformed mesh vertices per frame, allowing a one-frame shift.
16. Grep the written file for `LimbNode` / `Deformer`. Size is not evidence.
17. Read `UnitScaleFactor` out of the FBX itself. A Blender round trip cannot
    check it, and getting it wrong is a silent 100x in the target engine.
18. Set `fps` **and** `fps_base`, then assert the effective rate and each clip's DURATION
    in seconds. Frame-indexed checks cannot see a wrong frame rate.
19. Normalise skin weights and cap influences to the engine's limit. Blender normalises at
    evaluation, so the viewport can never show you this.
20. Strip F-curves that key deleted bones, then count `AnimationStack` against your clip
    table -- not against `len(bpy.data.actions)`.
21. Sample BETWEEN keyframes for twitches, and compare against the source as a baseline.
22. Exporting from someone else's file: hash it before and after to prove you wrote
    nothing, and diff a structural fingerprint so their edits fail loudly.
23. Re-import and assert **every** node is scale 1. A mismatch between the armature's scale
    and the mesh's is invisible in Blender and tears the skin in the engine.
24. Assert no datablock is multi-user before `transform_apply`. It refuses multi-user data,
    and the refusal is the reason a freeze silently does nothing.
25. Assert the skeleton has exactly ONE root. Unweighted IK/pole/aim targets are extra roots,
    and an engine that takes the top of the hierarchy as the character root gets none.
26. After deleting or re-parenting bones, re-key the affected subtrees from recorded
    armature-space matrices, and check that `actions.new(name)` did not become `name.001`.
27. If a metric ranks a known-good artifact WORSE than the broken one, fix the metric before
    acting on it. Compare at rest pose, where there is no pose ambiguity to get wrong.

Skinned characters as well (section "Skinned characters"):

28. Audit the rig first: left/right rolls and weights, unused deform bones, modifier order.
    Never copy a quaternion across sides.
29. Pose hands with the IK hand control, never by moving wrist targets or poles.
30. Wrung wrist or shoulder: add a twist bone, and prove the weights in `skin_lab.py` first.
31. Pose change: solid screenshot from the user's angle before any sim or render.
32. Animation change: rebuild live and stop. Bake, save and render only after approval.
33. Cloth: assert pinned verts against plain skinning, print the loop gap, compute shape counts.
34. Heavy walk: weight in the legs, no shake on torso or head, loose parts swing late and slow.
