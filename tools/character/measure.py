"""Measuring helpers for the arms and hands (exec into a dict): front-view leans and joint turns off rest."""
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

arm = bpy.data.objects["PumpkinRabbit_Rig"]
pose, sc, W = arm.pose.bones, bpy.context.scene, arm.matrix_world
SCALE = arm.scale.x
CENTRE_X = (W @ arm.data.bones["Root"].head_local).x
MIRROR = {"L": 1, "R": -1}   # he faces -Y, his left is +X


def rest3(name: str) -> Matrix:
    return arm.data.bones[name].matrix_local.to_3x3()


def local(name: str, body_rotation: Matrix) -> Quaternion:
    """A rotation given in the body's axes, as the bone's own quaternion."""
    basis = rest3(name)
    return (basis.inverted() @ body_rotation @ basis).to_quaternion()


def sided(base: str, side: str) -> str:
    head, dot, number = base.partition(".")
    return f"{head}.{side}{dot}{number}"


def head(name: str) -> Vector:
    return W @ pose[name].head


def tail(name: str) -> Vector:
    return W @ pose[name].tail


def lean(top: Vector, low: Vector, side: str) -> float:
    """Degrees a line leans out from straight down, away from the body's centre, seen from the front."""
    return math.degrees(math.atan2((low.x - top.x) * MIRROR[side], top.z - low.z))


def reading(side: str) -> dict:
    digits = {"thumb": ("Thumb", "Thumb.002"), "index": ("Index", "Index.002"), "middle": ("Middle", "Middle.001"), "pinky": ("Pinky", "Pinky.002")}
    out = {"lean": -lean(head(f"Lower Arm.{side}"), head(f"Hand.{side}"), side)}
    out.update({digit: lean(head(f"{base}.{side}"), tail(sided(tip, side)), side) for digit, (base, tip) in digits.items()})
    return out


def joint_turn(name: str) -> tuple:
    """How far a bone is bent and twisted off its rest, against its parent (degrees)."""
    parent = arm.data.bones[name].parent.name
    rest = rest3(parent).inverted() @ rest3(name)
    now = pose[parent].matrix.to_3x3().normalized().inverted() @ pose[name].matrix.to_3x3().normalized()
    bend, twist = (rest.inverted() @ now).to_quaternion().to_swing_twist("Y")
    return math.degrees(bend.angle), math.degrees(twist)
