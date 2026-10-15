"""Headless preview frames of one clip: blender -b file.blend --python render.py -- <out dir> <clip> [frame,frame,...]"""
import bpy, os, sys
args = sys.argv[sys.argv.index("--") + 1:]
out, clip = args[0], args[1]
scn = bpy.context.scene
arm = bpy.data.objects["PumpkinRabbit_Rig"]
action = bpy.data.actions[clip]
arm.animation_data.action, arm.animation_data.action_slot = action, action.slots[0]
scn.frame_start, scn.frame_end = 1, int(action.frame_range[1]) - 1
assert scn.camera.name == "BonPreviewCam"
r = scn.render
r.engine = "BLENDER_EEVEE"
scn.eevee.taa_render_samples = 64
r.resolution_x, r.resolution_y, r.resolution_percentage = 840, 1040, 100
r.use_border = r.use_compositing = r.use_sequencer = False
r.use_simplify, r.simplify_child_particles_render = True, 0.1
r.motion_blur_shutter = 0.22
r.image_settings.file_format = "PNG"
frames = [int(f) for f in args[2].split(",")] if len(args) > 2 else range(scn.frame_start, scn.frame_end + 1)
for f in frames:
    scn.frame_set(f)
    r.filepath = os.path.join(out, "f%04d.png" % f)
    bpy.ops.render.render(write_still=True)
    print("FRAME", f, flush=True)
print("DONE", clip, scn.frame_start, scn.frame_end)
