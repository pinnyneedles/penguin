#!/usr/bin/env python3
"""Penguin level kit: game-ready static meshes for Unreal Engine 5, built procedurally in Blender.

    python3 tools/make_props.py [--out props/Kit] [--only name1,name2] [--tex-size 1024]
    python3 tools/render_props.py props/Kit          # previews: Previews/Kit_Sheet.png, Kit_Vignette.png

Conventions (all props):
  * Centimetres, Z up. Pivot on the floor at the centre of the footprint (icicles: top centre;
    slide-chute pieces: centre of the entrance floor).
  * 100 cm grid. Blocks, ramps and chutes are multiples of 100 cm so they snap together.
  * UV0 is world-scaled (one texture tile = TILE cm), so all props share tileable texture sets
    and texel density stays even. Let Unreal generate lightmap UVs if you use baked lighting.
  * Collision: UCX_<mesh>_NN convex hulls exported with each mesh (Unreal imports them as simple
    collision). Chutes are split into many hulls so the slide floor and walls are accurate.
  * Slide-chute pieces carry SOCKET_Start / SOCKET_End empties (imported as static mesh sockets).
    Snap the next piece's actor to the previous piece's SOCKET_End to chain a track.
  * Materials: M_Ice, M_Snow, M_Rock, M_Fish, M_FishEye. Texture sets T_<Set>_BaseColor (sRGB),
    T_<Set>_Normal_DX (Unreal), T_<Set>_Normal_GL (Blender), T_<Set>_ORM (AO, roughness, metallic).
"""
import argparse, json, math, os, random, sys
import bpy, bmesh
import numpy as np
from mathutils import Vector, Matrix, noise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prop_textures as PT

TILE = {"Ice": 200.0, "Snow": 200.0, "Rock": 100.0}


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="props/Kit")
    ap.add_argument("--only", default="")
    ap.add_argument("--tex-size", type=int, default=1024)
    return ap.parse_args(argv)


# ---------------------------------------------------------------------------
# Scene, textures, materials
# ---------------------------------------------------------------------------
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"; sc.unit_settings.scale_length = 0.01
    return sc


def load_img(path, color=True):
    img = bpy.data.images.load(path)
    if not color:
        img.colorspace_settings.name = "Non-Color"
    return img


def make_textures(out, N):
    tdir = os.path.join(out, "Textures")
    for name in PT.SETS:
        PT.save_set(tdir, name, N)
    return tdir


def pbr_material(name, tdir, setname, extra=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    bs = N.get("Principled BSDF")
    col = N.new("ShaderNodeTexImage"); col.image = load_img(os.path.join(tdir, f"T_{setname}_BaseColor.png"))
    orm = N.new("ShaderNodeTexImage"); orm.image = load_img(os.path.join(tdir, f"T_{setname}_ORM.png"), False)
    nrm = N.new("ShaderNodeTexImage"); nrm.image = load_img(os.path.join(tdir, f"T_{setname}_Normal_GL.png"), False)
    sep = N.new("ShaderNodeSeparateColor"); nmap = N.new("ShaderNodeNormalMap")
    L.new(col.outputs["Color"], bs.inputs["Base Color"])
    L.new(orm.outputs["Color"], sep.inputs["Color"]); L.new(sep.outputs["Green"], bs.inputs["Roughness"])
    L.new(nrm.outputs["Color"], nmap.inputs["Color"]); L.new(nmap.outputs["Normal"], bs.inputs["Normal"])
    for k, v in (extra or {}).items():
        if k in bs.inputs: bs.inputs[k].default_value = v
    return m


def flat_material(name, color, rough, extra=None):
    m = bpy.data.materials.new(name); m.use_nodes = True
    bs = m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1); bs.inputs["Roughness"].default_value = rough
    for k, v in (extra or {}).items():
        if k in bs.inputs: bs.inputs[k].default_value = v
    m.diffuse_color = (*color, 1)
    return m


def build_materials(tdir):
    return {
        # ice glows a little from within in Blender; in Unreal use Subsurface or a fresnel tint (see guide)
        "Ice": pbr_material("M_Ice", tdir, "Ice", {"Subsurface Weight": 0.35, "Subsurface Radius": (0.6, 1.2, 1.8),
                                                    "Subsurface Scale": 12.0, "Coat Weight": 0.4, "Coat Roughness": 0.05}),
        "Snow": pbr_material("M_Snow", tdir, "Snow", {"Subsurface Weight": 0.15, "Subsurface Scale": 4.0}),
        "Rock": pbr_material("M_Rock", tdir, "Rock"),
        "Fish": flat_material("M_Fish", (0.90, 0.40, 0.05), 0.3, {"Coat Weight": 0.5}),   # warm gold reads against ice and snow
        "FishEye": flat_material("M_FishEye", (0.01, 0.01, 0.012), 0.1),
    }


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------
class Part:
    """Accumulates geometry with per-face material keys and per-loop UVs, then builds one object."""
    def __init__(self):
        self.v = []; self.f = []; self.m = []; self.uv = []

    def add(self, verts, faces, mat, uvs=None):
        o = len(self.v); self.v += [tuple(p) for p in verts]
        for k, face in enumerate(faces):
            self.f.append(tuple(i + o for i in face)); self.m.append(mat)
            self.uv.append(uvs[k] if uvs is not None else None)

    def build(self, name, mats, sharp_deg=35.0):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f); me.update()
        ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
        keys = sorted(set(self.m), key=lambda k: list(mats).index(k))
        for k in keys: me.materials.append(mats[k])
        for p, k in zip(me.polygons, self.m): p.material_index = keys.index(k)
        uvl = me.uv_layers.new(name="UVMap")
        for p, k, uvs in zip(me.polygons, self.m, self.uv):
            if uvs is not None:
                for li, uv in zip(p.loop_indices, uvs): uvl.data[li].uv = uv
        box_project(ob, [i for i, u in enumerate(self.uv) if u is None], {i: self.m[i] for i in range(len(self.m))})
        finish_mesh(ob, sharp_deg)
        return ob


def box_project(ob, face_ids, face_mat):
    """World-scaled box-projection UVs for the given faces (tile size from the face's material set)."""
    me = ob.data; uvl = me.uv_layers[0]
    for fi in face_ids:
        p = me.polygons[fi]; n = p.normal; ax = int(np.argmax(np.abs(np.array(n))))
        tile = TILE.get(face_mat[fi], 200.0)
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if ax == 2: u, v = co.x, co.y
            elif ax == 0: u, v = co.y * (1 if n.x > 0 else -1), co.z
            else: u, v = co.x * (-1 if n.y > 0 else 1), co.z
            uvl.data[li].uv = (u / tile, v / tile)


def finish_mesh(ob, sharp_deg):
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ngons = [f for f in bm.faces if len(f.verts) > 4]                 # FBX can't export tangents for n-gons
    if ngons: bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
    thr = math.radians(sharp_deg)
    for f in bm.faces: f.smooth = True
    for e in bm.edges:
        e.smooth = not (e.is_boundary or (len(e.link_faces) == 2 and e.calc_face_angle(0) > thr))
    bm.to_mesh(ob.data); bm.free(); ob.data.update()


def bm_object(name, bm, mat, mats):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    me.materials.append(mats[mat]); me.uv_layers.new(name="UVMap")
    box_project(ob, range(len(me.polygons)), {i: mat for i in range(len(me.polygons))})
    return ob


def hull_object(name, points):
    bm = bmesh.new()
    for p in points: bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=bm.verts)
    for v in [v for v in bm.verts if not v.link_faces]: bm.verts.remove(v)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    ob.display_type = "WIRE"
    return ob


def socket(name, parent, matrix):
    e = bpy.data.objects.new(name, None); e.empty_display_type = "ARROWS"; e.empty_display_size = 40
    bpy.context.scene.collection.objects.link(e)
    e.matrix_world = matrix; e.parent = parent; e.matrix_parent_inverse = parent.matrix_world.inverted()
    return e


def displace(bm, amp, scale, seed, mask=None):
    bm.normal_update()
    off = Vector((seed * 13.1, seed * 7.7, seed * 3.3))
    for v in bm.verts:
        if mask and not mask(v): continue
        n = noise.fractal(v.co / scale + off, 0.5, 2.0, 4)
        v.co += v.normal * amp * n


# ---------------------------------------------------------------------------
# Prop builders. Each returns (render object, [collision objects], [sockets], info)
# ---------------------------------------------------------------------------
def ice_block(name, mats, sx, sy, sz, bevel=6.0, chips=3, seed=1, snowcap=False):
    rnd = random.Random(seed)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x * sx, v.co.y * sy, v.co.z * sz + sz / 2))
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=3, profile=0.5, affect="EDGES", clamp_overlap=True)
    ob = bm_object(name, bm, "Ice", mats)
    # chipped edges: subtract a few rough lumps
    for k in range(chips):
        kind = rnd.choice(("top_x", "top_y", "vertical", "corner"))      # break an edge or a corner
        sxn, syn = rnd.choice((-1, 1)), rnd.choice((-1, 1))
        if kind == "top_x": cx, cy, cz = rnd.uniform(-.35, .35) * sx, syn * sy / 2, sz
        elif kind == "top_y": cx, cy, cz = sxn * sx / 2, rnd.uniform(-.35, .35) * sy, sz
        elif kind == "vertical": cx, cy, cz = sxn * sx / 2, syn * sy / 2, rnd.uniform(.25, .8) * sz
        else: cx, cy, cz = sxn * sx / 2, syn * sy / 2, sz
        r = rnd.uniform(0.10, 0.16) * min(sx, sy, max(sz, 0.6 * sx))
        cb = bmesh.new(); bmesh.ops.create_icosphere(cb, subdivisions=1, radius=r)
        for v in cb.verts: v.co = Vector((v.co.x * rnd.uniform(.8, 1.4), v.co.y * rnd.uniform(.8, 1.4), v.co.z * rnd.uniform(.6, 1.0)))
        for v in cb.verts: v.co += Vector((cx, cy, cz))
        cme = bpy.data.meshes.new("chip"); cb.to_mesh(cme); cb.free()
        cut = bpy.data.objects.new("chip", cme); bpy.context.scene.collection.objects.link(cut)
        mod = ob.modifiers.new("chip", "BOOLEAN"); mod.operation = "DIFFERENCE"; mod.solver = "EXACT"; mod.object = cut
        bpy.context.view_layer.objects.active = ob; bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cut)
    me = ob.data
    for p in me.polygons: p.material_index = 0
    box_project(ob, range(len(me.polygons)), {i: "Ice" for i in range(len(me.polygons))})
    finish_mesh(ob, 35)
    parts = [ob]
    top = sz
    if snowcap:
        # a rounded pillow of snow: a subdivided cube pushed out to a rounded box, domed on top, that
        # overhangs the block by 6 cm and rolls down over the top edges
        hx, hy, hz, rr = sx / 2 + 6, sy / 2 + 6, 12.0, 11.0
        cb = bmesh.new(); bmesh.ops.create_cube(cb, size=2.0)
        bmesh.ops.subdivide_edges(cb, edges=cb.edges[:], cuts=11, use_grid_fill=True)
        half = Vector((hx, hy, hz)); inner_lim = Vector((1 - rr / hx, 1 - rr / hy, 1 - rr / hz))
        for v in cb.verts:
            p = v.co.copy()
            inner = Vector([max(-inner_lim[i], min(inner_lim[i], p[i])) for i in range(3)])
            off = Vector([(p[i] - inner[i]) * half[i] for i in range(3)])
            q = Vector([inner[i] * half[i] for i in range(3)]) + (off.normalized() * rr if off.length > 1e-6 else Vector())
            radial = max(abs(q.x) / hx, abs(q.y) / hy)
            if q.z > 0: q.z += 9 * (1 - min(radial, 1) ** 2.5)          # domed, heaviest in the middle
            v.co = q
        bmesh.ops.delete(cb, geom=[f for f in cb.faces if f.calc_center_median().z < -hz + 1], context="FACES")  # hidden underside
        bmesh.ops.recalc_face_normals(cb, faces=cb.faces)
        displace(cb, 4.0, 40.0, seed, mask=lambda v: v.co.z > -4)
        for v in cb.verts: v.co.z += sz + hz - 9                           # sits down over the block's top edges
        cap = bm_object(name + "_cap", cb, "Snow", mats); finish_mesh(cap, 70)
        parts.append(cap); top = round(max(v.co.z for v in cap.data.vertices))
    if len(parts) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for p in parts: p.select_set(True)
        bpy.context.view_layer.objects.active = ob; bpy.ops.object.join()
    col = [hull_object(f"UCX_{name}_00", [(x * sx / 2, y * sy / 2, z) for x in (-1, 1) for y in (-1, 1) for z in (0, top)])]
    return ob, col, [], dict(size_cm=[sx, sy, top], pivot="bottom centre")


def ramp(name, mats, L, W, H, mat, lip=3.0):
    """Wedge rising along +X from a lip at x=-L/2 to full height at x=+L/2."""
    x0, x1, w = -L / 2, L / 2, W / 2
    v = [(x0, -w, 0), (x1, -w, 0), (x1, w, 0), (x0, w, 0), (x0, -w, lip), (x1, -w, H), (x1, w, H), (x0, w, lip)]
    f = [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)]
    bm = bmesh.new(); vs = [bm.verts.new(p) for p in v]
    for face in f: bm.faces.new([vs[i] for i in face])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    top_edges = [e for e in bm.edges if all(vv.co.z > 0.5 for vv in e.verts)]
    bmesh.ops.bevel(bm, geom=top_edges, offset=4.0, segments=3, profile=0.5, affect="EDGES", clamp_overlap=True)
    ob = bm_object(name, bm, mat, mats); finish_mesh(ob, 35)
    col = [hull_object(f"UCX_{name}_00", v)]
    return ob, col, [], dict(size_cm=[L, W, H], slope_deg=round(math.degrees(math.atan2(H - lip, L)), 1), pivot="bottom centre")


# Slide chute cross-section (y, z) in cm, counter-clockwise; True = ice (inside), False = snow (rim/outside)
CHUTE_W, CHUTE_WALL, CHUTE_H, CHUTE_BASE, CHUTE_R = 100.0, 30.0, 50.0, 25.0, 20.0


def chute_profile():
    w, t, h, b, r = CHUTE_W, CHUTE_WALL, CHUTE_H, CHUTE_BASE, CHUTE_R
    pts, ice = [], []
    def arc(cy, cz, a0, a1, n=5):
        return [(cy + r * math.cos(a), cz + r * math.sin(a)) for a in np.linspace(a0, a1, n)]
    # outer bottom right -> outer top right -> rounded rim -> inner wall -> rounded floor corners -> ... (loop)
    seq = [((w + t, -b), False), ((w + t, h - 6), False), ((w + t - 6, h), False), ((w + 6, h), True), ((w, h - 6), True)]
    seq += [(p, True) for p in arc(w - r, r, 0, -math.pi / 2, 6)]                                 # right floor corner
    seq += [(p, True) for p in arc(-w + r, r, -math.pi / 2, -math.pi, 6)]                         # left floor corner
    seq += [((-w, h - 6), True), ((-w - 6, h), False), ((-w - t + 6, h), False), ((-w - t, h - 6), False), ((-w - t, -b), False)]
    for p, i in seq:
        if pts and abs(pts[-1][0] - p[0]) < 1e-6 and abs(pts[-1][1] - p[1]) < 1e-6: continue
        pts.append(p); ice.append(i)
    return pts, ice


def chute(name, mats, path, n, kind):
    """Sweep the chute profile along path(s) -> (point, tangent) for s in [0, 1] with n segments."""
    prof, prof_ice = chute_profile()
    m = len(prof)
    frames = []
    for i in range(n + 1):
        P, T = path(i / n); T = T.normalized()
        lat = Vector((0, 0, 1)).cross(T).normalized(); up = T.cross(lat).normalized()
        frames.append((P, T, lat, up))
    # arc length along the floor centre for UVs
    s = [0.0]
    for i in range(1, n + 1): s.append(s[-1] + (frames[i][0] - frames[i - 1][0]).length)
    perim = [0.0]
    for k in range(1, m): perim.append(perim[-1] + math.dist(prof[k], prof[k - 1]))
    perim.append(perim[-1] + math.dist(prof[0], prof[-1]))
    verts = [tuple(P + lat * y + up * z) for (P, T, lat, up) in frames for (y, z) in prof]
    faces, mats_, uvs = [], [], []
    for i in range(n):
        for k in range(m):
            k2 = (k + 1) % m
            a, b_, c, d = i * m + k, i * m + k2, (i + 1) * m + k2, (i + 1) * m + k
            seg_ice = prof_ice[k] and prof_ice[k2]
            tile = TILE["Ice" if seg_ice else "Snow"]
            pk, pk2 = perim[k], (perim[k + 1] if k2 != 0 else perim[m])
            faces.append((a, b_, c, d)); mats_.append("Ice" if seg_ice else "Snow")
            uvs.append([(s[i] / tile, pk / tile), (s[i] / tile, pk2 / tile), (s[i + 1] / tile, pk2 / tile), (s[i + 1] / tile, pk / tile)])
    part = Part(); part.v = verts
    for fa, ma, uv in zip(faces, mats_, uvs): part.f.append(fa); part.m.append(ma); part.uv.append(uv)
    # end caps (triangulated later by bmesh; concave U shape)
    part.f.append(tuple(reversed(range(m)))); part.m.append("Snow"); part.uv.append(None)
    part.f.append(tuple(n * m + k for k in range(m))); part.m.append("Snow"); part.uv.append(None)
    ob = part.build(name, mats, sharp_deg=35)
    bm = bmesh.new(); bm.from_mesh(ob.data)
    big = [f for f in bm.faces if len(f.verts) > 4]
    bmesh.ops.triangulate(bm, faces=big, quad_method="BEAUTY", ngon_method="EAR_CLIP")
    bm.to_mesh(ob.data); bm.free(); ob.data.update()
    # collision: per segment, floor slab + two walls (each convex, chord across the floor corners)
    w, t, h, b = CHUTE_W, CHUTE_WALL, CHUTE_H, CHUTE_BASE
    floor_sec = [(-w - t, -b), (w + t, -b), (w + t, 0), (-w - t, 0)]
    wall_r = [(w - CHUTE_R, 0), (w + t, 0), (w + t, h), (w, h), (w, CHUTE_R)]
    wall_l = [(-y, z) for (y, z) in wall_r]
    cols, ci = [], 0
    for i in range(n):
        for sec in (floor_sec, wall_r, wall_l):
            pts = [tuple(frames[j][0] + frames[j][2] * y + frames[j][3] * z) for j in (i, i + 1) for (y, z) in sec]
            cols.append(hull_object(f"UCX_{name}_{ci:02d}", pts)); ci += 1
    socks = []
    for nm, (P, T, lat, up) in (("SOCKET_Start", frames[0]), ("SOCKET_End", frames[-1])):
        M = Matrix((T, lat, up)).transposed().to_4x4(); M.translation = P
        socks.append(socket(nm, ob, M))
    Pend, Tend = frames[-1][0], frames[-1][1]
    return ob, cols, socks, dict(kind=kind, exit_offset_cm=[round(c, 1) for c in Pend],
                                 exit_direction=[round(c, 3) for c in Tend], inner_width_cm=2 * CHUTE_W,
                                 wall_height_cm=CHUTE_H, pivot="centre of the entrance floor")


def straight_path(L):
    return lambda u: (Vector((L * u, 0, 0)), Vector((1, 0, 0)))


def curve_path(R, side):
    def f(u):
        a = u * math.pi / 2
        return Vector((R * math.sin(a), side * R * (1 - math.cos(a)), 0)), Vector((math.cos(a), side * math.sin(a), 0))
    return f


def slope_path(L, drop):
    def f(u):
        z = -drop * (3 * u * u - 2 * u ** 3); dz = -drop * (6 * u - 6 * u * u) / L
        return Vector((L * u, 0, z)), Vector((1, 0, dz))
    return f


def kicker_path(L, run, angle_deg):
    a_end = math.radians(angle_deg)
    def f(u):
        x = L * u
        if x <= run: return Vector((x, 0, 0)), Vector((1, 0, 0))
        q = (x - run) / (L - run)
        # integrate the climb angle a(q) = a_end * q^2 over the lip
        qs = np.linspace(0, q, 40); ang = a_end * qs ** 2
        trap = getattr(np, "trapezoid", None) or np.trapz          # older numpy inside Blender
        z = trap(np.tan(ang), qs) * (L - run) if q > 0 else 0.0
        a = a_end * q * q
        return Vector((x, 0, z)), Vector((1, 0, math.tan(a)))
    return f


def ice_floe(name, mats, R, thick=40.0, seed=1, n=36):
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 6.28) for _ in range(6)]; am = [rnd.uniform(0.04, 0.10) / (1 + 0.4 * k) for k in range(6)]
    def r(a): return R * (1 + sum(am[k] * math.sin((k + 2) * a + ph[k]) for k in range(6)))
    ang = np.linspace(0, 2 * math.pi, n, endpoint=False)
    out = [(r(a) * math.cos(a), r(a) * math.sin(a)) for a in ang]
    part = Part()
    rings = [(0.93, 0.0), (1.0, thick - 10), (0.98, thick - 3), (0.95, thick)]      # rounded top edge
    vs = [(x * s, y * s, z) for (s, z) in rings for (x, y) in out]
    fs = [(i * n + k, i * n + (k + 1) % n, (i + 1) * n + (k + 1) % n, (i + 1) * n + k) for i in range(3) for k in range(n)]
    fs.append(tuple(reversed(range(n))))                                             # bottom
    part.add(vs, fs, "Ice")
    c = len(part.v); part.v.append((0, 0, thick)); top0 = 3 * n
    part.f += [(top0 + k, top0 + (k + 1) % n, c) for k in range(n)]; part.m += ["Ice"] * n; part.uv += [None] * n
    # snow cover: a soft, slightly domed sheet inset from the edge
    srings = [(0.86, thick - 1), (0.85, thick + 6), (0.80, thick + 10)]
    s0 = len(part.v)
    part.v += [(x * s, y * s, z) for (s, z) in srings for (x, y) in out]
    for i in range(2):
        for k in range(n):
            a = s0 + i * n + k; b_ = s0 + i * n + (k + 1) % n
            part.f.append((a, b_, b_ + n, a + n)); part.m.append("Snow"); part.uv.append(None)
    cc = len(part.v); part.v.append((0, 0, thick + 14))
    t0 = s0 + 2 * n
    part.f += [(t0 + k, t0 + (k + 1) % n, cc) for k in range(n)]; part.m += ["Snow"] * n; part.uv += [None] * n
    ob = part.build(name, mats, sharp_deg=55)
    col = [hull_object(f"UCX_{name}_00", [(x, y, 0) for (x, y) in out] + [(x * .95, y * .95, thick + 8) for (x, y) in out])]
    return ob, col, [], dict(size_cm=[round(2 * max(abs(x) for x, _ in out)), round(2 * max(abs(y) for _, y in out)), thick + 14],
                             pivot="bottom centre (float it so about a third is under water)")


def snow_mound(name, mats, R, H, seed=1):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=1.0)
    for v in [v for v in bm.verts if v.co.z < -0.05]: bm.verts.remove(v)
    for v in bm.verts: v.co = Vector((v.co.x * R, v.co.y * R * 0.85, max(v.co.z, 0) * H))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    displace(bm, H * 0.10, R * 0.6, seed, mask=lambda v: v.co.z > 1)
    edge = [e for e in bm.edges if e.is_boundary]
    bmesh.ops.edgeloop_fill(bm, edges=edge)                                           # closed bottom
    for v in bm.verts:
        if v.co.z < 0.5: v.co.z = -6.0                                                # sink the skirt into the ground
    ob = bm_object(name, bm, "Snow", mats); finish_mesh(ob, 70)
    pts = [tuple(v.co) for v in ob.data.vertices]
    return ob, [hull_object(f"UCX_{name}_00", pts)], [], dict(size_cm=[2 * R, round(1.7 * R), H], pivot="bottom centre")


def rock(name, mats, R, seed=1, squash=(1.0, 0.8, 0.62)):
    rnd = random.Random(seed)
    bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=4, radius=R)
    off = Vector((seed * 5.1, seed * 2.3, seed * 9.7))
    for v in bm.verts:
        d = v.co.normalized()
        v.co = d * R * (1 + 0.22 * noise.fractal(d * 1.6 + off, 0.6, 2.0, 5))
    planes = [(Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.2, 1))).normalized(), rnd.uniform(0.62, 0.8) * R) for _ in range(5)]
    for v in bm.verts:                                                                # a few flat facets
        for nrm, dist in planes:
            excess = v.co.dot(nrm) - dist
            if excess > 0: v.co -= nrm * excess
    for v in bm.verts: v.co = Vector((v.co.x * squash[0], v.co.y * squash[1], v.co.z * squash[2]))
    zmin = -0.35 * R * squash[2]
    for v in bm.verts: v.co.z = max(v.co.z, zmin)
    for v in bm.verts: v.co.z -= zmin + 6.0                                           # sit 6 cm into the ground
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = bm_object(name, bm, "Rock", mats); finish_mesh(ob, 50)
    pts = [tuple(v.co) for v in ob.data.vertices]
    dims = ob.dimensions
    return ob, [hull_object(f"UCX_{name}_00", pts)], [], dict(size_cm=[round(d) for d in dims], pivot="bottom centre")


def icicles(name, mats, seed=1):
    """Ice ledge with hanging icicles. Pivot at the TOP centre: snap it under an overhang."""
    rnd = random.Random(seed)
    part = Part()
    n = 20; ang = np.linspace(0, 2 * math.pi, n, endpoint=False)
    out = [(70 * math.cos(a) * (1 + 0.1 * math.sin(3 * a + 1)), 32 * math.sin(a)) for a in ang]
    vs = [(x * s, y * s, z) for (s, z) in ((0.95, 0.0), (1.0, -4), (0.97, -14), (0.9, -18)) for (x, y) in out]
    fs = [(i * n + k, i * n + (k + 1) % n, (i + 1) * n + (k + 1) % n, (i + 1) * n + k) for i in range(3) for k in range(n)]
    fs += [tuple(reversed(range(n))), tuple(3 * n + k for k in range(n))]
    part.add(vs, fs, "Ice")
    cols_pts = [[(x, y, z) for (x, y) in out for z in (0, -18)]]
    for i in range(7):
        x, y = rnd.uniform(-55, 55), rnd.uniform(-18, 18)
        r0, L = rnd.uniform(4.5, 9.0), rnd.uniform(28, 95)
        ring, k = 8, 9
        base = len(part.v); bend = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), 0)) * rnd.uniform(0, 4)
        for j in range(k):
            u = j / (k - 1); rr = r0 * (1 - u) ** 1.15 + 0.4 * (1 - u) * (1 + 0.15 * math.sin(9 * u))
            c = Vector((x, y, -14 - L * u)) + bend * u * u
            for q in range(ring):
                a = 2 * math.pi * q / ring
                part.v.append(tuple(c + Vector((rr * math.cos(a), rr * math.sin(a), 0))))
        for j in range(k - 1):
            for q in range(ring):
                a = base + j * ring + q; b_ = base + j * ring + (q + 1) % ring
                part.f.append((a, a + ring, b_ + ring, b_)); part.m.append("Ice"); part.uv.append(None)
        tip = len(part.v); part.v.append((x + bend.x, y + bend.y, -14 - L - 3))
        last = base + (k - 1) * ring
        part.f += [(last + q, tip, last + (q + 1) % ring) for q in range(ring)]; part.m += ["Ice"] * ring; part.uv += [None] * ring
        cols_pts.append([(x + r0 * math.cos(a), y + r0 * math.sin(a), -12) for a in np.linspace(0, 6.28, 6, endpoint=False)] + [(x + bend.x, y + bend.y, -14 - L - 3)])
    ob = part.build(name, mats, sharp_deg=60)
    cols = [hull_object(f"UCX_{name}_{i:02d}", p) for i, p in enumerate(cols_pts)]
    return ob, cols, [], dict(size_cm=[round(d) for d in ob.dimensions], pivot="top centre (hangs down)",
                              note="use the collision as a damage trigger if icicles are a hazard")


def fish(name, mats):
    """Collectible fish, 40 cm long, pivot at its centre (bob and spin it in a Blueprint)."""
    part = Part()
    k, ring = 14, 12
    for j in range(k):
        u = j / (k - 1); x = 20 - 32 * u
        ry = 7.0 * math.sin(math.pi * min(1, u * 1.05)) ** 0.8 * (1 - 0.35 * u) + 0.3
        rz = 9.0 * math.sin(math.pi * min(1, u * 1.05)) ** 0.8 * (1 - 0.25 * u) + 0.3
        for q in range(ring):
            a = 2 * math.pi * q / ring
            part.v.append((x, ry * math.cos(a) * 0.8, rz * math.sin(a)))
    for j in range(k - 1):
        for q in range(ring):
            a = j * ring + q; b_ = j * ring + (q + 1) % ring
            part.f.append((a, b_, b_ + ring, a + ring)); part.m.append("Fish"); part.uv.append(None)
    part.f.append(tuple(range(ring))[::-1]); part.m.append("Fish"); part.uv.append(None)
    part.f.append(tuple((k - 1) * ring + q for q in range(ring))); part.m.append("Fish"); part.uv.append(None)
    def fin(pts, mat="Fish", th=0.8):
        b = len(part.v)
        part.v += [(x, y - th, z) for x, y, z in pts] + [(x, y + th, z) for x, y, z in pts]
        m = len(pts)
        part.f.append(tuple(range(b, b + m))); part.f.append(tuple(range(b + 2 * m - 1, b + m - 1, -1)))
        part.m += [mat, mat]; part.uv += [None, None]
        for q in range(m):
            q2 = (q + 1) % m
            part.f.append((b + q, b + m + q, b + m + q2, b + q2)); part.m.append(mat); part.uv.append(None)
    fin([(-11, 0, 0), (-21, 0, 9), (-18, 0, 0), (-21, 0, -9)])            # tail
    fin([(4, 0, 8), (-4, 0, 13), (-8, 0, 7)])                               # dorsal fin
    for s in (-1, 1):                                                       # eyes: small UV spheres
        c = Vector((14, s * 4.8, 2.5)); rr, rings, seg = 1.6, 5, 10
        top = len(part.v); part.v.append(tuple(c + Vector((0, 0, rr))))
        for j in range(1, rings):
            th = math.pi * j / rings
            for q in range(seg):
                ph = 2 * math.pi * q / seg
                part.v.append(tuple(c + Vector((rr * math.sin(th) * math.cos(ph), rr * math.sin(th) * math.sin(ph) * 0.6, rr * math.cos(th)))))
        bot = len(part.v); part.v.append(tuple(c - Vector((0, 0, rr))))
        ring = lambda j, q: top + 1 + (j - 1) * seg + q % seg
        for q in range(seg):
            part.f.append((top, ring(1, q + 1), ring(1, q))); part.m.append("FishEye"); part.uv.append(None)
            part.f.append((bot, ring(rings - 1, q), ring(rings - 1, q + 1))); part.m.append("FishEye"); part.uv.append(None)
            for j in range(1, rings - 1):
                part.f.append((ring(j, q), ring(j, q + 1), ring(j + 1, q + 1), ring(j + 1, q))); part.m.append("FishEye"); part.uv.append(None)
    ob = part.build(name, mats, sharp_deg=70)
    pts = [tuple(v.co) for v in ob.data.vertices]
    return ob, [hull_object(f"UCX_{name}_00", pts)], [], dict(size_cm=[round(d) for d in ob.dimensions], pivot="centre")


def kit_specs(mats):
    return [
        ("SM_IceBlock_200", lambda: ice_block("SM_IceBlock_200", mats, 200, 200, 200, seed=1)),
        ("SM_IceBlock_100", lambda: ice_block("SM_IceBlock_100", mats, 100, 100, 100, bevel=4, chips=2, seed=2)),
        ("SM_IceSlab_200x200x50", lambda: ice_block("SM_IceSlab_200x200x50", mats, 200, 200, 50, bevel=5, chips=2, seed=3)),
        ("SM_IceBlock_200_SnowCap", lambda: ice_block("SM_IceBlock_200_SnowCap", mats, 200, 200, 200, seed=4, snowcap=True)),
        ("SM_Ramp_Snow_400x200x100", lambda: ramp("SM_Ramp_Snow_400x200x100", mats, 400, 200, 100, "Snow")),
        ("SM_Ramp_Ice_400x200x200", lambda: ramp("SM_Ramp_Ice_400x200x200", mats, 400, 200, 200, "Ice")),
        ("SM_SlideChute_Straight_400", lambda: chute("SM_SlideChute_Straight_400", mats, straight_path(400), 4, "straight")),
        ("SM_SlideChute_CurveLeft_90", lambda: chute("SM_SlideChute_CurveLeft_90", mats, curve_path(400, 1), 16, "90 degree left turn, centre-line radius 400")),
        ("SM_SlideChute_CurveRight_90", lambda: chute("SM_SlideChute_CurveRight_90", mats, curve_path(400, -1), 16, "90 degree right turn, centre-line radius 400")),
        ("SM_SlideChute_Slope_400x100", lambda: chute("SM_SlideChute_Slope_400x100", mats, slope_path(400, 100), 12, "drops 100 over 400, level at both ends")),
        ("SM_SlideChute_Kicker_400", lambda: chute("SM_SlideChute_Kicker_400", mats, kicker_path(400, 200, 25), 12, "jump lip, exits 25 degrees up")),
        ("SM_IceFloe_A", lambda: ice_floe("SM_IceFloe_A", mats, 160, seed=1)),
        ("SM_IceFloe_B", lambda: ice_floe("SM_IceFloe_B", mats, 240, seed=2)),
        ("SM_IceFloe_C", lambda: ice_floe("SM_IceFloe_C", mats, 320, seed=3, n=44)),
        ("SM_SnowMound_A", lambda: snow_mound("SM_SnowMound_A", mats, 120, 45, seed=1)),
        ("SM_SnowMound_B", lambda: snow_mound("SM_SnowMound_B", mats, 200, 80, seed=2)),
        ("SM_Rock_A", lambda: rock("SM_Rock_A", mats, 40, seed=1)),
        ("SM_Rock_B", lambda: rock("SM_Rock_B", mats, 70, seed=2, squash=(1.1, 0.75, 0.7))),
        ("SM_Rock_C", lambda: rock("SM_Rock_C", mats, 120, seed=3, squash=(1.0, 0.9, 0.55))),
        ("SM_Icicles_Cluster", lambda: icicles("SM_Icicles_Cluster", mats, seed=1)),
        ("SM_Fish_Collectible", lambda: fish("SM_Fish_Collectible", mats)),
    ]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def export_fbx(path, objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"MESH", "EMPTY"}, global_scale=1.0, apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_UNITS", axis_forward="X", axis_up="Z", use_space_transform=True,
        bake_space_transform=False, use_mesh_modifiers=True, mesh_smooth_type="FACE", use_tspace=True,
        add_leaf_bones=False, bake_anim=False, path_mode="STRIP", embed_textures=False)


def main():
    a = parse()
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)
    reset()
    tdir = make_textures(out, a.tex_size)
    mats = build_materials(tdir)
    only = set(filter(None, a.only.split(",")))
    stats = {}
    mdir = os.path.join(out, "Meshes"); os.makedirs(mdir, exist_ok=True)
    built = []
    for name, fn in kit_specs(mats):
        if only and name not in only: continue
        ob, cols, socks, info = fn()
        ob.data.calc_loop_triangles()
        info.update(triangles=len(ob.data.loop_triangles), collision_hulls=len(cols), sockets=[s.name for s in socks],
                    materials=[m.name for m in ob.data.materials])
        export_fbx(os.path.join(mdir, name + ".fbx"), [ob] + cols + socks)
        for sk in socks: sk.name = f"{sk.name}__{name}"        # free the plain names for the next piece
        stats[name] = info; built.append((ob, cols, socks))
        print("built", name, info["triangles"], "tris", len(cols), "hulls", flush=True)
    json.dump(stats, open(os.path.join(out, "props_stats.json"), "w"), indent=2)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "Penguin_Kit.blend"))
    print("KIT_DONE", len(stats), flush=True)


if __name__ == "__main__":
    main()
