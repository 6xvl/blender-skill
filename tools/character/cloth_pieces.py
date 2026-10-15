"""The rabbit's loose pieces over his looping clips: the apron and the arm straps as real cloth, the tie as a hanging
chain. Each is simulated once per clip and stored as shape keys, so it plays back without a simulation.

A piece's keys are [Basis, the Walk's shapes, the Idle's shapes] and all follow one number on the armature,
"cloth_time", which each clip's action animates. Switching the armature's action switches the cloth with it.

Exec inside the live Blender. Once: spine_blend("Cube.005", "Cube.018", "Plane.008") (apron, tie, back strap).
Then per clip:
    cloth_begin("apron", "straps", clip="Idle"), cloth_step() until it returns True
    tie_swing("Idle")
    cloth_bake("Idle")
The cloth runs in slices because one long call drops the bridge. The functions live in bpy.app.driver_namespace.
"""
import time

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

NS = bpy.app.driver_namespace
sc = bpy.context.scene
arm, body = bpy.data.objects["PumpkinRabbit_Rig"], bpy.data.objects["Cube.010"]
PREROLL = 60                      # frames in which rest blends into the clip before it starts cycling
CLIPS = {"Walk": 2, "Idle": 5}    # clip (its action) -> frames between stored shapes; keys are stored in this order
WARM = {"Walk": 5, "Idle": 4}     # cycles simulated and thrown away before the kept one (the walk's apron needs 4 to
                                  # settle; the Idle's apron needs 1, its loose straps 4: with 2 one still looped 0.07 off)
TIME = "cloth_time"
TIE = "Cube.018"

# pin: world heights where the piece stops being free and where it is fully held (left out: the pin group it has).
# fitted: colliders only push the cloth under this height; above it the piece keeps the fit it was modelled with
#         (the apron sits 0.1 off the waist, tighter than the collision margin, which crumpled the waistline).
# colliders: object -> (how far it keeps the cloth off its surface, friction). The rest are Blender's cloth settings.
PIECES = {
    "apron": dict(objs=("Cube.005",), pin=(14.2, 14.7), fitted=14.2, colliders={"Cube.010": (0.3, 8.0)}, grav=6.0, quality=24,
                  tension=600.0, shear=300.0, bend=40.0, mass=0.3, air=1.5, tdamp=30.0, bdamp=4.0),
    "straps": dict(objs=("Plane.005", "Plane.006", "Plane.009", "Plane.010"),      # ride the forearm bones, no skinning
                   tension=2.0, shear=2 / 3, bend=0.003, air=0.05, tdamp=0.3, bdamp=0.01),
}
SETTINGS = {"tension": ("tension_stiffness", "compression_stiffness"), "shear": ("shear_stiffness",), "bend": ("bending_stiffness",),
            "tdamp": ("tension_damping", "compression_damping", "shear_damping"), "bdamp": ("bending_damping",),
            "air": ("air_damping",), "mass": ("mass",), "quality": ("quality",)}
WORN = [name for piece in PIECES.values() for name in piece["objs"]] + [TIE]
RESIZING = ("SUBSURF", "SOLIDIFY")   # modifiers that change the vertex count: off while recording

SPINE = ("Pelvis", "Spine", "Spine.001", "Chest")
BLEND = 0.65   # half the height each spine joint's bend is spread over; the artist's 0.2 creased the bib at 40 deg a unit


def smooth(t: float) -> float:
    u = max(0.0, min(1.0, t))
    return u * u * (3 - 2 * u)


def cycle(clip: str) -> int:
    """Frames in the clip's loop (its builder keys 1 to this + 1)."""
    return int(bpy.data.actions[clip].frame_range[1]) - 1


def curves(clip: str):
    action = bpy.data.actions[clip]
    return action.layers[0].strips[0].channelbag(action.slots[0]).fcurves


def play(action):
    """Puts the action on the armature and returns the one it had."""
    anim = arm.animation_data
    was = anim.action
    anim.action, anim.action_slot = action, action.slots[0]
    return was


def move_modifier(obj, name: str, index: int):
    with bpy.context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_move_to_index(modifier=name, index=index)


def resizing_off(obj) -> dict:
    was = {m.name: m.show_viewport for m in obj.modifiers if m.type in RESIZING}
    for name in was:
        obj.modifiers[name].show_viewport = False
    return was


def resizing_back(obj, was: dict):
    for name, shown in was.items():
        obj.modifiers[name].show_viewport = shown


def skins_at(clip: str, frames) -> dict:
    """World skinning matrix of every bone on these frames of the clip."""
    was, to_arm, out = play(bpy.data.actions[clip]), arm.matrix_world.inverted(), {}
    for f in frames:
        sc.frame_set(f)
        out[f] = {b.name: arm.matrix_world @ arm.pose.bones[b.name].matrix @ b.matrix_local.inverted() @ to_arm for b in arm.data.bones}
    play(was)
    return out


def bone_weights(obj) -> list:
    """Each vertex's (bone, share) pairs; empty for a vertex no bone skins."""
    names = {g.index: g.name for g in obj.vertex_groups if g.name in arm.data.bones}
    out = []
    for v in obj.data.vertices:
        w = [(names[g.group], g.weight) for g in v.groups if g.group in names and g.weight > 0]
        total = sum(x for _, x in w)
        out.append([(bone, x / total) for bone, x in w] if total > 0 else [])
    return out


def spine_shares(z: float) -> tuple:
    """How a point at this world height splits between the spine bones, in SPINE order."""
    s = [smooth((z - ((arm.matrix_world @ arm.data.bones[b].head_local).z - BLEND)) / (2 * BLEND)) for b in SPINE[1:]]
    return 1 - s[0], s[0] - s[1], s[1] - s[2], s[2]


def spine_blend(*objects: str):
    """Re-splits each vertex's spine weight by its height, so the torso's bends spread out instead of creasing.
    Everything worn on the torso gets the same split, so the tie and straps stay on the apron."""
    for name in objects:
        obj = bpy.data.objects[name]
        if name + "_artist_weights" not in bpy.data.meshes:
            keep = obj.data.copy()
            keep.name, keep.use_fake_user = name + "_artist_weights", True
        groups = [obj.vertex_groups.get(b) or obj.vertex_groups.new(name=b) for b in SPINE]
        spine = {g.index for g in groups}
        moved = 0
        for v in obj.data.vertices:
            total = sum(g.weight for g in v.groups if g.group in spine)
            if total <= 0:
                continue
            for group, share in zip(groups, spine_shares((obj.matrix_world @ v.co).z)):
                group.add([v.index], total * share, "REPLACE")
            moved += 1
        print(f"spine blend: {name} {moved} of {len(obj.data.vertices)} verts")


KNOT_Z, LINKS, SUBSTEPS = 17.8, 6, 4   # the tie is held above this world height; chain links below it; steps per frame
# Tuned on the 104-frame walk. With no stiffness or hold the tip swung 0.34 either side and 0.74 front to back and
# bowed 0.19 off straight; these give 0.28, 0.32 and 0.09.
DRAG, STIFF, HOLD = 6.5, 60.0, 8.0


def tie_swing(clip="Walk", gravity=59.0, drag=DRAG, lift=0.07, straight=0.5, stiff=STIFF, hold=HOLD, rub=0.5, cycles=10):
    """The tie as a chain hanging from its knot: it falls plumb while the torso leans, swings with the sway and
    cannot pass behind the place the modelled tie lay (the bib), which it rests `lift` in front of.
    Blender's cloth was tried first and dropped: the tie is a thick closed strip, which cloth either holds rigid
    or lets balloon. straight: how firmly the band stays straight edgeways (0 a rope, 1 a ruler). stiff: the spring
    that straightens it front to back, and hold: the spring by which the knot keeps the tie the way it was modelled
    against the chest (0 hangs plumb); both are pull per unit of distance, on the scale of gravity over the tie's
    length (about 20). drag: how fast a swing dies, per second. Leaves the cycle for cloth_bake(clip).
    ponytail: shape keys do not export to Roblox; put these links on bones when the rabbit is exported."""
    obj, T = bpy.data.objects[TIE], cycle(clip)
    move_modifier(obj, next(m.name for m in obj.modifiers if m.type == "ARMATURE"), 0)   # skin, then subdivide: keys replay exactly
    world = obj.matrix_world
    rest = [world @ v.co for v in obj.data.vertices]
    weights = bone_weights(obj)

    rows = {}
    for at in rest:
        if at.z <= KNOT_Z + 0.05:
            rows.setdefault(round(at.z, 1), []).append(at)
    line = sorted((sum(pts, Vector()) / len(pts) for pts in rows.values()), key=lambda c: -c.z)

    def centre(z: float) -> Vector:
        for a, b in zip(line, line[1:]):
            if b.z <= z <= a.z:
                return a.lerp(b, (a.z - z) / (a.z - b.z)) if a.z > b.z else a.copy()
        return (line[0] if z > line[0].z else line[-1]).copy()

    tip_z = min(at.z for at in rest)
    link = (KNOT_Z - tip_z) / LINKS
    home = [centre(KNOT_Z - link * k) for k in range(LINKS + 1)]
    length = [(home[k + 1] - home[k]).length for k in range(LINKS)]
    along = [sum(length[:k]) / sum(length) for k in range(LINKS + 1)]
    shares = [spine_shares(c.z) for c in home]
    X = Vector((1, 0, 0))

    def frame(a: Vector, b: Vector, side: Vector) -> Matrix:
        down = (b - a).normalized()
        side = (side - side.dot(down) * down).normalized()
        return Matrix((side, down.cross(side), down)).transposed()

    home_frame = [frame(home[k], home[k + 1], X) for k in range(LINKS)]
    front = [home_frame[min(k, LINKS - 1)].col[1].copy() for k in range(LINKS + 1)]   # points away from the body
    assert all(n.y < 0 for n in front), front

    skins = skins_at(clip, range(1, T + 1))
    skins[T + 1] = skins[1]
    sc.frame_set(1)

    def carried(f: int, k: int) -> Matrix:
        out = Matrix(((0,) * 4,) * 4)
        for bone, share in zip(SPINE, shares[k]):
            out += skins[f][bone] * share
        return out

    glued = {f: [carried(f, k) @ home[k] for k in range(LINKS + 1)] for f in skins}
    wall = {f: [(carried(f, k).to_3x3() @ front[k]).normalized() for k in range(LINKS + 1)] for f in skins}
    side = {f: (skins[f]["Chest"].to_3x3() @ X).normalized() for f in skins}

    at = [glued[1][k] + wall[1][k] * lift for k in range(LINKS + 1)]
    at[0] = glued[1][0].copy()
    was = [q.copy() for q in at]
    dt = 1 / (sc.render.fps * SUBSTEPS)
    fall = Vector((0, 0, -gravity)) * dt * dt
    rec, starts = {}, []
    for lap in range(cycles):
        for f in range(1, T + 1):
            if f == 1:
                starts.append([q.copy() for q in at])
            if lap == cycles - 1:
                rec[f] = [q.copy() for q in at]
            for step in range(1, SUBSTEPS + 1):
                u = step / SUBSTEPS
                held = [glued[f][k].lerp(glued[f + 1][k], u) for k in range(LINKS + 1)]
                out = [wall[f][k].lerp(wall[f + 1][k], u).normalized() for k in range(LINKS + 1)]
                across = side[f].lerp(side[f + 1], u).normalized()
                for k in range(1, LINKS + 1):
                    moved = (at[k] - was[k]) * max(0.0, 1 - drag * dt)
                    was[k] = at[k].copy()
                    at[k] = at[k] + moved + fall
                at[0] = held[0]
                for k in range(1, LINKS + 1):
                    at[k] = at[k] + (held[k] + out[k] * lift - at[k]) * (hold * dt * dt)
                for k in range(1, LINKS):
                    bow = at[0].lerp(at[LINKS], along[k]) - at[k]   # back to the straight line from knot to tip
                    edge = across * bow.dot(across)
                    at[k] = at[k] + edge * straight + (bow - edge) * min(1.0, stiff * dt * dt)
                for _ in range(8):
                    for k in range(1, LINKS + 1):
                        at[k] = at[k - 1] + (at[k] - at[k - 1]).normalized() * length[k - 1]
                        sunk = (at[k] - held[k]).dot(out[k]) - lift
                        if sunk < 0:
                            at[k] = at[k] - out[k] * sunk
                            was[k] = was[k] + (at[k] - was[k]) * rub
    rec[T + 1] = [q.copy() for q in at]
    starts.append(rec[T + 1])
    settle = [round(max((a - b).length for a, b in zip(x, y)), 3) for x, y in zip(starts, starts[1:])]

    def link_matrix(f: int, k: int) -> Matrix:
        turn = frame(rec[f][k], rec[f][k + 1], side[f]) @ home_frame[k].transposed()
        return Matrix.Translation(rec[f][k]) @ turn.to_4x4() @ Matrix.Translation(-home[k])

    local = world.inverted()
    shape = {}
    for f in range(1, T + 2):
        links = [link_matrix(f, k) for k in range(LINKS)]
        knot = carried(f, 0)
        placed = []
        for i, p in enumerate(rest):
            if p.z >= KNOT_Z:
                skin = Matrix(((0,) * 4,) * 4)
                for bone, x in weights[i]:
                    skin += skins[f][bone] * x
                placed.append(local @ (skin @ p))
                continue
            k = min(LINKS - 1, int((KNOT_Z - p.z) / link))
            t = (KNOT_Z - p.z) / link - k
            here = links[k] @ p
            if t < 0.5:
                other, share = (links[k - 1] @ p, 0.5 - t) if k else (knot @ p, 1 - 2 * t)
            else:
                other, share = links[min(k + 1, LINKS - 1)] @ p, t - 0.5
            placed.append(local @ here.lerp(other, share))
        shape[f] = placed
    NS.setdefault("cloth_rec", {})[(TIE, clip)] = shape
    sway = [(rec[f][LINKS] - rec[f][0]).dot(side[f]) for f in range(1, T + 1)]
    fore = [(rec[f][LINKS] - rec[f][0]).y for f in range(1, T + 1)]
    off = [(rec[f][k] - glued[f][k]).dot(wall[f][k]) for f in range(1, T + 1) for k in range(1, LINKS + 1)]
    fastest = max((rec[f + 1][k] - rec[f][k]).length for f in range(1, T + 1) for k in range(LINKS + 1))
    bowed = max((rec[f][0].lerp(rec[f][LINKS], along[k]) - rec[f][k]).length for f in range(1, T + 1) for k in range(1, LINKS))
    print(f"tie over the {clip}: tip against the knot sideways {min(sway):+.2f}..{max(sway):+.2f}, fore-aft {min(fore):+.2f}..{max(fore):+.2f} | "
          f"off the bib {min(off):.2f}..{max(off):.2f} | bows {bowed:.2f} off straight | cycle to cycle {settle[-4:]} | fastest link {fastest:.3f} a frame")


def cloth_begin(*pieces: str, clip="Walk", **over):
    """Sets the pieces up to be simulated together over the clip. Keyword arguments override their PIECES entries."""
    T = cycle(clip)
    record = 1 + T * over.pop("warm", WARM[clip])
    job = {"clip": clip, "T": T, "objs": [], "next": 1, "rec": {}, "starts": {}, "record": record, "last": record + T,
           "began": time.time(), "resizing": {}, "end": sc.frame_end, "action": arm.animation_data.action.name}
    for piece in pieces:
        cfg = {**PIECES[piece], **over}
        for name in cfg["objs"]:
            obj = bpy.data.objects[name]
            if obj.data.shape_keys:                          # simulate from the modelled shape, not a stored one
                obj.show_only_shape_key, obj.active_shape_key_index = True, 0
            cloth = next((m for m in obj.modifiers if m.type == "CLOTH"), None) or obj.modifiers.new(piece.title() + "Cloth", "CLOTH")
            skin = next((m for m in obj.modifiers if m.type == "ARMATURE"), None)
            if skin:
                move_modifier(obj, skin.name, 0)
                move_modifier(obj, cloth.name, 1)
            s, c = cloth.settings, cloth.collision_settings
            if "pin" in cfg:
                held = obj.vertex_groups.get(piece.title() + "Pin") or obj.vertex_groups.new(name=piece.title() + "Pin")
                fitted = obj.vertex_groups.get(piece.title() + "Fitted") or obj.vertex_groups.new(name=piece.title() + "Fitted")
                fitted.remove(list(range(len(obj.data.vertices))))
                for v in obj.data.vertices:
                    z = (obj.matrix_world @ v.co).z
                    held.add([v.index], smooth((z - cfg["pin"][0]) / (cfg["pin"][1] - cfg["pin"][0])), "REPLACE")
                    if z >= cfg["fitted"]:
                        fitted.add([v.index], 1.0, "REPLACE")
                s.vertex_group_mass, c.vertex_group_object_collisions = held.name, fitted.name
            for key, attributes in SETTINGS.items():
                for attribute in attributes if key in cfg else ():
                    setattr(s, attribute, cfg[key])
            if "grav" in cfg:
                s.effector_weights.gravity = cfg["grav"]
            c.use_collision = bool(cfg.get("colliders"))     # the straps hug the forearm closer than any margin: no collision
            if c.use_collision:
                c.use_self_collision, c.distance_min, c.collision_quality = False, 0.02, 4
            cloth.show_viewport = cloth.show_render = True
            cloth.point_cache.frame_start, cloth.point_cache.frame_end = 1, record + T
            job["objs"].append(name)
            job["rec"][name], job["starts"][name], job["resizing"][name] = {}, [], resizing_off(obj)
        for other, (margin, friction) in cfg.get("colliders", {}).items():
            solid = bpy.data.objects[other]
            if not any(m.type == "COLLISION" for m in solid.modifiers):
                solid.modifiers.new("ClothCollider", "COLLISION")
            solid.collision.use = True
            solid.collision.thickness_outer, solid.collision.cloth_friction, solid.collision.thickness_inner = margin, friction, 0.3
    sc.frame_end = record + T
    NS["cloth_job"] = job


def cloth_step(seconds: float = 25.0) -> bool:
    """Simulates for about this long. True once the kept cycle is recorded and the scene is put back."""
    job, pose, anim = NS["cloth_job"], arm.pose.bones, arm.animation_data
    clip, T, record, last = job["clip"], job["T"], job["record"], job["last"]
    bones = [fc for fc in curves(clip) if fc.data_path.startswith("pose.bones")]
    chans = {}
    for fc in bones:
        chans.setdefault((fc.data_path.split('"')[1], fc.data_path.rsplit(".", 1)[1]), {})[fc.array_index] = fc
    until = time.time() + seconds
    while job["next"] <= last and time.time() < until:
        f = job["next"]
        if f == 1:
            anim.action = None
        # The pose is written here, the clip repeating, with the action off. Cycle modifiers added to its curves
        # mid-run never reached the evaluated action: the skeleton froze after one pass and the cloth hung still.
        at, k = (f - 1) % T + 1, smooth((f - 10) / (PREROLL - 10))
        for (name, prop), d in chans.items():
            if prop == "location":
                pose[name].location = Vector([d[i].evaluate(at) if i in d else 0.0 for i in range(3)]) * k
            elif prop == "rotation_quaternion":
                q = Quaternion([d[i].evaluate(at) if i in d else float(i == 0) for i in range(4)]).normalized()
                pose[name].rotation_quaternion = Quaternion().slerp(q, k)
        sc.frame_set(f)
        if f >= record or f % T == 1:
            graph = bpy.context.evaluated_depsgraph_get()
            for name in job["objs"]:
                now = [v.co.copy() for v in bpy.data.objects[name].evaluated_get(graph).data.vertices]
                if f >= record:
                    job["rec"][name][f - record + 1] = now
                if f % T == 1 and f > PREROLL:
                    job["starts"][name].append(now)
        job["next"] = f + 1
    if job["next"] <= last:
        print(f"{clip} cloth at frame {job['next'] - 1} of {last}, {time.time() - job['began']:.0f} s in")
        return False

    sc.frame_end = job["end"]
    print(f"{clip} cloth done in {time.time() - job['began']:.0f} s")
    cloths = {name: next(m for m in bpy.data.objects[name].modifiers if m.type == "CLOTH") for name in job["objs"]}
    for cloth in cloths.values():
        cloth.show_viewport = cloth.show_render = False
    play(bpy.data.actions[clip])                             # cloth off, Basis only: what the skeleton alone does
    led = dict.fromkeys(cloths, 0.0)
    for f in (T // 4, T // 2, 3 * T // 4):
        sc.frame_set(f)
        graph = bpy.context.evaluated_depsgraph_get()
        for name, cloth in cloths.items():
            obj, pin = bpy.data.objects[name], bpy.data.objects[name].vertex_groups[cloth.settings.vertex_group_mass].index
            shown = obj.evaluated_get(graph).data.vertices
            fixed = [v.index for v in obj.data.vertices if any(g.group == pin and g.weight >= 1 for g in v.groups)]
            led[name] = max(led[name], max((shown[i].co - job["rec"][name][f][i]).length for i in fixed) * obj.matrix_world.median_scale)
    play(bpy.data.actions[job["action"]])
    for name in cloths:
        bpy.data.objects[name].show_only_shape_key = False
        resizing_back(bpy.data.objects[name], job["resizing"][name])
    for name, cloth in cloths.items():
        obj = bpy.data.objects[name]
        rec, verts, unit = job["rec"][name], obj.data.vertices, obj.matrix_world.median_scale
        assert len(rec) == T + 1 and len(rec[1]) == len(verts), (name, len(rec), len(rec[1]), len(verts))
        assert led[name] < 0.02, f"{name}: its held vertices are {led[name]:.3f} off the skeleton, so it was not simulated on this clip"
        held = obj.vertex_groups[cloth.settings.vertex_group_mass].index
        free = {v.index for v in verts if not any(g.group == held and g.weight > 0 for g in v.groups)}
        edges = [(a, b, (verts[a].co - verts[b].co).length) for a, b in (e.vertices for e in obj.data.edges) if a in free and b in free]
        ratio = sorted((rec[f][a] - rec[f][b]).length / length for f in range(1, T + 1, 6) for a, b, length in edges if length > 1e-5)
        seam = max((a - b).length for a, b in zip(rec[1], rec[T + 1])) * unit
        settle = [round(max((a - b).length for a, b in zip(x, y)) * unit, 3) for x, y in zip(job["starts"][name], job["starts"][name][1:])]
        mean = {i: sum((rec[f][i] for f in range(1, T + 1)), Vector()) / T for i in free}
        swing = max((rec[f][i] - mean[i]).length for f in range(1, T + 1) for i in free) * unit
        print(f"  {name}: free edges x{ratio[0]:.2f}..x{ratio[-1]:.2f} of rest (1% x{ratio[len(ratio) // 100]:.2f}, 99% x{ratio[-len(ratio) // 100]:.2f}) | "
              f"strays {swing:.2f} from its mean place | loop seam {seam:.3f}, cycle to cycle {settle}")
        NS.setdefault("cloth_rec", {})[(name, clip)] = rec
    sc.frame_set(1)
    return True


def stored_shapes(obj) -> dict:
    """The shapes the object's keys hold, by clip, each as a flat list of coordinates."""
    out = {}
    for key in obj.data.shape_keys.key_blocks[1:] if obj.data.shape_keys else ():
        flat = [0.0] * (3 * len(key.data))
        key.data.foreach_get("co", flat)
        out.setdefault(key.name.split(" ")[0], []).append(flat)
    return out


def write_keys(obj, stored: dict):
    """Rebuilds the object's keys as [Basis, each clip's shapes] and makes them follow the armature's cloth_time."""
    if obj.data.shape_keys:
        obj.shape_key_clear()
    obj.shape_key_add(name="Basis")                          # the modelled shape, which cloth_begin simulates from
    for clip in [c for c in CLIPS if c in stored]:
        for f, flat in zip(range(1, cycle(clip) + 2, CLIPS[clip]), stored[clip], strict=True):
            key = obj.shape_key_add(name=f"{clip} {f:03d}", from_mix=False)
            key.interpolation = "KEY_LINEAR"
            key.data.foreach_set("co", flat)
    keys = obj.data.shape_keys
    keys.use_relative = False                                # only now: an absolute key is filed at the current eval_time
    if TIME not in arm:
        arm[TIME] = 0.0
        arm.update_tag()                                     # or the evaluated armature lacks it and the driver fails for good
        bpy.context.view_layer.update()
    driver = keys.driver_add("eval_time").driver
    driver.type = "SUM"
    source = driver.variables.new()
    source.type = "SINGLE_PROP"
    source.targets[0].id, source.targets[0].data_path = arm, f'["{TIME}"]'


def clock_clips() -> dict:
    """Animates cloth_time in each clip's action over that clip's shapes, which every piece must store alike."""
    spans = {}
    for name in WORN:
        keys = bpy.data.objects[name].data.shape_keys
        for clip in CLIPS:
            at = [k.frame for k in keys.key_blocks if k.name.startswith(clip + " ")] if keys else []
            if at:
                assert spans.setdefault(clip, (at[0], at[-1])) == (at[0], at[-1]), (name, clip, at[0], at[-1], spans[clip])
    for clip, (first, last) in spans.items():
        found = curves(clip)
        curve = found.find(f'["{TIME}"]') or found.new(f'["{TIME}"]')
        curve.keyframe_points.clear()
        for frame, value in ((1, first), (cycle(clip) + 1, last)):
            curve.keyframe_points.insert(frame, value).interpolation = "LINEAR"
        if not curve.modifiers:
            curve.modifiers.new("CYCLES")
        curve.update()
        bpy.data.actions[clip].update_tag()                  # a modifier alone does not reach the evaluated action
    return spans


def cloth_bake(clip: str):
    """Stores everything recorded over the clip as shape keys in rest space (the skinning is undone per vertex)."""
    T, frames = cycle(clip), list(range(1, cycle(clip) + 2, CLIPS[clip]))
    skins = skins_at(clip, frames)
    done = [name for name, recorded in NS["cloth_rec"] if recorded == clip]
    for name in done:
        obj, rec = bpy.data.objects[name], NS["cloth_rec"][(name, clip)]
        gap = [a - b for a, b in zip(rec[1], rec[T + 1])]
        for f in range(T - 38, T + 2):                       # the last 40 frames ease onto frame 1
            rec[f] = [co + (f - (T - 39)) / 40 * gap[i] for i, co in enumerate(rec[f])]
        weights, to_world, to_obj = bone_weights(obj), obj.matrix_world, obj.matrix_world.inverted()
        shapes = []
        for f in frames:
            flat = []
            for i, w in enumerate(weights):
                co = rec[f][i]
                if w:                                        # no bone: the piece rides one, and its shape is already local
                    blend = Matrix(((0,) * 4,) * 4)
                    for bone, x in w:
                        blend += skins[f][bone] * x
                    co = (to_obj @ blend @ to_world).inverted() @ co
                flat.extend(co)
            shapes.append(flat)
        write_keys(obj, {**stored_shapes(obj), clip: shapes})
    spans = clock_clips()

    was, off, worst = play(bpy.data.actions[clip]), {name: resizing_off(bpy.data.objects[name]) for name in done}, dict.fromkeys(done, 0.0)
    for f in frames[::max(1, len(frames) // 6)]:             # replay against the recording, on stored frames
        sc.frame_set(f)
        graph = bpy.context.evaluated_depsgraph_get()
        for name in done:
            obj = bpy.data.objects[name]
            gap = max((v.co - NS["cloth_rec"][(name, clip)][f][i]).length for i, v in enumerate(obj.evaluated_get(graph).data.vertices))
            worst[name] = max(worst[name], gap * obj.matrix_world.median_scale)
    for name in done:
        resizing_back(bpy.data.objects[name], off[name])
    play(was)
    sc.frame_set(1)
    print(f"{clip} baked, {len(frames)} shapes each | {TIME} runs {spans} | replay strays from the recording by at most "
          f"{ {name: round(gap, 4) for name, gap in worst.items()} }")


def clip_sweep(clip: str, every: int = 3):
    """Counts apron points (vertices, face centres, edge midpoints) under the body's surface through the clip."""
    apron, was = bpy.data.objects["Cube.005"], play(bpy.data.actions[clip])
    bad, deepest, closest = [], 0.0, 9.0
    for f in range(1, cycle(clip) + 1, every):
        sc.frame_set(f)
        graph = bpy.context.evaluated_depsgraph_get()
        shown = body.evaluated_get(graph)
        mesh = shown.to_mesh()
        tree = BVHTree.FromPolygons([shown.matrix_world @ v.co for v in mesh.vertices], [p.vertices[:] for p in mesh.polygons])
        shown.to_mesh_clear()
        cloth = apron.evaluated_get(graph)
        M, me = cloth.matrix_world, cloth.data
        points = [M @ v.co for v in me.vertices] + [M @ p.center for p in me.polygons]
        points += [M @ ((me.vertices[a].co + me.vertices[b].co) / 2) for a, b in (e.vertices for e in me.edges)]
        inside = 0
        for at in points:
            near, normal, _, distance = tree.find_nearest(at)
            if (at - near).dot(normal) < -0.02:
                inside, deepest = inside + 1, max(deepest, distance)
            elif at.z < PIECES["apron"]["fitted"]:
                closest = min(closest, distance)
        if inside:
            bad.append((f, inside))
    play(was)
    sc.frame_set(1)
    print(f"{clip} clip sweep, every {every} frames: frames with apron points inside the body {bad} | deepest {deepest:.3f} | "
          f"nearest the free flap gets to the skin {closest:.3f}")


NS.update(spine_blend=spine_blend, tie_swing=tie_swing, cloth_begin=cloth_begin, cloth_step=cloth_step, cloth_bake=cloth_bake,
          clip_sweep=clip_sweep)
