#!/usr/bin/env python3
"""Check the Pebble Chick clips for Unreal: loop seams, clip-to-clip pose matches, planted-foot
slip, and a clean FBX round trip (armature node name, bones, frame counts, poses).

    python3 tools/verify_chick_anims.py pebble/Pebble_Chick
Writes anim_validation.json next to the clips and prints a summary.
"""
import json, os, sys
import bpy
import numpy as np
from io_scene_fbx import parse_fbx

D = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else sys.argv[1]
CLIPS = ["Chick_Idle", "Chick_Waddle", "Chick_Waddle_RootMotion", "Chick_Jump_Start", "Chick_Jump_Loop",
         "Chick_Jump_Land", "Chick_BellySlide_Start", "Chick_BellySlide_Loop", "Chick_BellySlide_End"]
LOOPS = ["Chick_Idle", "Chick_Waddle", "Chick_Jump_Loop", "Chick_BellySlide_Loop"]


def use(rig, act):
    rig.animation_data.action = act
    if hasattr(act, "slots") and act.slots:
        rig.animation_data.action_slot = act.slots[0]


def pose(rig, f, skip_root=False):
    bpy.context.scene.frame_set(f)
    out = {}
    for p in rig.pose.bones:
        M = np.array(rig.matrix_world @ p.matrix)
        if skip_root:
            R = np.array(rig.matrix_world @ rig.pose.bones["root"].matrix)
            M = np.linalg.inv(R) @ M
        out[p.name] = M
    return out


def diff(a, b):
    t = max(np.linalg.norm(a[k][:3, 3] - b[k][:3, 3]) for k in a)
    r = max(np.abs(a[k][:3, :3] - b[k][:3, :3]).max() for k in a)
    return round(float(t), 4), round(float(r), 5)


rep = {"source": {}, "fbx": {}}
bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "Pebble_Chick_Anims.blend"))
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
A = {a.name: a for a in bpy.data.actions}
n = {k: int(round(A[k].frame_range[1])) for k in CLIPS}
# rest pose
rig.animation_data.action = None
for p in rig.pose.bones:
    p.location = (0, 0, 0); p.rotation_quaternion = (1, 0, 0, 0); p.scale = (1, 1, 1)
bpy.context.view_layer.update()
REST = {p.name: np.array(rig.matrix_world @ p.matrix) for p in rig.pose.bones}
first, last = {}, {}
for k in CLIPS:
    use(rig, A[k]); first[k] = pose(rig, 1); last[k] = pose(rig, n[k])
seams = {k: diff(first[k], last[k]) for k in LOOPS}
use(rig, A["Chick_Waddle_RootMotion"])
rm_first, rm_last = pose(rig, 1, True), pose(rig, n["Chick_Waddle_RootMotion"], True)
seams["Chick_Waddle_RootMotion (relative to root)"] = diff(rm_first, rm_last)
chain = {
    "Idle first == rest": diff(first["Chick_Idle"], REST),
    "Jump_Start first == rest": diff(first["Chick_Jump_Start"], REST),
    "Jump_Start last == Jump_Loop first": diff(last["Chick_Jump_Start"], first["Chick_Jump_Loop"]),
    "Jump_Land first == Jump_Loop first": diff(first["Chick_Jump_Land"], first["Chick_Jump_Loop"]),
    "Jump_Land last == rest": diff(last["Chick_Jump_Land"], REST),
    "BellySlide_Start first == rest": diff(first["Chick_BellySlide_Start"], REST),
    "BellySlide_Start last == BellySlide_Loop first": diff(last["Chick_BellySlide_Start"], first["Chick_BellySlide_Loop"]),
    "BellySlide_End first == BellySlide_Loop first": diff(first["Chick_BellySlide_End"], first["Chick_BellySlide_Loop"]),
    "BellySlide_End last == rest": diff(last["Chick_BellySlide_End"], REST),
}
rep["source"]["loop_seams_cm_and_matrix"] = seams
rep["source"]["chain_matches_cm_and_matrix"] = chain

# planted-foot slip with root motion: each planted foot must stay fixed in the world
use(rig, A["Chick_Waddle_RootMotion"])
slip = {}
for L in "LR":
    P, Rm = [], []
    for f in range(1, n["Chick_Waddle_RootMotion"] + 1):
        bpy.context.scene.frame_set(f)
        m = rig.matrix_world @ rig.pose.bones["foot." + L].matrix
        P.append(np.array(m.translation)); Rm.append(np.array(m.to_3x3()))
    P = np.array(P)
    z = P[:, 2]; planted = np.where(z < z.min() + 0.01)[0]
    runs, cur = [], [planted[0]]
    for i in planted[1:]:
        if i == cur[-1] + 1: cur.append(i)
        else: runs.append(cur); cur = [i]
    runs.append(cur)
    seg = np.array(max(runs, key=len))          # longest continuous planted stretch
    rot = max(np.abs(Rm[i] - Rm[seg[0]]).max() for i in seg)
    slip[L] = dict(planted_frames=f"{seg[0] + 1}-{seg[-1] + 1}",
                   x=round(float(np.ptp(P[seg, 0])), 3), y=round(float(np.ptp(P[seg, 1])), 3),
                   z=round(float(np.ptp(P[seg, 2])), 3), rotation=round(float(rot), 5))
rep["source"]["waddle_planted_foot_slip_cm"] = slip
root_travel = float(np.linalg.norm(np.array((rig.matrix_world @ rig.pose.bones["root"].matrix).translation)))
rep["source"]["waddle_root_motion_cm_per_cycle"] = round(root_travel, 2)

# FBX round trip
for k in CLIPS:
    path = os.path.join(D, f"AN_Pebble_{k}.fbx")
    root, ver = parse_fbx.parse(path)
    objs = next(e for e in root.elems if e.id == b"Objects")
    models = [(e.props[1].decode(errors="ignore").split("\x00")[0], e.props[2].decode()) for e in objs.elems if e.id == b"Model"]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene; sc.unit_settings.system = "METRIC"; sc.unit_settings.scale_length = .01; sc.render.fps = 30
    bpy.ops.import_scene.fbx(filepath=path, use_anim=True, anim_offset=0, ignore_leaf_bones=False,
                             automatic_bone_orientation=False, force_connect_children=False)
    arms = [o for o in sc.objects if o.type == "ARMATURE"]; meshes = [o for o in sc.objects if o.type == "MESH"]
    ar = arms[0]
    bpy.context.view_layer.objects.active = ar
    bpy.ops.object.mode_set(mode="EDIT")
    for b in ar.data.edit_bones: b.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    frames = [tuple(a.frame_range) for a in bpy.data.actions]
    rep["fbx"][k] = dict(fbx_version=ver, armature_node=[m for m in models if m[1] == "Null"],
                         bones=len(ar.data.bones), meshes=len(meshes), frames=frames,
                         bone_names=sorted(b.name for b in ar.data.bones))
    # compare a few reimported poses with the source (bone heads, cm)
    rep["fbx"][k]["_heads"] = {}
    for f in sorted({1, max(1, n[k] // 2), n[k]}):
        sc.frame_set(f)
        rep["fbx"][k]["_heads"][f] = {p.name: list(ar.matrix_world @ p.head) for p in ar.pose.bones}

bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "Pebble_Chick_Anims.blend"))
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
A = {a.name: a for a in bpy.data.actions}
for k in CLIPS:
    use(rig, A[k]); worst = 0.0
    for f, heads in rep["fbx"][k].pop("_heads").items():
        bpy.context.scene.frame_set(int(f))
        for name, h in heads.items():
            worst = max(worst, float(np.linalg.norm(np.array(rig.matrix_world @ rig.pose.bones[name].head) - np.array(h))))
    rep["fbx"][k]["max_bone_head_error_cm"] = round(worst, 4)
names = {tuple(v["bone_names"]) for v in rep["fbx"].values()}
for v in rep["fbx"].values(): v.pop("bone_names")
rep["fbx_bone_names_identical_across_clips"] = len(names) == 1
rep["bone_names"] = list(names)[0] if len(names) == 1 else None
json.dump(rep, open(os.path.join(D, "anim_validation.json"), "w"), indent=2)
print(json.dumps(rep, indent=1))
