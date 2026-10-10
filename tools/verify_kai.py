#!/usr/bin/env python3
"""Verify Kai's exported FBX files the way Unreal will see them: re-import each one into an empty Blender scene
and check the skeleton, skin weights, morph targets, normals, materials, textures and size.

    python3 tools/verify_kai.py [build dir, default kai]

Writes verify_report.json into the build dir and exits non-zero if any check fails.
"""
import glob, json, os, sys
import numpy as np
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kai_geometry as G

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
D = os.path.abspath(argv[0] if argv else "kai")
stats = json.load(open(os.path.join(D, "source_stats.json")))
SK = G.skeleton()
EXPECT_BONES = {b[0]: np.array(b[1]) for b in SK}
MOUTH_KEYS = sorted(k for k in G.MOUTH_SHAPES if k != "rest")
report, failures = {}, []


def check(cond, msg):
    if not cond: failures.append(msg)
    return bool(cond)


def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path, use_custom_normals=True, ignore_leaf_bones=False,
                             automatic_bone_orientation=False, axis_forward="X", axis_up="Z")
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    return arms, meshes


for path in sorted(glob.glob(os.path.join(D, "SK_Kai*.fbx"))):
    name = os.path.splitext(os.path.basename(path))[0]
    arms, meshes = load(path)
    r = dict(file=os.path.basename(path), size_mb=round(os.path.getsize(path) / 1e6, 2))
    check(len(arms) == 1, f"{name}: expected one armature, found {len(arms)}")
    rig = arms[0]
    names = [b.name for b in rig.data.bones]
    r["bones"] = len(names)
    check(len(names) == len(EXPECT_BONES), f"{name}: {len(names)} bones, expected {len(EXPECT_BONES)}")
    check(set(names) == set(EXPECT_BONES), f"{name}: bone names differ from the skeleton")
    check(len({b.name for b in rig.data.bones if b.parent is None}) == 1 and rig.data.bones[0].name == "root",
          f"{name}: the hierarchy should have a single root bone named root")
    # rest pose: bone heads where the skeleton puts them (cm, in Blender's frame)
    M = np.array(rig.matrix_world)
    err = max(np.linalg.norm((M[:3, :3] @ np.array(b.head_local) + M[:3, 3]) * 100.0 - EXPECT_BONES[b.name])
              for b in rig.data.bones if b.name in EXPECT_BONES)
    r["rest_pose_max_error_cm"] = round(float(err), 4)
    check(err < 0.05, f"{name}: rest pose off by {err:.3f} cm")
    tris, top, low = 0, -1e9, 1e9
    r["meshes"] = {}
    for ob in meshes:
        me = ob.data
        me.calc_loop_triangles()
        nt = len(me.loop_triangles); tris += nt
        Mw = np.array(ob.matrix_world)
        P = np.array([v.co[:] for v in me.vertices]) @ Mw[:3, :3].T + Mw[:3, 3]
        top, low = max(top, P[:, 2].max() * 100), min(low, P[:, 2].min() * 100)
        gi = {g.index: g.name for g in ob.vertex_groups}
        infl = np.array([len([g for g in v.groups if g.weight > 1e-6]) for v in me.vertices])
        wsum = np.array([sum(g.weight for g in v.groups) for v in me.vertices])
        unknown = {gi[g.group] for v in me.vertices for g in v.groups} - set(EXPECT_BONES)
        mods = [m for m in ob.modifiers if m.type == "ARMATURE"]
        mr = dict(triangles=nt, max_influences=int(infl.max()), unweighted=int((infl == 0).sum()),
                  weight_sum_range=[round(float(wsum.min()), 3), round(float(wsum.max()), 3)],
                  materials=[m.name for m in me.materials if m],
                  morph_targets=[k.name for k in me.shape_keys.key_blocks[1:]] if me.shape_keys else [],
                  custom_normals=bool(me.has_custom_normals))
        check(mods and mods[0].object == rig, f"{name}/{ob.name}: not skinned to the armature")
        check(mr["max_influences"] <= 4, f"{name}/{ob.name}: {mr['max_influences']} bone influences on a vertex (max 4)")
        check(mr["unweighted"] == 0, f"{name}/{ob.name}: {mr['unweighted']} vertices without weights")
        check(abs(wsum.min() - 1) < 0.01 and abs(wsum.max() - 1) < 0.01, f"{name}/{ob.name}: weights do not sum to 1")
        check(not unknown, f"{name}/{ob.name}: weights on unknown bones {sorted(unknown)}")
        check(mr["materials"], f"{name}/{ob.name}: no material")
        for m in me.materials:
            if not m or not m.use_nodes: continue
            imgs = [n.image for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
            check(imgs and all(i.has_data or i.packed_file or os.path.exists(bpy.path.abspath(i.filepath)) for i in imgs),
                  f"{name}/{ob.name}: material {m.name} has no colour texture")
        if "Head" in ob.name or "SK_Kai" == name:
            if mr["morph_targets"]:
                check(sorted(mr["morph_targets"]) == MOUTH_KEYS, f"{name}/{ob.name}: morph targets {mr['morph_targets']}")
        r["meshes"][ob.name] = mr
    r["triangles"] = tris
    r["height_cm"] = round(top - low, 2)
    if name in ("SK_Kai", "SK_Kai_Head"):
        heads = [m for m in r["meshes"].values() if m["morph_targets"]]
        check(heads and sorted(heads[0]["morph_targets"]) == MOUTH_KEYS, f"{name}: mouth morph targets missing")
        check(any(m["custom_normals"] for m in r["meshes"].values()), f"{name}: custom normals (ears, eye domes) missing")
    if name == "SK_Kai":
        check(abs(r["height_cm"] - stats["height_cm"]) < 1.0, f"SK_Kai: height {r['height_cm']} cm, expected {stats['height_cm']}")
    report[name] = r
    print(f"{name:24s} bones {r['bones']}  tris {tris:6d}  height {r['height_cm']:6.1f} cm  rest err {r['rest_pose_max_error_cm']} cm", flush=True)

check(len(report) >= 11, f"expected 11 or more FBX files, found {len(report)}")
out = dict(ok=not failures, failures=failures, files=report)
json.dump(out, open(os.path.join(D, "verify_report.json"), "w"), indent=2)
print("\n".join(failures) if failures else "", "VERIFY_OK" if not failures else f"VERIFY_FAIL {len(failures)}")
sys.exit(1 if failures else 0)
