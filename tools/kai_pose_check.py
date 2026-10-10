#!/usr/bin/env python3
"""Check that Kai's clothes stay clear of each other when the legs move.

    python3 tools/kai_pose_check.py [build dir, default kai]

Opens the built Kai.blend, poses the legs with plain bone rotations (the way game animation drives them, with the
posing rig's IK switched off) and counts triangles where one part cuts through the outside of another: shirt and
pants, sash and pants, shirt and calves. Only faces that can be seen are counted (the outer surface of each
garment, classified in the rest pose), so overlaps hidden inside clothing are ignored. Exits non-zero if anything
cuts through in the supported range of motion; poses beyond it are reported for information.
"""
import math, os, sys
import numpy as np
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kai_geometry as G

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
D = os.path.abspath(argv[0] if argv else "kai")
bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "Kai.blend"))
rig = bpy.data.objects["Armature"]
for pb in rig.pose.bones:
    for c in pb.constraints: c.influence = 0.0


def reset():
    for pb in rig.pose.bones: pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def turn_world(name, axis, deg):
    """Rotate a bone about a world axis through its head, on top of its current pose."""
    pb = rig.pose.bones[name]; h = pb.head.copy()
    pb.matrix = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, Vector(axis)) @ Matrix.Translation(-h) @ pb.matrix
    bpy.context.view_layer.update()


def leg(side, lift=0.0, knee=0.0, out=0.0):
    """lift: thigh forward (+) or back (-); knee: bend; out: step out sideways (degrees). Kai faces -Y."""
    s = 1.0 if side == "L" else -1.0
    if out: turn_world(G.bn("thigh", side), (0, 1, 0), -out * s)
    if lift: turn_world(G.bn("thigh", side), (1, 0, 0), -lift)
    if knee: turn_world(G.bn("calf", side), (1, 0, 0), knee)


# supported range of motion for platforming, and poses beyond it (reported only)
SUPPORTED = {
    "run stride": [("L", 55, 75, 0), ("R", -25, 35, 0)],
    "jump tuck": [("L", 50, 85, 0), ("R", 50, 85, 0)],
    "crouch landing": [("L", 75, 110, 8), ("R", 75, 110, 8)],
    "knee lift 70": [("L", 70, 90, 0)],
    "kick back 40": [("R", -40, 40, 0)],
    "step out 45": [("L", 0, 10, 45)],
}
BEYOND = {
    "knee lift 85": [("L", 85, 100, 0)],
    "climb pull-up 95": [("L", 95, 110, 0), ("R", 5, 15, 0)],
}

PAIRS = [("SK_Kai_Tunic", "SK_Kai_Pants"), ("SK_Kai_Sash", "SK_Kai_Pants"), ("SK_Kai_Tunic", "SK_Kai_Legs")]
reset()
OUTER = {}                                    # faces of each garment that can be seen, from its outer shape at rest
for name, fn in (("SK_Kai_Tunic", G.tunic_sdf), ("SK_Kai_Pants", G.pants_sdf)):
    ob = bpy.data.objects[name]
    cen = np.array([(ob.matrix_world @ p.center)[:] for p in ob.data.polygons])
    OUTER[name] = set(np.flatnonzero(fn(cen) > -0.15).tolist())


def tree(name):
    ob = bpy.data.objects[name]
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
    t = BVHTree.FromPolygons([ob.matrix_world @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    ev.to_mesh_clear()
    return t


def cuts(legs):
    reset()
    for side, lift, knee, out in legs: leg(side, lift, knee, out)
    trees = {n: tree(n) for n in {x for p in PAIRS for x in p}}
    out = {}
    for a, b in PAIRS:
        ov = trees[a].overlap(trees[b])
        if a in OUTER: ov = [(i, j) for i, j in ov if i in OUTER[a]]
        if b in OUTER: ov = [(i, j) for i, j in ov if j in OUTER[b]]
        out[f"{a[7:]}/{b[7:]}"] = len(ov)
    return out


bad = 0
for group, poses in (("supported", SUPPORTED), ("beyond the supported range", BEYOND)):
    print(f"-- {group}")
    for name, legs in poses.items():
        c = cuts(legs)
        n = sum(c.values())
        if group == "supported": bad += n
        print(f"{name:20s} " + "  ".join(f"{k} {v:4d}" for k, v in c.items()), flush=True)
reset()
print("POSE_CHECK_OK" if bad == 0 else f"POSE_CHECK_FAIL {bad}")
sys.exit(1 if bad else 0)
