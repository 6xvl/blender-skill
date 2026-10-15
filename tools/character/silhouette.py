"""Headless: the character alone, flat black on a transparent film, one clip.
blender -b file.blend --python silhouette.py -- <out dir> <clip> [frame,frame,...]   (saves nothing)"""
import bpy, os, sys
args = sys.argv[sys.argv.index("--") + 1:]
out, clip = args[0], args[1]
scn = bpy.context.scene
arm = bpy.data.objects["PumpkinRabbit_Rig"]
action = bpy.data.actions[clip]
arm.animation_data.action, arm.animation_data.action_slot = action, action.slots[0]
scn.frame_start, scn.frame_end = 1, int(action.frame_range[1]) - 1


def his(o):
    while o:
        if o == arm:
            return True
        o = o.parent
    return False


for o in scn.objects:                      # only him: no floor, no backdrop
    if o.type not in {"CAMERA", "LIGHT"} and not his(o):
        o.hide_render = True
black = bpy.data.materials.new("SilhouetteBlack")
black.use_nodes = True
nodes = black.node_tree.nodes
nodes.clear()
shader, output = nodes.new("ShaderNodeEmission"), nodes.new("ShaderNodeOutputMaterial")
shader.inputs["Color"].default_value = (0, 0, 0, 1)
black.node_tree.links.new(shader.outputs[0], output.inputs[0])
bpy.context.view_layer.material_override = black
r = scn.render
r.engine = "BLENDER_EEVEE"
scn.eevee.taa_render_samples = 16
r.film_transparent = True
r.resolution_x, r.resolution_y, r.resolution_percentage = 840, 1040, 100
r.use_border = r.use_compositing = r.use_sequencer = False
r.use_simplify, r.simplify_child_particles_render = True, 0.1
r.image_settings.file_format, r.image_settings.color_mode = "PNG", "RGBA"
frames = [int(f) for f in args[2].split(",")] if len(args) > 2 else range(scn.frame_start, scn.frame_end + 1)
for f in frames:
    scn.frame_set(f)
    r.filepath = os.path.join(out, "f%04d.png" % f)
    bpy.ops.render.render(write_still=True)
    print("FRAME", f, flush=True)
