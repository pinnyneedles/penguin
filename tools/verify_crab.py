#!/usr/bin/env python3
"""Check the crab package: re-import every FBX (the mesh, its three levels of detail and every clip), then measure
on the authored clips: loop seams, foot slip against the stated ground speed or turn rate, that the IK goal bones
follow the feet and claw tips exactly, and ground contact of the deformed mesh. Writes <dir>/anim_validation.json.

    python3 tools/verify_crab.py crab
"""
import glob, json, math, os, sys
import bpy
import numpy as np

D = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "crab")
BONES = 80
stats = json.load(open(os.path.join(D, "anim_stats.json")))
LOOPS = {n for n, c in stats["clips"].items() if c["loop"]}
report = {}


def set_action(rig, act):
    rig.animation_data.action = act
    if hasattr(act, "slots") and act.slots: rig.animation_data.action_slot = act.slots[0]


# ---- FBX re-imports --------------------------------------------------------------------------------
def import_mesh(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    arm = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"][0]
    m = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]; m.data.calc_loop_triangles()
    bones = {b.name for b in arm.data.bones}
    return dict(armature_object=arm.name, bones=len(bones), top_bones=[b.name for b in arm.data.bones if b.parent is None],
                triangles=len(m.data.loop_triangles), materials=[s.material.name for s in m.material_slots],
                embedded_images=sorted(i.name for i in bpy.data.images),
                every_vertex_one_bone_weight_1=all(len(v.groups) == 1 and abs(v.groups[0].weight - 1) < 1e-4 for v in m.data.vertices),
                skinned_bones=len(m.vertex_groups), groups_are_bones=all(g.name in bones for g in m.vertex_groups),
                height_cm=round(max((m.matrix_world @ v.co).z for v in m.data.vertices) * 100, 1)), sorted(bones)


report["skeletal_mesh"], names0 = import_mesh(os.path.join(D, "SK_Crab.fbx"))
report["lods"] = {}
for lv in (1, 2, 3):
    r, names = import_mesh(os.path.join(D, f"SK_Crab_LOD{lv}.fbx"))
    r["same_skeleton_as_lod0"] = names == names0
    report["lods"][f"LOD{lv}"] = r
clips = {}
for f in sorted(glob.glob(os.path.join(D, "AN_Crab_*.fbx"))):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=f)
    arm = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"][0]
    act = arm.animation_data.action if arm.animation_data else None
    clips[os.path.basename(f)] = dict(objects=[o.type for o in bpy.context.scene.objects], bones=len(arm.data.bones),
                                      same_skeleton_as_mesh=sorted(b.name for b in arm.data.bones) == names0,
                                      top_bones=[b.name for b in arm.data.bones if b.parent is None],
                                      frames=int(round(act.frame_range[1] - act.frame_range[0])) + 1 if act else 0)
report["animation_fbx"] = clips

# ---- clip measurements on the authored scene ------------------------------------------------------
bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "Crab_Anims.blend"))
rig = bpy.data.objects["Armature"]; mesh = bpy.data.objects["SK_Crab"]
sc = bpy.context.scene
ends = [b.name for b in rig.data.bones if "_end_" in b.name]
goal_pairs = [(f"ik_{e.replace('_end', '')}", e) for e in ends] + [(f"ik_claw_{s}", f"claw_tip_{s}") for s in "lr"]
ankle_pairs = [(f"ik_{e.replace('_end_', '_ankle_')}", e.replace("_end", "_tip")) for e in ends]
res = {}
for act in sorted([a for a in bpy.data.actions if a.name.startswith("Crab_")], key=lambda a: a.name):
    set_action(rig, act)
    n = int(round(act.frame_range[1]))
    poses, feet, mesh_min, sync = [], [], [], 0.0
    for f in range(1, n + 1):
        sc.frame_set(f)
        poses.append({pb.name: np.array(pb.matrix_basis) for pb in rig.pose.bones})
        feet.append({e: np.array(rig.pose.bones[e].head) for e in ends})
        pm = lambda b: np.array(rig.pose.bones[b].matrix)
        sync = max([sync] + [float(np.abs(pm(g) - pm(s)).max()) for g, s in goal_pairs + ankle_pairs])
        dg = bpy.context.evaluated_depsgraph_get(); ev = mesh.evaluated_get(dg); me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co)
        mesh_min.append(float(co.reshape(-1, 3)[:, 2].min())); ev.to_mesh_clear()
    r = dict(frames=n, mesh_min_z_cm=round(min(mesh_min), 3), lowest_frame=int(np.argmin(mesh_min)) + 1,
             ik_goals_match_feet_and_claws=round(sync, 5))
    if act.name in LOOPS:
        r["loop_seam_max_diff"] = float(max(np.abs(poses[0][b] - poses[-1][b]).max() for b in poses[0]))
    c = stats["clips"].get(act.name, {})
    move = {"Crab_Scuttle_Left": (1, 0), "Crab_Scuttle_Right": (-1, 0), "Crab_Walk_Forward": (0, -1), "Crab_Walk_Backward": (0, 1)}
    if act.name in move or "turn_deg_s" in c or act.name == "Crab_Idle":
        v = c.get("speed_cm_s", 0.0); d = np.array(move.get(act.name, (0, 0)), float)
        w = math.radians(c.get("turn_deg_s", 0.0)) / 30.0
        Rz = np.array([[math.cos(-w), -math.sin(-w)], [math.sin(-w), math.cos(-w)]])
        dev, planted = 0.0, 0
        for f in range(n - 1):
            for e in ends:
                p0, p1 = feet[f][e], feet[f + 1][e]
                if p0[2] < 0.02 and p1[2] < 0.02:               # in-place clip: planted feet move against the actor
                    planted += 1
                    dev = max(dev, float(np.linalg.norm(p1[:2] - (Rz @ p0[:2] - d * v / 30.0))))
        r["foot_slip_cm_per_frame"] = round(dev, 4); r["planted_samples"] = planted
        if v: r["ground_speed_cm_s"] = v
        if w: r["turn_deg_s"] = c["turn_deg_s"]
    r["foot_min_z_cm"] = round(float(min(min(ft[e][2] for e in ends) for ft in feet)), 3)
    res[act.name] = r
    print(act.name, r, flush=True)
report["clips"] = res
demo = os.path.join(D, "procedural_demo.json")
if os.path.exists(demo): report["procedural_demo"] = json.load(open(demo))
sk = report["skeletal_mesh"]
report["pass"] = bool(
    sk["bones"] == BONES and sk["top_bones"] == ["root"] and sk["every_vertex_one_bone_weight_1"] and sk["groups_are_bones"]
    and all(l["bones"] == BONES and l["same_skeleton_as_lod0"] and l["every_vertex_one_bone_weight_1"] for l in report["lods"].values())
    and len(clips) == len(stats["clips"])
    and all(c["bones"] == BONES and c["top_bones"] == ["root"] and c["same_skeleton_as_mesh"] for c in clips.values())
    and all(r.get("loop_seam_max_diff", 0) < 1e-4 for r in res.values())
    and all(r.get("foot_slip_cm_per_frame", 0) < 0.01 for r in res.values())
    and all(r["ik_goals_match_feet_and_claws"] < 1e-3 for r in res.values())
    and all(r["mesh_min_z_cm"] > -0.6 for r in res.values())
    and report.get("procedural_demo", {}).get("planted_foot_slip_cm", 0) < 0.01)
json.dump(report, open(os.path.join(D, "anim_validation.json"), "w"), indent=2)
print("VERIFY_PASS" if report["pass"] else "VERIFY_FAIL", flush=True)
