import bpy, os, shutil
path = os.environ["BLEND_PATH"]  # set to the .blend you are saving, e.g. <project>\PumpkinRabbit_ANIM.blend
assert bpy.data.filepath == path, bpy.data.filepath
sc = bpy.context.scene
arm = bpy.data.objects["PumpkinRabbit_Rig"]
playing = arm.animation_data.action
assert playing.name in ("Walk", "Idle") and (sc.frame_start, sc.frame_end) == (1, int(playing.frame_range[1]) - 1) and sc.camera.name == "BonPreviewCam"
for clip in ("Walk", "Idle"):
    a = bpy.data.actions[clip]
    for fc in a.layers[0].strips[0].channelbag(a.slots[0]).fcurves:
        assert [m.type for m in fc.modifiers] == (["CYCLES"] if fc.data_path == '["cloth_time"]' else []), (clip, fc.data_path)
worn = ("Cube.005", "Cube.018", "Plane.005", "Plane.006", "Plane.009", "Plane.010")
for n in worn:
    o = bpy.data.objects[n]
    k = o.data.shape_keys
    assert not o.show_only_shape_key and not any(m.type == "CLOTH" and (m.show_viewport or m.show_render) for m in o.modifiers), n
    assert len(k.key_blocks) == 1 + sum((int(bpy.data.actions[c].frame_range[1]) - 1) // step + 1 for c, step in (('Walk', 2), ('Idle', 5))) and not k.use_relative and k.animation_data.drivers[0].driver.is_valid, (n, len(k.key_blocks))
sc.frame_set(1)
size = os.path.getsize(path)
free = shutil.disk_usage("E:\\").free
assert free + size > size * 1.05, (free, size)
os.remove(path)
bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False)
print("saved, opens on", playing.name, "|", os.path.getsize(path) // 2**20, "MB | E: free", shutil.disk_usage("E:\\").free // 2**20, "MB | dirty", bpy.data.is_dirty)
