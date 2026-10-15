"""Read-only rig audit, rest pose: left/right bone pairs out of mirror, joints whose pivot is off the centre of the
skin they bend, hinge chains whose bend axes disagree, deform bones nothing rides, groups with no bone."""
import math
import bpy
from mathutils import Vector
arm = bpy.data.objects["PumpkinRabbit_Rig"]
bones = arm.data.bones
S = lambda v: Vector((-v.x, v.y, v.z))
deg = lambda a: round(math.degrees(a), 1)
print("bones", len(bones), "| deform", sum(b.use_deform for b in bones), "| centre x of Root", round(bones["Root"].head_local.x, 4))
print("TREE:", "; ".join(f"{b.name}<{b.parent.name if b.parent else '-'}{'' if b.use_deform else ' (ctl)'}" for b in bones))

# ---- left / right mirror ---------------------------------------------------------------------------
def other(name):
    for a, b in ((".L", ".R"),):
        if name.endswith(a) or (a + ".") in name:
            return name.replace(a, b, 1) if name.endswith(a) else name.replace(a + ".", b + ".", 1)
print("MIRROR (left bone against its right twin; position in rig units x", round(arm.scale.x, 2), ")")
for b in bones:
    twin = other(b.name)
    if twin is None:
        continue
    if twin not in bones:
        print("   no right twin for", b.name)
        continue
    r = bones[twin]
    dh, dt = (S(b.head_local) - r.head_local).length * arm.scale.x, (S(b.tail_local) - r.tail_local).length * arm.scale.x
    xl, xr = S(b.matrix_local.to_3x3().col[0]), r.matrix_local.to_3x3().col[0]
    roll = math.acos(min(1.0, abs(xl.dot(xr))))
    if dh > 0.01 or dt > 0.01 or roll > math.radians(1):
        print(f"   {b.name:22} head off {dh:.3f}  tail off {dt:.3f}  roll off {deg(roll)}")
for b in bones:
    if (b.name.endswith(".R") or ".R." in b.name) and b.name.replace(".R", ".L", 1) not in bones:
        print("   no left twin for", b.name)

# ---- skin: who rides what --------------------------------------------------------------------------
verts = []        # (position in rig space, {bone: weight})
edges = []
orphans, bare = {}, {}
for ob in bpy.data.objects:
    if ob.type != "MESH" or not any(m.type == "ARMATURE" and m.object == arm for m in ob.modifiers):
        continue
    to_arm = arm.matrix_world.inverted() @ ob.matrix_world
    names = {g.index: g.name for g in ob.vertex_groups}
    base = len(verts)
    for v in ob.data.vertices:
        w = {names[g.group]: g.weight for g in v.groups if g.weight > 1e-3}
        for n in w:
            if n not in bones:
                orphans.setdefault(ob.name, set()).add(n)
        w = {n: x for n, x in w.items() if n in bones}
        if not w:
            bare[ob.name] = bare.get(ob.name, 0) + 1
        total = sum(w.values()) or 1
        verts.append((to_arm @ v.co, {n: x / total for n, x in w.items()}))
    edges += [(base + e.vertices[0], base + e.vertices[1]) for e in ob.data.edges]
used = {n for _, w in verts for n in w}
print("DEFORM BONES NOTHING RIDES:", sorted(b.name for b in bones if b.use_deform and b.name not in used) or "none")
print("SKINNED TO A NON-DEFORM BONE:", sorted(n for n in used if not bones[n].use_deform) or "none")
print("GROUPS WITH WEIGHT BUT NO BONE:", {k: sorted(v)[:6] for k, v in orphans.items()} or "none", "| VERTS ON NO BONE:", bare or "none")

# ---- joints: is the pivot in the middle of the skin that bends there? -------------------------------
def lead(i):
    w = verts[i][1]
    return max(w, key=w.get) if w else None
print("JOINTS (pivot against the centre of the seam between a bone's skin and its parent's; off = distance / seam radius)")
rows = []
for b in bones:
    p = b.parent
    if not (b.use_deform and p and b.name in used):
        continue
    while p and (not p.use_deform or p.name not in used):
        p = p.parent
    if not p:
        continue
    seam = [verts[i][0] for i in range(len(verts)) if verts[i][1].get(b.name, 0) > 0.15 and verts[i][1].get(p.name, 0) > 0.15]
    kind = "blend"
    if len(seam) < 3:
        seam = [(verts[i][0] + verts[j][0]) / 2 for i, j in edges if {lead(i), lead(j)} == {b.name, p.name}]
        kind = "hard"
    if len(seam) < 3:
        rows.append((9.0, f"   {b.name:22} < {p.name:18} no shared skin seam ({len(seam)} points)"))
        continue
    c = sum(seam, Vector()) / len(seam)
    radius = sum((q - c).length for q in seam) / len(seam)
    off = b.head_local - c
    axis = (b.tail_local - b.head_local).normalized()
    along, across = off.dot(axis), (off - axis * off.dot(axis)).length
    rows.append((off.length / max(radius, 1e-6), f"   {b.name:22} < {p.name:18} {kind:5} seam {len(seam):3} pts  radius {radius * arm.scale.x:.2f}  pivot off {off.length / max(radius, 1e-6):.2f} (along the bone {along * arm.scale.x:+.2f}, across {across * arm.scale.x:.2f})"))
for _, line in sorted(rows, reverse=True):
    print(line)

# ---- hinge chains: do a bone and its child bend about the same axis? --------------------------------
print("BEND AXES (angle between a bone's own X axis and its child's, same chain; a clean hinge chain reads near 0)")
for b in bones:
    kids = [c for c in b.children if c.use_deform and b.use_deform]
    for c in kids:
        a = b.matrix_local.to_3x3().col[0].angle(c.matrix_local.to_3x3().col[0])
        gap = (c.head_local - b.tail_local).length * arm.scale.x
        if a > math.radians(8) or gap > 0.02:
            print(f"   {b.name:22} > {c.name:22} x axes {deg(a):5} apart | child starts {gap:.2f} from the parent's tip{' (connected)' if c.use_connect else ''}")
print("ROTATION MODES:", {m: sum(pb.rotation_mode == m for pb in arm.pose.bones) for m in {pb.rotation_mode for pb in arm.pose.bones}})
print("CONSTRAINTS:", "; ".join(f"{pb.name}: " + ",".join(f"{c.type}>{getattr(c, 'subtarget', '')}" for c in pb.constraints) for pb in arm.pose.bones if pb.constraints))
