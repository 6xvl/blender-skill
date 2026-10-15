"""Read-only, no frame change: the forearm and wrist skin as it is posed now, worked out by hand (linear blend on the
subdivided mesh), against the same skin with the hand's twist shared out to forearm twist bones that do not exist
yet. Prints how squeezed and stretched the skin's edges are in each case, and the worst edges as they are now."""
import math
import bpy
from mathutils import Matrix, Vector
arm, ob = bpy.data.objects["PumpkinRabbit_Rig"], bpy.data.objects["Cube.009"]
ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
me = ev.data
names = {g.index: g.name for g in ob.vertex_groups}
bones, pose = arm.data.bones, arm.pose.bones
skin = {n: pose[n].matrix @ bones[n].matrix_local.inverted() for n in names.values() if n in bones}
to_arm = arm.matrix_world.inverted() @ ev.matrix_world
ZERO = Matrix.Diagonal((0, 0, 0, 0))


def blend(w: dict, mats: dict) -> Matrix:
    total = sum(w.values())
    return sum((mats[n] * (x / total) for n, x in w.items()), ZERO.copy())


weights = [{names[g.group]: g.weight for g in v.groups if g.weight > 1e-4 and names.get(g.group) in skin} for v in me.vertices]
posed = [to_arm @ v.co for v in me.vertices]
rest = [blend(w, skin).inverted() @ p if w else p for w, p in zip(weights, posed)]
smooth = lambda x: (lambda t: t * t * (3 - 2 * t))(min(1.0, max(0.0, x)))
print("frame", bpy.context.scene.frame_current, "| subdivided verts", len(me.vertices))

for side in "RL":
    la, hand = f"Lower Arm.{side}", f"Hand.{side}"
    a, b = bones[la].head_local, bones[hand].head_local
    axis, length = (b - a).normalized(), (b - a).length
    rel = lambda mats: mats[0].to_3x3().normalized().inverted() @ mats[1].to_3x3().normalized()
    turn = (rel((bones[la].matrix_local, bones[hand].matrix_local)).inverted() @ rel((pose[la].matrix, pose[hand].matrix))).to_quaternion()
    swing, twist = turn.to_swing_twist("Y")
    s_of = {i: (rest[i] - b).dot(axis) / length for i, w in enumerate(weights) if any(side in n.split(".")[1:] for n in w)}
    region = {i for i, s in s_of.items() if -1.0 <= s <= 0.2 and not any(n.startswith(("Thumb", "Index", "Middle", "Ring", "Pinky")) for n in weights[i])}
    edges = [e.vertices[:] for e in me.edges if e.vertices[0] in region and e.vertices[1] in region]
    print(f"{side}: wrist bent {math.degrees(swing.angle):.0f}, twisted {math.degrees(twist):.0f} | skin verts {len(region)}, edges {len(edges)}")

    def case(label: str, shares: tuple, rings: tuple = (-0.96, -0.34, -0.15)):
        """shares: the part of the hand's twist each twist bone carries, elbow end first. The forearm's own weight
        moves onto them by height: all on the first by rings[1], all on the second by rings[2]."""
        mats = dict(skin)
        for k, share in enumerate(shares):
            mats[f"T{k}"] = pose[la].matrix @ Matrix.Rotation(share * twist, 4, "Y") @ bones[la].matrix_local.inverted()
        out = {}
        for i in region:
            w = dict(weights[i])
            own = w.pop(la, 0.0)
            if own and shares:
                t = smooth((s_of[i] - rings[0]) / (rings[1] - rings[0]))
                u = smooth((s_of[i] - rings[1]) / (rings[2] - rings[1])) if len(shares) > 1 else 0.0
                w[la] = own * (1 - t)
                w["T0"] = own * t * (1 - u)
                if len(shares) > 1:
                    w["T1"] = own * t * u
            elif own:
                w[la] = own
            out[i] = blend({n: x for n, x in w.items() if x > 0}, mats) @ rest[i]
        ratios = sorted(((out[i] - out[j]).length / max((rest[i] - rest[j]).length, 1e-9), i, j) for i, j in edges)
        n = len(ratios)
        print(f"   {label:34} shortest edge {ratios[0][0]:.2f} of rest | 2% under {ratios[n // 50][0]:.2f} | 2% over {ratios[-(n // 50) - 1][0]:.2f} | longest {ratios[-1][0]:.2f} | under 0.7: {sum(r[0] < 0.7 for r in ratios)} | over 1.4: {sum(r[0] > 1.4 for r in ratios)}")
        return ratios

    now = case("as it is", ())
    for r, i, j in now[:5]:
        print(f"        squeezed to {r:.2f} at s {s_of[i]:+.2f}/{s_of[j]:+.2f}: " + " | ".join(" ".join(f"{n} {x:.2f}" for n, x in sorted(weights[k].items(), key=lambda t: -t[1])[:3]) for k in (i, j)))
    for r, i, j in now[-3:]:
        print(f"        stretched to {r:.2f} at s {s_of[i]:+.2f}/{s_of[j]:+.2f}: " + " | ".join(" ".join(f"{n} {x:.2f}" for n, x in sorted(weights[k].items(), key=lambda t: -t[1])[:3]) for k in (i, j)))
    case("low only, 0.5 from -0.34", (0.5,), (-0.34, -0.15, 0))
    case("low only, 0.6 from -0.34", (0.6,), (-0.34, -0.15, 0))
    case("low only, 0.7 from -0.34", (0.7,), (-0.34, -0.15, 0))
    case("two: 0.4 and 0.8 (whole forearm)", (0.4, 0.8))
