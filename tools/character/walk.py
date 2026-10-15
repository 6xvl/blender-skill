"""Rebuilds the looping Walk on the Pumpkin Rabbit, in place, after the reference clip
(J6qS5xSJa-VJvFDn.mp4). Run inside the open ANIM file:  exec(compile(open(p).read(), p, "exec"), {})

Timing is measured off the clip (120 frames, two steps, tracked head and feet) and played back in LOOP frames:
  a foot is down for about half the cycle and the other one lands as it leaves;
  it is picked UP at the back first (toes hanging, about 1.0 clear), swings through low, hovers
  in front and is set down at about 2 units a second;
  he is a robot, so the joints are hinges with modest ranges, taken from Bon's walk: the foot stays flat while it is
  down and only tips in the air, the knee stays inside Bon's range, and only the claws flex;
  the body is highest and furthest over the landing foot at each footfall, and sinks for 0.45 s after.
Weight and loose parts, after the heavy clip (wJngVLWHajO9WbG8.mp4: he falls onto each foot, the claws trail):
  the legs take the weight: he sinks deep and quickly after a footfall and hoists up slowly (HEAVY, EARLY, BOB);
  the torso and head do not shake; only the loose parts answer a footfall (jolt), late and slowly, each at its
  own pace: ears, arms, fingers, jaw;
  the hands drag behind the arm's swing at the wrist, the fingers curl and open a little behind the hands.
Afterwards bake the Walk's cloth again (cloth_pieces.py). Nothing here saves the file.
"""
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

T, STANCE = 120, 62            # the clip's clock, which all the timing below is written on: its cycle; frames a foot stays down
LOOP = 94                      # frames the cycle plays in here: faster than the clip (120), so the slow rise does not drag
STRIDE = 3.4                   # how far the ground carries a planted foot
CENTRE = -0.7                  # stride centre, from the rest foot (puts it under the hip)
WIDE = 0.08                    # feet this much wider than rest, each
DROP, BOB = 0.43, 0.17         # pelvis sits this low, and bobs this much either way
SHAKE = 1.0                    # how far the loose parts swing after a footfall (0 = none)
EARLY = 0.35                   # the low point comes this much sooner after a footfall: a short fall, a long slow rise
HEAVY = 0.3                    # 0 = an even bob; more = he drops faster after a footfall and stays down longer
TAU = 2 * math.pi

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
pose, bones, world, scene = arm.pose.bones, arm.data.bones, arm.matrix_world, bpy.context.scene
SCALE = arm.scale.x
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))  # he faces -Y, his left is +X


def rest3(name):
    return bones[name].matrix_local.to_3x3()


def spin(*spins):
    total = Matrix.Identity(3)
    for axis, degrees in spins:
        total = Matrix.Rotation(math.radians(degrees), 3, axis) @ total
    return total


def turn(name, *spins):
    """Rotations about the body's axes (X pitch forward +, Y lean to his left +, Z yaw) as the bone's quaternion."""
    basis = rest3(name)
    return (basis.inverted() @ spin(*spins) @ basis).to_quaternion()


def shift(name, offset):
    return rest3(name).inverted() @ (Vector(offset) / SCALE)


def track(knots):
    """Cubic Hermite through (frame, value, slope per frame or None = from the neighbours)."""
    t, v = [k[0] for k in knots], [k[1] for k in knots]
    m = [k[2] if k[2] is not None else (v[min(i + 1, len(v) - 1)] - v[max(i - 1, 0)]) / (t[min(i + 1, len(t) - 1)] - t[max(i - 1, 0)])
         for i, k in enumerate(knots)]

    def at(x):
        i = max(j for j in range(len(t) - 1) if t[j] <= x)
        h = t[i + 1] - t[i]
        s = (x - t[i]) / h
        return ((2 * s ** 3 - 3 * s ** 2 + 1) * v[i] + (s ** 3 - 2 * s ** 2 + s) * h * m[i]
                + (-2 * s ** 3 + 3 * s ** 2) * v[i + 1] + (s ** 3 - s ** 2) * h * m[i + 1])
    return at


SPEED = STRIDE / STANCE                                  # the ground, per frame
FRONT, BACK = CENTRE - STRIDE / 2, CENTRE + STRIDE / 2   # where the foot lands and where it leaves
HEEL, TIP = Vector((0, 0.48, -0.955)), Vector((0, -1.30, -0.955))   # the sole's two ends, from the ankle (measured on the mesh)
TOE_OUT = 8                                              # degrees the feet point out
# He is a robot, built like Bon: 91% of his skin rides ONE bone, and knee, ankle and elbow have no blended skin at all.
# So the joints are hinges. Bon's walk keeps the foot FLAT the whole time it is down and only tips it in the air; so does this.
PITCH = track([(0, 0, 0), (STANCE, 0, 0), (76, 16, None), (84, 20, 0), (96, 11, None), (106, 2, None), (112, 0, 0), (T, 0, 0)])  # + = toes down
REACH = track([(STANCE, BACK, SPEED), (68, BACK + 0.12, 0), (104, FRONT - 0.10, 0), (T, FRONT, 0.7 * SPEED)])
LIFT = track([(STANCE, 0, 0), (72, 0.45, None), (84, 0.9, 0), (94, 0.75, None), (104, 0.5, None), (112, 0.22, None), (T, 0, -0.02)])
# The three claws are the only soft part of the foot. They flare before he lands, tap down one after another, hang and curl in the air.
CLAW = track([(0, -14, 0), (4, -14, 0), (9, 0, 0), (64, 0, 0), (72, 6, None), (84, 8, 0), (98, 4, None), (110, -12, None), (T, -14, 0)])
CURL = track([(0, -6, 0), (6, -6, 0), (12, 0, 0), (64, 0, 0), (76, 8, 0), (98, 8, 0), (110, -6, 0), (T, -6, 0)])
SPLAY = track([(0, 9, 0), (12, 5, 0), (54, 5, 0), (66, -3, 0), (100, -3, 0), (114, 9, 0), (T, 9, 0)])
CLAWS = (("Out", 1, 0), ("Mid", 0, 2), ("In", -1, 4))    # name, which way it spreads, frames it runs behind


def up(p):
    """+1 at each footfall (a touch before it), -1 when he has sunk onto the standing leg."""
    since = TAU * (2 * p + 0.033)
    return math.cos(since + HEAVY * math.sin(since) + EARLY * (1 - math.cos(since)))


def jolt(p, late, swing):
    """What a footfall does to a LOOSE part (ears, hands, claws, jaw), `late` clip frames after it: one slow swing
    of `swing` frames and a small return. Big, loose things swing slowly, each at its own pace. The torso and head
    get none of this: any shake on them, slow or quick, read as a robot (the user, twice)."""
    t = ((2 * p) % 1.0) * T / 2 - late
    t += T / 2 if t < 0 else 0
    return SHAKE * math.exp(-t / (0.42 * swing)) * math.sin(TAU * t / swing)


# The fingers hang hooked, as the Idle holds them (read off its first frame), and curl about their own Z.
FINGERS = (("Index.{}.001", 0, 0), ("Index.{}.002", 0, 1), ("Middle.{}", 1, 0), ("Middle.{}.001", 1, 1), ("Pinky.{}.001", 2, 0), ("Pinky.{}.002", 2, 1))
idle = bpy.data.actions["Idle"].layers[0].strips[0].channelbag(bpy.data.actions["Idle"].slots[0]).fcurves
HANG = {name.format(side): Quaternion([idle.find(f'pose.bones["{name.format(side)}"].rotation_quaternion', index=i).evaluate(1) for i in range(4)])
        for name, _, _ in FINGERS for side in "LR"}


SIDES = (("L", 1, 0), ("R", -1, T // 2))


def leg(side, mirror, frame):
    """IK target, knee pole and claws for one leg, `frame` frames after its own footfall."""
    f = frame % T
    swing = math.sin(math.pi * (f - 66) / 46) ** 2 if 66 < f < 112 else 0.0   # a little room round the other thigh
    ankle = Vector((mirror * (WIDE + 0.12 * swing), FRONT + SPEED * f if f <= STANCE else REACH(f), LIFT(f) if f > STANCE else 0.0))
    turned = spin((X, PITCH(f)), (Z, mirror * TOE_OUT))
    name = f"IK Foot.{side}"
    out = {name: (shift(name, ankle), (rest3(name).inverted() @ turned @ rest3(name)).to_quaternion()),
           f"Pole Knee.{side}": (shift(f"Pole Knee.{side}", (mirror * (-0.35 + 0.1 * swing), 0, 0)), None)}
    for claw, spread, behind in CLAWS:
        g = (f - behind) % T
        out[f"Toe {claw}.{side}"] = (None, turn(f"Toe {claw}.{side}", (X, CLAW(g)), (Z, mirror * spread * SPLAY(g))))
        for part in ("001", "002"):
            out[f"Toe {claw}.{side}.{part}"] = (None, turn(f"Toe {claw}.{side}.{part}", (X, CURL(g))))
    return out


def body(p):
    c = lambda lag=0.0: math.cos(TAU * (p - lag))        # +1 as the LEFT foot lands
    low = DROP - BOB * up(p)
    out = {"Pelvis": (shift("Pelvis", (0.24 * c(0.02), 0, -low)), turn("Pelvis", (X, 9 - up(p)), (Y, 4 * c(0.07)), (Z, -8 * c()))),
           "Spine": (None, turn("Spine", (X, 8), (Y, 1.6 * c(0.03) - 3.0 * c(0.07)))),
           "Spine.001": (None, turn("Spine.001", (X, 6), (Z, 4 * c(0.03)))),
           "Chest": (None, turn("Chest", (X, 6 - 1.5 * up(p - 0.03)), (Y, 1.4 * c(0.05)), (Z, 7 * c(0.05)))),
           "Neck": (None, turn("Neck", (X, -7))),
           "Head": (None, turn("Head", (X, -10 + 1.0 * up(p - 0.06)), (Y, -1.5 * c(0.08)), (Z, -2.5 * c(0.08)))),
           "Jaw": (None, Quaternion((1, 0, 0), math.radians(3 * max(0.0, jolt(p, 3, 26)))))}   # +X drops the jaw: the teeth rattle
    for side, mirror, _ in SIDES:
        late = p - 0.05                                  # the arms hang off him and arrive a beat late
        ride = Vector((0.25 * math.cos(TAU * (late - 0.02)) + 0.1 * mirror, -0.7 + 0.45 * mirror * math.cos(TAU * (late - 0.01)),
                       0.2 - 0.9 * (DROP - BOB * up(late)) - 0.08 * jolt(p, 3, 28)))
        out[f"IK Hand.{side}"] = (shift(f"IK Hand.{side}", ride), None)
        out[f"Pole Elbow.{side}"] = (shift(f"Pole Elbow.{side}", (0.24 * c(0.02) + 1.0 * mirror, 2.0, -low)), None)
        out[f"Shoulder.{side}"] = (None, turn(f"Shoulder.{side}", (Y, -1.5 * mirror * up(p - 0.05))))
        out[f"Ear.{side}.001"] = (None, turn(f"Ear.{side}.001", (X, 4.5 * up(p - 0.08) + 2.5 * jolt(p, 4, 34)), (Y, 3 * c(0.10))))
        out[f"Ear.{side}.002"] = (None, turn(f"Ear.{side}.002", (X, 8 * up(p - 0.14) + 4.5 * jolt(p, 8, 34)), (Y, 4.5 * c(0.16))))
        for name, finger, joint in FINGERS:              # each finger a little behind the one before, the tip behind the knuckle
            more = 5 * math.sin(TAU * (late - 0.06 - 0.012 * finger - 0.02 * joint)) + 6 * jolt(p, 6 + finger + 2 * joint, 22)
            out[name.format(side)] = (None, Quaternion((0, 0, 1), math.radians(-mirror * more)) @ HANG[name.format(side)])
    return out


def clock(frame):
    """The clip's time at one of our frames."""
    return (frame - 1) * T / LOOP


def everything(frame):
    out = body(clock(frame) / T)
    for side, mirror, offset in SIDES:
        out.update(leg(side, mirror, clock(frame) + offset))
    return out


# ---- write the keys ------------------------------------------------------------------------
anim = arm.animation_data
walk = bpy.data.actions["Walk"]
anim.action, anim.action_slot = walk, walk.slots[0]
bag = walk.layers[0].strips[0].channelbag(anim.action_slot)
mine = set(everything(1))
for curve in [c for c in bag.fcurves if c.data_path.split('"')[1] in mine]:
    bag.fcurves.remove(curve)
for frame in range(1, LOOP + 2):
    for name, (location, rotation) in everything(frame).items():
        legwork = name.startswith(("IK Foot", "Pole Knee", "Toe"))
        if not legwork and frame % 2 == 0:               # legs every frame, the rest every other
            continue
        pb = pose[name]
        if location is not None:
            pb.location = location
            pb.keyframe_insert("location", frame=frame)
        if rotation is not None:
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = rotation
            pb.keyframe_insert("rotation_quaternion", frame=frame)
for frame in range(1, LOOP + 1, 2):                      # hands follow their forearms, dragging a little behind the arm's swing
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    for side in "LR":
        lower, target = pose[f"Lower Arm.{side}"], pose[f"IK Hand.{side}"]
        want = (lower.matrix @ lower.bone.matrix_local.inverted() @ bones[f"Hand.{side}"].matrix_local).to_3x3()
        p, mirror = clock(frame) / T, 1 if side == "L" else -1
        want = spin((X, 7 * mirror * math.sin(TAU * (p - 0.11)) + 4 * jolt(p, 5, 28))) @ want   # fingertips trail the way the arm came from
        target.rotation_quaternion = (rest3(target.name).inverted() @ want).to_quaternion()
        for at in ((frame, LOOP + 1) if frame == 1 else (frame,)):
            target.keyframe_insert("rotation_quaternion", frame=at)
for curve in [c for c in bag.fcurves if c.data_path.startswith("pose.bones")]:   # not cloth_time (cloth_pieces.py)
    name = curve.data_path.split('"')[1]
    for key in curve.keyframe_points:
        key.interpolation = "LINEAR" if name.startswith(("IK Foot", "Pole Knee", "Toe")) else "BEZIER"
        key.handle_left_type = key.handle_right_type = "AUTO_CLAMPED"
    curve.update()
scene.frame_start, scene.frame_end = 1, LOOP
clock_curve = bag.fcurves.find('["cloth_time"]')          # the cloth's clock ends with the cycle, whatever was baked on it
if clock_curve:
    clock_curve.keyframe_points[-1].co.x = LOOP + 1
    clock_curve.update()
    walk.update_tag()
if not idle.find('pose.bones["Jaw"].rotation_quaternion', index=0):   # the Idle holds the jaw shut, or the Walk's rattle would stay on it
    for i, value in enumerate((1.0, 0.0, 0.0, 0.0)):
        idle.new('pose.bones["Jaw"].rotation_quaternion', index=i).keyframe_points.insert(1, value)


# ---- checks ---------------------------------------------------------------------------------
def sample(frame):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    got = {pb.name: (world @ pb.matrix).translation.copy() for pb in pose}
    for side in "LR":
        foot = pose[f"Foot.{side}"]
        for tag, edge in (("heel.", HEEL), ("tip.", TIP)):   # the sole's ends, riding the posed foot bone
            at_rest = world.inverted() @ (world @ foot.bone.head_local + Vector((edge.x, edge.y, edge.z)))
            got[tag + side] = world @ (foot.matrix @ (foot.bone.matrix_local.inverted() @ at_rest))
        got["claw." + side] = min((world @ pose[f"Toe {c}.{side}.002"].tail).z - (world @ bones[f"Toe {c}.{side}.002"].tail_local).z for c, _, _ in CLAWS)
        got["shin." + side] = math.degrees(math.atan2(-pose[f"LowerLeg.{side}"].matrix.col[1].y, -pose[f"LowerLeg.{side}"].matrix.col[1].z))
        got["knee." + side] = math.degrees((pose[f"UpperLeg.{side}"].matrix.col[1].xyz).angle(pose[f"LowerLeg.{side}"].matrix.col[1].xyz))
    return got


shots = {f: sample(f) for f in range(1, LOOP + 2)}
ground = (world @ bones["Foot.L"].head_local).z + HEEL.z
print(f"WALK {LOOP} frames a cycle, ground {SPEED * T / LOOP * scene.render.fps:.2f} a second | seam {max((shots[1][n] - shots[LOOP + 1][n]).length for n in pose.keys()):.5f}"
      f" | feet off their targets {max((shots[f]['Foot.' + s] - shots[f]['IK Foot.' + s]).length for f in shots for s in 'LR'):.4f}"
      f" | hands off theirs {max((shots[f]['Hand.' + s] - shots[f]['IK Hand.' + s]).length for f in shots for s in 'LR'):.4f}")
for side, mirror, offset in SIDES:
    since = lambda f: (clock(f) + offset) % T              # the clip's time since this foot landed
    slips = [((shots[f + 1][tag + side] - shots[f][tag + side]) - Vector((0, SPEED * T / LOOP, 0))).length
             for f in range(1, LOOP + 1) for tag in ("heel.", "tip.") if since(f + 1) < STANCE and since(f) < since(f + 1)]
    low = {f: min(shots[f]["heel." + side].z, shots[f]["tip." + side].z) - ground for f in range(1, LOOP + 1)}
    clear = {t: round(low[round((t - offset) % T * LOOP / T) % LOOP + 1], 2) for t in (76, 88, 96, 104, 112)}
    knees = [shots[f]["knee." + side] for f in range(1, LOOP + 1)]
    shins = [shots[f]["shin." + side] for f in range(1, LOOP + 1)]
    print(f"WALK {side}: planted sole slips {max(slips):.4f} a frame | sole never lower than {min(low.values()):+.3f}, claws {min(shots[f]['claw.' + side] for f in range(1, LOOP + 1)):+.3f}"
          f" | clears {clear} (the clip lifts higher: 1.0, 0.9, 0.5, 0.5, 0.2) | knee bend {min(knees):.0f} to {max(knees):.0f} deg (Bon 26 to 70-85) | shin never further back than {min(shins):.0f} deg (Bon -37 to -46)")
apart = [shots[f]["LowerLeg.L"].x - shots[f]["LowerLeg.R"].x for f in shots]
heads = [shots[f]["Head"] for f in range(1, LOOP + 1)]
print(f"WALK knees {min(apart):.2f} to {max(apart):.2f} apart (rest 2.04) | head bobs {max(h.z for h in heads) - min(h.z for h in heads):.2f} (clip 0.22-0.34)"
      f", sways {max(h.x for h in heads) - min(h.x for h in heads):.2f} (clip 0.72)")
lean = [math.degrees(math.atan2(-(shots[f]["Neck"] - shots[f]["Pelvis"]).y, (shots[f]["Neck"] - shots[f]["Pelvis"]).z)) for f in range(1, LOOP + 1)]
print(f"WALK torso leans forward {min(lean):.1f} to {max(lean):.1f} deg (was 14.2 to 17.2)")
scene.frame_set(1)
