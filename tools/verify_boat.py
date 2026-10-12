#!/usr/bin/env python3
"""Verify the boat's exported FBX files the way Unreal will see them: re-import each one into an empty Blender scene
and check the mesh, its pivot, collision pieces (UCX_, each convex), sockets (SOCKET_, where Boat expects them),
material and texture, UVs and face orientation.

    python3 tools/verify_boat.py [build dir, default boat]

Writes verify_report.json into the build dir and exits non-zero if any check fails.
"""
import json, os, sys
import numpy as np
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boat_geometry as B

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
D = os.path.abspath(argv[0] if argv else "boat")
stats = json.load(open(os.path.join(D, "source_stats.json")))
report, failures = {}, []


def check(cond, msg):
    if not cond: failures.append(msg)
    return bool(cond)


def world_verts(ob):
    M = np.array(ob.matrix_world)
    V = np.array([v.co[:] for v in ob.data.vertices]) @ M[:3, :3].T + M[:3, 3]
    return V * 100.0                                         # metres in Blender after import -> cm


def is_convex(ob, tol=0.05):
    """No vertex lies more than tol cm outside the plane of any face (sliver faces from coplanar points skipped)."""
    V = world_verts(ob); ob.data.calc_loop_triangles()
    for t in ob.data.loop_triangles:
        a, b, c = V[list(t.vertices)]
        n = np.cross(b - a, c - a); area = np.linalg.norm(n)
        if area < 0.5: continue
        if ((V - a) @ (n / area) > tol).any(): return False
    return True


def signed_volume(ob):
    V = world_verts(ob); ob.data.calc_loop_triangles()
    T = np.array([t.vertices[:] for t in ob.data.loop_triangles])
    return float(np.einsum("ij,ij->i", V[T[:, 0]], np.cross(V[T[:, 1]], V[T[:, 2]])).sum() / 6.0)


EXPECT = {
    "SM_Boat_Hull": dict(origin=np.zeros(3), sockets={n: v[0] for n, v in B.sockets().items()}, closed=False),
    "SM_Boat_Motor": dict(origin=B.MOTOR_PIVOT, sockets={n: v[0] for n, v in B.motor_sockets().items()}, closed=True),
    "SM_Boat_Propeller": dict(origin=B.PROP_C, sockets={}, closed=True),
    "SM_Boat_Wheel": dict(origin=B.WHEEL_C, sockets={}, closed=True),
}
for name, exp in EXPECT.items():
    path = os.path.join(D, name + ".fbx")
    if not check(os.path.exists(path), f"{name}.fbx missing"): continue
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path, axis_forward="X", axis_up="Z", use_custom_normals=True)
    obs = {o.name: o for o in bpy.data.objects}
    r = dict(file=name + ".fbx", size_mb=round(os.path.getsize(path) / 1e6, 2))
    if not check(name in obs, f"{name}: mesh missing from its FBX"): continue
    ob = obs[name]; me = ob.data
    V = world_verts(ob)
    me.calc_loop_triangles()
    r["triangles"] = len(me.loop_triangles)
    r["bounds_cm"] = [np.round(V.min(0), 1).tolist(), np.round(V.max(0), 1).tolist()]
    # the pivot: everything was exported in the part's own frame, so the boat-frame geometry is V + origin
    Vb = V + exp["origin"]
    if name == "SM_Boat_Hull":
        check(abs(V[:, 2].min()) < 0.5, f"{name}: keel bottom at z {V[:, 2].min():.2f} cm, expected 0")
        check(abs(V[:, 0].max() - (B.XB + B.RAKE + 4.2)) < 3.0, f"{name}: bow at x {V[:, 0].max():.1f}")
        check(abs(V[:, 1].max() + V[:, 1].min()) < 0.5, f"{name}: not symmetric about the centreline")
    if name == "SM_Boat_Motor":
        axis = (np.hypot(V[:, 0], V[:, 1]) < 2.6) & (V[:, 2] < 0) & (V[:, 2] > B.sheer_z(B.XS) - 9 - B.MOTOR_PIVOT[2])
        check(axis.sum() > 10, f"{name}: no swivel tube on the steering axis (origin)")
        check(Vb[:, 2].min() < B.PROP_C[2] - 6, f"{name}: the skeg should reach below the propeller")
    if name == "SM_Boat_Propeller":                          # three-fold symmetric, so its surface centroid is on the axis
        T = np.array([t.vertices[:] for t in me.loop_triangles])
        area = np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1)
        c = (V[T].mean(1) * area[:, None]).sum(0) / area.sum()
        r["centroid_cm"] = np.round(c, 3).tolist()
        check(np.abs(c[1:]).max() < 0.3, f"{name}: hub not on the X axis through the origin (centroid {np.round(c, 2)})")
    if name == "SM_Boat_Wheel":                              # the rim runs round the local X axis through the origin
        rad = np.hypot(V[:, 1], V[:, 2])
        check(abs(rad.max() - (B.WHEEL_R + B.WHEEL_RIM)) < 0.3 and np.abs(V[:, 0]).max() < 3.5,
              f"{name}: rim not round the X axis through the origin")
    # material and texture
    mats = [m for m in me.materials if m]
    r["materials"] = [m.name for m in mats]
    check(len(mats) == 1 and mats[0].name == "M_" + name[3:], f"{name}: material {r['materials']}")
    imgs = [n.image for m in mats if m.node_tree for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
    check(imgs, f"{name}: no colour texture")
    # UVs inside 0..1
    uv = np.empty(len(me.loops) * 2); me.uv_layers[0].data.foreach_get("uv", uv)
    check(uv.min() >= -1e-4 and uv.max() <= 1 + 1e-4, f"{name}: UVs outside 0..1")
    if exp["closed"]:
        vol = signed_volume(ob); r["volume_cm3"] = round(vol, 1)
        check(vol > 0, f"{name}: faces point inward (signed volume {vol:.1f})")
    # collision
    ucx = sorted(n for n in obs if n.startswith(f"UCX_{name}_"))
    r["collision"] = len(ucx)
    check(ucx == sorted(stats["meshes"][name]["collision"]), f"{name}: collision pieces {ucx}")
    for n in ucx:
        check(is_convex(obs[n]), f"{n}: not convex")
        check(signed_volume(obs[n]) > 0, f"{n}: faces point inward")
    # sockets
    socks = {n[7:]: o for n, o in obs.items() if n.startswith("SOCKET_")}
    r["sockets"] = sorted(socks)
    check(set(socks) == set(exp["sockets"]), f"{name}: sockets {sorted(socks)}")
    err = 0.0
    for n, loc in exp["sockets"].items():
        if n not in socks: continue
        p = np.array(socks[n].matrix_world.translation) * 100.0 + exp["origin"]
        err = max(err, float(np.linalg.norm(p - loc)))
        fwd = np.array(socks[n].matrix_world.to_3x3().col[0]); fwd /= np.linalg.norm(fwd)
        want = (B.sockets() if name == "SM_Boat_Hull" else B.motor_sockets())[n][1]
        check(fwd @ want > 0.999, f"{name}: socket {n} faces {np.round(fwd, 3)}, expected {want}")
        check(socks[n].parent == ob, f"{name}: socket {n} is not parented to the mesh")
    r["socket_max_error_cm"] = round(err, 4)
    check(err < 0.05, f"{name}: sockets off by {err:.3f} cm")
    report[name] = r
    print(f"{name:20s} tris {r['triangles']:6d}  collision {r['collision']:2d}  sockets {len(r['sockets']):2d}  "
          f"bounds {r['bounds_cm']}", flush=True)

out = dict(ok=not failures, failures=failures, files=report)
json.dump(out, open(os.path.join(D, "verify_report.json"), "w"), indent=2)
print("\n".join(failures) if failures else "", "VERIFY_OK" if not failures else f"VERIFY_FAIL {len(failures)}")
sys.exit(1 if failures else 0)
