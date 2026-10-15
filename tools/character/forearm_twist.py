"""Shares the hand's twist out along the lower forearm, so turning a hand no longer wrings the wrist.

The rig had no forearm twist bone: the whole turn of a hand (89 degrees in the Idle) landed on the two rings of
skin at the wrist, 0.2 long. This adds one bone on each forearm, a child of the lower arm and in line with it,
driven to carry 0.7 of the hand's twist, and gives it the lower arm's skin from the last ring before the wrist
down. The bend stays at the wrist. The skin above that ring's neighbour does not change, so the straps (pinned
higher up, parented to the lower arm) stay on the skin and keep their baked cloth.

Measured on the Idle's right wrist (89 degrees, subdivided skin, before -> after): most squeezed edge 0.35 -> 0.55
of its rest length, edges under 0.7: 26 -> 4, most stretched 2.12 -> 1.48. Left (74 degrees): 0.48 -> 0.61,
26 -> 7, 2.12 -> 1.43.

Exec inside the live Blender. Running it again changes nothing.
"""
import math

import bpy

SHARES = (0.7,)          # of the hand's twist, one per twist bone, elbow end first
RINGS = (-0.34, -0.15)   # the skin's rings along the forearm, from the wrist in forearm lengths: the lower arm
                         # owns the first alone, each twist bone the next one down and everything below it
NAME = "Lower Arm Twist"

arm = bpy.data.objects["PumpkinRabbit_Rig"]
bones = arm.data.bones


def twist_names(side: str) -> list:
    return [f"{NAME}.{side}" + (f".{k:03}" if k else "") for k in range(len(SHARES))]


def smooth(x: float) -> float:
    t = min(1.0, max(0.0, x))
    return t * t * (3 - 2 * t)


def twist_of(child: str, parent: str) -> float:
    """How far the child is twisted round its own length off its rest, against the parent (radians)."""
    rest = bones[parent].matrix_local.to_3x3().inverted() @ bones[child].matrix_local.to_3x3()
    now = arm.pose.bones[parent].matrix.to_3x3().normalized().inverted() @ arm.pose.bones[child].matrix.to_3x3().normalized()
    return (rest.inverted() @ now).to_quaternion().to_swing_twist("Y")[1]


# ---- bones -----------------------------------------------------------------------------------------
if any(name not in bones for side in "RL" for name in twist_names(side)):
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    with bpy.context.temp_override(window=window, area=area, region=next(r for r in area.regions if r.type == "WINDOW")):
        view = bpy.context.view_layer
        active, mode = view.objects.active, arm.mode
        view.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        for side in "RL":
            fore = arm.data.edit_bones[f"Lower Arm.{side}"]
            for k, name in enumerate(twist_names(side)):
                if name in arm.data.edit_bones:
                    continue
                bone = arm.data.edit_bones.new(name)
                bone.head = fore.head.lerp(fore.tail, (k + 1) / (len(SHARES) + 1))
                bone.tail = fore.head.lerp(fore.tail, (k + 2) / (len(SHARES) + 1))
                bone.roll, bone.parent, bone.use_connect, bone.use_deform = fore.roll, fore, False, True
                for collection in fore.collections:
                    collection.assign(bone)
        bpy.ops.object.mode_set(mode=mode)
        view.objects.active = active

# ---- drivers ---------------------------------------------------------------------------------------
for side in "RL":
    for name, share in zip(twist_names(side), SHARES):
        assert bones[name].matrix_local.to_3x3().col[0].angle(bones[f"Lower Arm.{side}"].matrix_local.to_3x3().col[0]) < 0.002, f"{name} does not lie as the lower arm does"
        pb = arm.pose.bones[name]
        pb.rotation_mode = "XYZ"
        path = pb.path_from_id("rotation_euler")
        arm.driver_remove(path, 1)
        driver = arm.driver_add(path, 1).driver
        driver.type = "SCRIPTED"
        var = driver.variables.new()
        var.name, var.type = "twist", "TRANSFORMS"
        target = var.targets[0]
        target.id, target.bone_target = arm, f"Hand.{side}"
        target.transform_type, target.rotation_mode, target.transform_space = "ROT_Y", "SWING_TWIST_Y", "LOCAL_SPACE"
        driver.expression = f"twist * {share}"

# ---- skin weights ----------------------------------------------------------------------------------
for ob in bpy.data.objects:
    if ob.type != "MESH" or not any(m.type == "ARMATURE" and m.object == arm for m in ob.modifiers):
        continue
    to_arm = arm.matrix_world.inverted() @ ob.matrix_world
    for side in "RL":
        levels = [f"Lower Arm.{side}"] + twist_names(side)
        if levels[0] not in ob.vertex_groups:
            continue
        wrist = bones[f"Hand.{side}"].head_local
        along = wrist - bones[levels[0]].head_local
        shared = 0
        for v in ob.data.vertices:
            mine = {g.index for g in ob.vertex_groups if g.name in levels}
            own = sum(g.weight for g in v.groups if g.group in mine)
            if own <= 0:
                continue
            s = ((to_arm @ v.co) - wrist).dot(along) / along.length_squared
            steps = [smooth((s - RINGS[k]) / (RINGS[k + 1] - RINGS[k])) for k in range(len(SHARES))] + [0.0]
            for name, part in zip(levels, [1 - steps[0]] + [steps[k] - steps[k + 1] for k in range(len(SHARES))]):
                group = ob.vertex_groups.get(name)
                if part * own > 1e-4:
                    (group or ob.vertex_groups.new(name=name)).add([v.index], part * own, "REPLACE")
                elif group:
                    group.remove([v.index])
            shared += steps[0] > 0
        if shared:
            most = max(sum(g.weight > 1e-4 for g in v.groups) for v in ob.data.vertices)
            print(f"FOREARM TWIST {ob.name} {side}: {shared} vertices ride the twist bone | most bones on one vertex {most}")
    ob.data.update()

# ---- check: the bones turn by their share of what the hand is twisted right now -----------------------
arm.update_tag()
bpy.context.view_layer.update()
for side in "RL":
    hand = twist_of(f"Hand.{side}", f"Lower Arm.{side}")
    got = [twist_of(name, f"Lower Arm.{side}") for name in twist_names(side)]
    print(f"FOREARM TWIST {side}: hand twisted {math.degrees(hand):+.1f}, twist bones " + ", ".join(f"{math.degrees(g):+.1f}" for g in got))
    assert all(abs(g - share * hand) < math.radians(1.5) for g, share in zip(got, SHARES)), "the twist bones do not carry their share"
