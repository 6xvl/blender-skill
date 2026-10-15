"""Read-only, no frame change: which bones the user has posed away from the Idle's curves at the current frame,
and whether any key in the Idle differs from the copy taken before the hands work."""
import bpy
arm, sc = bpy.data.objects["PumpkinRabbit_Rig"], bpy.context.scene
anim = arm.animation_data
a, f = anim.action, sc.frame_current + sc.frame_subframe
bag = lambda act: act.layers[0].strips[0].channelbag(act.slots[0]).fcurves
print("frame", f, "| action", a.name, "| auto key", sc.tool_settings.use_keyframe_insert_auto, "| mode", bpy.context.mode,
      "| active bone", arm.data.bones.active.name if arm.data.bones.active else None, "| selected", [pb.name for pb in (bpy.context.selected_pose_bones or [])][:8])
REST = {"location": (0, 0, 0), "rotation_quaternion": (1, 0, 0, 0), "rotation_euler": (0, 0, 0), "scale": (1, 1, 1)}
for pb in arm.pose.bones:
    for prop, rest in REST.items():
        now = list(getattr(pb, prop))
        fcs = [bag(a).find(f'pose.bones["{pb.name}"].{prop}', index=i) for i in range(len(rest))]
        want = [fc.evaluate(f) if fc else r for fc, r in zip(fcs, rest)]
        if max(abs(n - w) for n, w in zip(now, want)) > 1e-4:
            print(f"POSED {pb.name}.{prop} ({pb.rotation_mode}, keyed {sum(fc is not None for fc in fcs)}/{len(rest)}): curve {[round(w, 4) for w in want]} -> now {[round(n, 4) for n in now]}")
old = bpy.data.actions.get("Idle_before_hands")
if old:
    changed = {}
    for src in bag(old):
        dst = bag(a).find(src.data_path, index=src.array_index)
        if dst is None or len(dst.keyframe_points) != len(src.keyframe_points) or any(abs(p.co.y - q.co.y) > 1e-5 or abs(p.co.x - q.co.x) > 1e-5 for p, q in zip(dst.keyframe_points, src.keyframe_points)):
            changed[src.data_path] = changed.get(src.data_path, 0) + 1
    print("curves in", a.name, "that differ from Idle_before_hands:", changed, "| curve counts", len(bag(a)), len(bag(old)))
