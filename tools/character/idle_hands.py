"""Turns the Idle's hands at the wrist the way the user did it in the viewport: only the IK hand boxes rotate.
The arms stay where they are, so the straps' cloth does not need baking again.

The right hand is the user's own pose (2026-10-13, frame 1): the box turned 73 degrees about an axis close to
straight up, so the hooked fingers show from the side as in the concept drawing. The left hand gets a share of
the same turn, mirrored: the drawing shows that hand less turned, its fingers still fanned.

A turn goes on top of every key the box has, so the sway and the drift stay. The turn applied is remembered on
the action, and running this again with other numbers replaces it. Exec inside the live Blender.
"""
import math

import bpy
from mathutils import Matrix, Quaternion

# The right hand box as the user left it at frame 1, and where the Idle had it there.
POSED = Quaternion((0.1281297206878662, 0.004417210817337036, -0.9800258278846741, 0.15202867984771729))
HAD = Quaternion((0.6641989946365356, 0.15865573287010193, -0.7301703691482544, 0.022789284586906433))
LEFT_SHARE = 0.75    # of the right hand's turn
LEFT_ROLL = -10      # degrees on top, in the plane the drawing shows: fans the fingers outward

arm = bpy.data.objects["PumpkinRabbit_Rig"]
FLIP = Matrix.Diagonal((-1, 1, 1))   # his left is +X


def rest3(name: str) -> Matrix:
    return arm.data.bones[name].matrix_local.to_3x3()


def mirrored(turn: Quaternion) -> Quaternion:
    """The right box's turn as the left box's own quaternion, mirrored across the body."""
    right, left = rest3("IK Hand.R"), rest3("IK Hand.L")
    return (left.inverted() @ FLIP @ right @ turn.to_matrix() @ right.inverted() @ FLIP @ left).to_quaternion()


right = POSED @ HAD.inverted()
roll = (rest3("IK Hand.L").inverted() @ Matrix.Rotation(math.radians(LEFT_ROLL), 3, "Y") @ rest3("IK Hand.L")).to_quaternion()
TURNS = {"R": right, "L": roll @ Quaternion().slerp(mirrored(right), LEFT_SHARE)}

idle = bpy.data.actions["Idle"]
curves = idle.layers[0].strips[0].channelbag(idle.slots[0]).fcurves
for side, turn in TURNS.items():
    name, mark = f"IK Hand.{side}", f"hand_turn_{side}"
    step = turn @ Quaternion(idle.get(mark, (1, 0, 0, 0))).inverted()
    four = [curves.find(f'pose.bones["{name}"].rotation_quaternion', index=i) for i in range(4)]
    for keys in zip(*(curve.keyframe_points for curve in four)):
        for key, value in zip(keys, step @ Quaternion([key.co.y for key in keys])):
            key.co.y = value
    for curve in four:
        curve.update()
    idle[mark] = list(turn)
idle.update_tag()
bpy.context.scene.frame_set(bpy.context.scene.frame_current)

at_one = Quaternion([curves.find('pose.bones["IK Hand.R"].rotation_quaternion', index=i).evaluate(1) for i in range(4)])
assert (at_one - POSED).magnitude < 1e-3, f"the right hand is not where the user posed it: {at_one}"
print("IDLE HANDS turned: right as posed, left", LEFT_SHARE, "of it mirrored, rolled", LEFT_ROLL)
