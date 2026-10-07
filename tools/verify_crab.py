#!/usr/bin/env python3
"""Check the crab package: re-import every FBX, then measure loop seams, foot slip against the stated ground
speed and ground contact of the deformed mesh in every clip. Writes <dir>/anim_validation.json.

    python3 tools/verify_crab.py crab
"""
import glob, json, math, os, sys
import bpy
import numpy as np

D = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "crab")
LOOPS = {"Crab_Idle", "Crab_Scuttle_Left", "Crab_Scuttle_Right", "Crab_Walk_Forward"}
report = {}


def set_action(rig, act):
    rig.animation_data.action = act
    if hasattr(act, "slots") and act.slots: rig.animation_data.action_slot = act.slots[0]


# ---- FBX re-imports --------------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=os.path.join(D, "SK_Crab.fbx"))
arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
m = meshes[0]; m.data.calc_loop_triangles()
tops = [b.name for b in arms[0].data.bones if b.parent is None]
weights_ok = all(len(v.groups) == 1 and abs(v.groups[0].weight - 1) < 1e-4 for v in m.data.vertices)
report["skeletal_mesh"] = dict(armature_object=arms[0].name, bones=len(arms[0].data.bones), top_bones=tops,
                               triangles=len(m.data.loop_triangles), materials=[s.material.name for s in m.material_slots],
                               embedded_images=sorted(i.name for i in bpy.data.images),
                               every_vertex_one_bone_weight_1=weights_ok,
                               height_cm=round(max((m.matrix_world @ v.co).z for v in m.data.vertices) * 100, 1))
clips = {}
for f in sorted(glob.glob(os.path.join(D, "AN_Crab_*.fbx"))):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=f)
    arm = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"][0]
    act = arm.animation_data.action if arm.animation_data else None
    clips[os.path.basename(f)] = dict(objects=[o.type for o in bpy.context.scene.objects], bones=len(arm.data.bones),
                                      top_bones=[b.name for b in arm.data.bones if b.parent is None],
                                      frames=int(round(act.frame_range[1] - act.frame_range[0])) + 1 if act else 0)
report["animation_fbx"] = clips

# ---- clip measurements on the authored scene ------------------------------------------------------
bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "Crab_Anims.blend"))
stats = json.load(open(os.path.join(D, "anim_stats.json")))
rig = bpy.data.objects["Armature"]; mesh = bpy.data.objects["SK_Crab"]
sc = bpy.context.scene
tips = [b.name for b in rig.data.bones if "_tip." in b.name]
res = {}
for act in sorted([a for a in bpy.data.actions if a.name.startswith("Crab_")], key=lambda a: a.name):
    set_action(rig, act)
    n = int(round(act.frame_range[1]))
    poses, tipw, mesh_min = [], [], []
    for f in range(1, n + 1):
        sc.frame_set(f)
        poses.append({pb.name: np.array(pb.matrix_basis) for pb in rig.pose.bones})
        tipw.append({t: np.array(rig.matrix_world @ rig.pose.bones[t].tail) for t in tips})
        dg = bpy.context.evaluated_depsgraph_get(); ev = mesh.evaluated_get(dg); me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co)
        mesh_min.append(float(co.reshape(-1, 3)[:, 2].min())); ev.to_mesh_clear()
    r = dict(frames=n, mesh_min_z_cm=round(min(mesh_min), 3), lowest_frame=int(np.argmin(mesh_min)) + 1)
    if act.name in LOOPS:
        r["loop_seam_max_diff"] = float(max(np.abs(poses[0][b] - poses[-1][b]).max() for b in poses[0]))
    speed = {"Crab_Scuttle_Left": (stats["scuttle_speed_cm_s"], (1, 0)), "Crab_Scuttle_Right": (stats["scuttle_speed_cm_s"], (-1, 0)),
             "Crab_Walk_Forward": (stats["walk_speed_cm_s"], (0, -1)), "Crab_Idle": (0.0, (0, 0))}.get(act.name)
    if speed:
        v, d = speed
        exp = -np.array(d, float) * v / 30.0                  # in-place clip: planted feet slide back at the ground speed
        dev, planted = 0.0, 0
        for f in range(n - 1):
            for t in tips:
                if tipw[f][t][2] < 0.02 and tipw[f + 1][t][2] < 0.02:
                    planted += 1
                    dev = max(dev, float(np.linalg.norm((tipw[f + 1][t] - tipw[f][t])[:2] - exp)))
        r["foot_slip_cm_per_frame"] = round(dev, 4); r["planted_samples"] = planted
        r["ground_speed_cm_s"] = v
    r["tip_min_z_cm"] = round(float(min(min(tw[t][2] for t in tips) for tw in tipw)), 3)
    res[act.name] = r
    print(act.name, r, flush=True)
report["clips"] = res
report["pass"] = bool(
    report["skeletal_mesh"]["bones"] == 36 and report["skeletal_mesh"]["top_bones"] == ["root"]
    and report["skeletal_mesh"]["every_vertex_one_bone_weight_1"]
    and all(c["bones"] == 36 and c["top_bones"] == ["root"] for c in clips.values())
    and all(r.get("loop_seam_max_diff", 0) < 1e-4 for r in res.values())
    and all(r.get("foot_slip_cm_per_frame", 0) < 0.01 for r in res.values())
    and all(r["mesh_min_z_cm"] > -0.6 for r in res.values()))
json.dump(report, open(os.path.join(D, "anim_validation.json"), "w"), indent=2)
print("VERIFY_PASS" if report["pass"] else "VERIFY_FAIL", flush=True)
