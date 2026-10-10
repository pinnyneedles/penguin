#!/usr/bin/env python3
"""Build Kai, a modular toon island kid for a platformer: every slot as a skinned mesh on one shared skeleton,
painted colour textures, mouth shape keys, a Blender posing rig, and Unreal FBX files.

    python3 tools/build_kai.py [--out kai] [--draft]

Shapes come from tools/kai_geometry.py and colours from tools/kai_textures.py. Preview renders are made by
tools/render_kai.py from the saved Kai.blend.
"""
import json, math, os, sys, time
import bpy, bmesh
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kai_geometry as G
import kai_textures as TX

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
OUT = os.path.abspath(argv[argv.index("--out") + 1]) if "--out" in argv else os.path.abspath("kai")
DRAFT = "--draft" in argv                      # coarser meshes and smaller textures for quick iteration
os.makedirs(OUT, exist_ok=True)
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


# slot: (export name, marching-cubes spacing (cm), triangle budget, texture size, is part of the default outfit)
SLOTS = {
    "head": ("SK_Kai_Head", 0.22, 7600, 2048, True),          # plus EAR_TRIS for each ear
    "hair_tousled": ("SK_Kai_Hair_Tousled", 0.26, 8000, 1024, True),
    "hair_spiky": ("SK_Kai_Hair_Spiky", 0.26, 8000, 1024, False),
    "arms": ("SK_Kai_Arms", 0.15, 9000, 1024, True),
    "tunic": ("SK_Kai_Tunic", 0.22, 10000, 2048, True),
    "pants": ("SK_Kai_Pants", 0.24, 6000, 1024, True),
    "legs": ("SK_Kai_Legs", 0.18, 3000, 1024, True),
    "sandals": ("SK_Kai_Sandals", 0.12, 9000, 1024, True),
    "sash": ("SK_Kai_Sash", 0.22, 3000, 1024, True),
    "neckerchief": ("SK_Kai_Neckerchief", 0.18, 1600, 512, True),
}
EAR_TRIS = 1500
if DRAFT:
    SLOTS = {k: (n, h * 1.6, b // 2, max(256, t // 2), d) for k, (n, h, b, t, d) in SLOTS.items()}
    EAR_TRIS //= 2

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = "METRIC"; sc.unit_settings.scale_length = 0.01
sc.render.fps = 30
CHAR = bpy.data.collections.new("CHARACTER • exported parts"); sc.collection.children.link(CHAR)
ALT = bpy.data.collections.new("ALTERNATE PARTS • exported, hidden"); sc.collection.children.link(ALT)
PREVIEW = bpy.data.collections.new("PREVIEW • outlines, not exported"); sc.collection.children.link(PREVIEW)


# ---------------------------------------------------------------------------
# Skeleton
# ---------------------------------------------------------------------------
arm = bpy.data.armatures.new("Kai_Skeleton")
rig = bpy.data.objects.new("Armature", arm)       # Unreal drops a root node named "Armature" (no extra bone)
CHAR.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
SK = G.skeleton()
for name, h, t, z, parent, deform in SK:
    b = arm.edit_bones.new(name); b.head = Vector(h); b.tail = Vector(t); b.align_roll(Vector(z))
    if parent: b.parent = arm.edit_bones[parent]
    b.use_connect = False; b.use_deform = True        # every bone is exported (IK goals carry no weights)
bpy.ops.object.mode_set(mode="OBJECT")
rig.show_in_front = True; arm.display_type = "OCTAHEDRAL"
for p in rig.pose.bones: p.rotation_mode = "QUATERNION"
BONES = [b[0] for b in SK]
BODY = [n for n in BONES if not (n.startswith(("eye", "eyelid", "brow", "hair", "sash", "collar", "neckerchief", "ik_")))
        and n != "root"]
log("skeleton", len(BONES), "bones,", len(BODY), "body bones")


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------
def np_mesh(me):
    V = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", V)
    F = [tuple(p.vertices) for p in me.polygons]
    return V.reshape(-1, 3), F


def make_mesh(name, V, F):
    me = bpy.data.meshes.new(name); me.from_pydata(np.asarray(V).tolist(), [], [[int(i) for i in f] for f in F]); me.update()
    return me


def decimated(V, F, target, zone=None, zone_target=0):
    """Blender's collapse decimation down to about `target` triangles. With zone (positions -> bool per vertex), that
    region is decimated on its own to zone_target triangles, so small detail like the ears keeps enough of them."""
    def run(V, F, ratio, mask=None):
        me = make_mesh("tmp", V, F); ob = bpy.data.objects.new("tmp", me); sc.collection.objects.link(ob)
        mod = ob.modifiers.new("dec", "DECIMATE"); mod.ratio = min(1.0, ratio)
        if mask is not None:                     # weight 0 leaves a vertex alone, weight 1 lets it go
            vg = ob.vertex_groups.new(name="dec")
            vg.add(np.flatnonzero(mask).tolist(), 1.0, "REPLACE")
            mod.vertex_group = "dec"
        dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); m2 = ev.to_mesh()
        out = np_mesh(m2)
        ev.to_mesh_clear(); bpy.data.objects.remove(ob); bpy.data.meshes.remove(me)
        return out
    if zone is None:
        return run(V, F, target / max(len(F), 1))
    z = zone(V); Fa = np.asarray(F)
    n_zone = int(z[Fa].all(axis=1).sum())
    V, F = run(V, F, (n_zone + target) / len(F), ~z)              # everything else first
    z = zone(V)
    return run(V, F, (target + zone_target) / len(F), z)          # then the zone


class Piece:
    def __init__(self, V, F, piece, mat, local=None, keys=None, bone=None):
        self.V = np.asarray(V, float); self.F = [tuple(int(i) for i in f) for f in F]
        self.piece = piece; self.mat = mat; self.bone = bone
        self.local = np.zeros((len(self.V), 2)) if local is None else np.asarray(local, float)
        self.keys = keys or {}


def build_pieces(slot):
    name, h, budget, tex, default = SLOTS[slot]
    fn = G.PARTS[slot][0]
    V, F = G.polygonize(fn, G.part_box(slot), h)
    n_mc = len(F)
    if slot == "head":
        V, F = decimated(V, F, budget, lambda P: np.any([G.ear_zone(P, s) < 1.0 for _, s in G.SIDES], axis=0), 2 * EAR_TRIS)
    else:
        V, F = decimated(V, F, budget)
    log(slot, "marching cubes", n_mc, "->", len(F), "faces")
    pieces = [Piece(V, F, TX.PIECES["body"], 0)]
    if slot == "head":
        for side, s in G.SIDES:
            E = G.eye_pieces(side)
            pieces.append(Piece(*E["sclera"][:2], TX.PIECES["sclera"], 1, E["sclera"][2], bone="head"))
            pieces.append(Piece(*E["iris"][:2], TX.PIECES["iris"], 1, E["iris"][2], bone=G.bn("eye", side)))
            pieces.append(Piece(*E["lid_upper"][:2], TX.PIECES["lid_upper"], 0, E["lid_upper"][2], bone=G.bn("eyelid_upper", side)))
            pieces.append(Piece(*E["lid_lower"][:2], TX.PIECES["lid_lower"], 0, E["lid_lower"][2], bone=G.bn("eyelid_lower", side)))
            bv, bf, bl = G.brow_piece(side)
            pieces.append(Piece(bv, bf, TX.PIECES["brow"], 0, bl, bone=G.bn("brow", side)))
        mv, mf, ml, mk = G.mouth_piece()
        pieces.append(Piece(mv, mf, TX.PIECES["mouth"], 1, ml, keys=mk, bone="head"))
    return pieces


def assemble(slot, pieces, coll):
    """One mesh object for the slot: pieces joined, a 'piece' face attribute and a 'Local' UV layer for painting."""
    V, F, piece_f, mat_f, local, offs = [], [], [], [], [], []
    o = 0
    for p in pieces:
        offs.append(o)
        V.append(p.V); local.append(p.local)
        F.extend([tuple(i + o for i in f) for f in p.F]); piece_f += [p.piece] * len(p.F); mat_f += [p.mat] * len(p.F)
        o += len(p.V)
    V = np.vstack(V); local = np.vstack(local)
    me = make_mesh(SLOTS[slot][0], V, F)
    me.attributes.new("piece", "INT", "FACE").data.foreach_set("value", np.array(piece_f, np.int32))
    me.polygons.foreach_set("material_index", np.array(mat_f, np.int32))
    loops_v = np.empty(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", loops_v)
    uv = me.uv_layers.new(name="UVMap"); loc = me.uv_layers.new(name="Local")
    loc.data.foreach_set("uv", local[loops_v].astype(np.float32).ravel())
    me.uv_layers.active = uv
    bm = bmesh.new(); bm.from_mesh(me)
    for f in bm.faces: f.smooth = True
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(SLOTS[slot][0], me); coll.objects.link(ob)
    return ob, offs


# fixed layout of the face-features texture (material 1 of the head): piece -> (centre u, centre v, scale u, scale v)
FACE_UV = {TX.PIECES["iris"]: (0.25, 0.75, 0.235, 0.235), TX.PIECES["sclera"]: (0.75, 0.75, 0.19, 0.19),
           TX.PIECES["mouth"]: (0.5, 0.06, 0.47, 0.38)}


def unwrap(ob, nmats):
    """Material 0: Blender's smart UV project. Material 1 (eyes and mouth): a fixed layout from the pieces' own
    coordinates, so irises and mouth shapes get plenty of texels and stay crisp when the mouth opens."""
    me = ob.data
    bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    mats = np.empty(len(me.polygons), np.int32); me.polygons.foreach_get("material_index", mats)
    me.polygons.foreach_set("select", (mats == 0))
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.006, area_weight=0.0, correct_aspect=True,
                             scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    if nmats > 1:
        pc = np.empty(len(me.polygons), np.int32); me.attributes["piece"].data.foreach_get("value", pc)
        lp = np.empty(len(me.loops), np.int64); me.polygons.foreach_get("loop_start", lp[:0]) if False else None
        loop_poly = np.repeat(np.arange(len(me.polygons)), [p.loop_total for p in me.polygons])
        lc = np.empty(len(me.loops) * 2); me.uv_layers["Local"].data.foreach_get("uv", lc); lc = lc.reshape(-1, 2)
        uv = np.empty(len(me.loops) * 2); me.uv_layers["UVMap"].data.foreach_get("uv", uv); uv = uv.reshape(-1, 2)
        for piece, (cu, cv, su, sv) in FACE_UV.items():
            m = pc[loop_poly] == piece
            uv[m, 0] = cu + lc[m, 0] * su; uv[m, 1] = cv + lc[m, 1] * sv
        me.uv_layers["UVMap"].data.foreach_set("uv", uv.ravel())


def paint(ob, slot):
    """Bake each material's colour texture from the painters; returns {material index: image path}."""
    me = ob.data; me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    tl = np.empty(nt * 3, np.int64); me.loop_triangles.foreach_get("loops", tl); tl = tl.reshape(-1, 3)
    tv = np.empty(nt * 3, np.int64); me.loop_triangles.foreach_get("vertices", tv); tv = tv.reshape(-1, 3)
    tp = np.empty(nt, np.int64); me.loop_triangles.foreach_get("polygon_index", tp)
    tm = np.empty(nt, np.int64); me.loop_triangles.foreach_get("material_index", tm)
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    vn = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("normal", vn); vn = vn.reshape(-1, 3)
    uv = np.empty(len(me.loops) * 2); me.uv_layers["UVMap"].data.foreach_get("uv", uv); uv = uv.reshape(-1, 2)
    lc = np.empty(len(me.loops) * 2); me.uv_layers["Local"].data.foreach_get("uv", lc); lc = lc.reshape(-1, 2)
    pc = np.empty(len(me.polygons), np.int32); me.attributes["piece"].data.foreach_get("value", pc)
    out = {}
    specs = [(0, slot, SLOTS[slot][3])] + ([(1, "eye", 1024 if not DRAFT else 512)] if slot == "head" else [])
    for mi, painter, size in specs:
        s = tm == mi
        attr = np.concatenate([co[tv[s]], vn[tv[s]], np.repeat(pc[tp[s]][:, None, None], 3, 1).astype(float), lc[tl[s]]], axis=2)
        img = TX.bake(uv[tl[s]], attr, size, TX.PAINTERS[painter])
        tname = "T_Kai_Eye_BaseColor" if painter == "eye" else "T_" + SLOTS[slot][0][3:] + "_BaseColor"
        path = os.path.join(OUT, tname + ".png"); Image.fromarray(img).save(path)
        out[mi] = (tname, path)
    return out


LDIR = (-0.45, -0.62, 0.64)
SHADE = (0.62, 0.56, 0.70)


def material(name, tex_path):
    """Principled BSDF with the colour texture (what the FBX carries), plus an unconnected cel shader that
    render_kai.py switches on for previews: two tones from a fixed light direction, like the Unreal toon material."""
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; bs = nt.nodes["Principled BSDF"]
    img = bpy.data.images.load(tex_path); img.name = os.path.splitext(os.path.basename(tex_path))[0]
    tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = img; tx.name = "BaseColor"
    nt.links.new(tx.outputs["Color"], bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = 0.9
    if "Specular IOR Level" in bs.inputs: bs.inputs["Specular IOR Level"].default_value = 0.1
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dot = nt.nodes.new("ShaderNodeVectorMath"); dot.operation = "DOT_PRODUCT"; dot.inputs[1].default_value = LDIR
    nt.links.new(geo.outputs["Normal"], dot.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs[1].default_value = -0.03; mr.inputs[2].default_value = 0.03
    nt.links.new(dot.outputs["Value"], mr.inputs[0])
    mul = nt.nodes.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"; mul.inputs[0].default_value = 1.0
    rg = [i for i in mul.inputs if i.type == "RGBA"]; nt.links.new(tx.outputs["Color"], rg[0]); rg[1].default_value = (*SHADE, 1)
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    mg = [i for i in mix.inputs if i.type == "RGBA"]
    nt.links.new(mr.outputs[0], mix.inputs[0]); nt.links.new([o for o in mul.outputs if o.type == "RGBA"][0], mg[0])
    nt.links.new(tx.outputs["Color"], mg[1])
    em = nt.nodes.new("ShaderNodeEmission"); em.name = "CelPreview"
    nt.links.new([o for o in mix.outputs if o.type == "RGBA"][0], em.inputs[0])
    return m


# ---------------------------------------------------------------------------
# Build every slot
# ---------------------------------------------------------------------------
PARTS, OFFS, PIECES = {}, {}, {}
for slot, (name, h, budget, tex, default) in SLOTS.items():
    pieces = build_pieces(slot)
    ob, offs = assemble(slot, pieces, CHAR if default else ALT)
    if slot == "head":                           # toon shading normals for the ears and eye domes (see G)
        me = ob.data; Pv = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", Pv); Pv = Pv.reshape(-1, 3)
        Nv = np.empty(len(me.vertices) * 3); me.vertex_normals.foreach_get("vector", Nv); Nv = Nv.reshape(-1, 3)
        nb = len(pieces[0].V)
        Nv[:nb] = G.eye_dome_normals(Pv[:nb], G.ear_normals(Pv[:nb], Nv[:nb]))
        me.normals_split_custom_set_from_vertices(Nv.tolist())
    nm = 2 if slot == "head" else 1
    unwrap(ob, nm)
    texs = paint(ob, slot)
    for mi in range(nm):
        mname = "M_Kai_Eye" if (slot == "head" and mi == 1) else "M_" + name[3:]
        ob.data.materials.append(material(mname, texs[mi][1]))
    PARTS[slot] = ob; OFFS[slot] = offs; PIECES[slot] = pieces
    log(slot, len(ob.data.vertices), "verts", sum(len(p.vertices) - 2 for p in ob.data.polygons), "tris")


# ---------------------------------------------------------------------------
# Skin weights: a smooth proxy body takes Blender's automatic (bone heat) weights for the body bones, and every
# part copies them from the nearest point on the proxy, so stacked layers (skin, sleeve, collar) move together.
# Face, hair, sash, collar and neckerchief bones are weighted directly.
# ---------------------------------------------------------------------------
def proxy_sdf(P):
    d = G.head_base_sdf(P)
    d = np.minimum(d, G.tunic_sdf(P))
    d = np.minimum(d, G.arms_sdf(P))
    d = np.minimum(d, G.pants_sdf(P))
    d = np.minimum(d, G.legs_sdf(P))
    d = np.minimum(d, np.minimum(G.foot_skin_sdf(P, 1.0), G.foot_skin_sdf(P, -1.0)))
    return d


V, F = G.polygonize(proxy_sdf, ((-40, 40), (-17, 14), (-1, G.HEAD_C[2] + 19)), 0.55 if not DRAFT else 0.8)
V, F = decimated(V, F, 40000 if not DRAFT else 16000)
proxy = bpy.data.objects.new("PROXY_weights", make_mesh("PROXY_weights", V, F)); sc.collection.objects.link(proxy)
for b in arm.bones: b.use_deform = b.name in BODY
bpy.ops.object.select_all(action="DESELECT"); proxy.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
for b in arm.bones: b.use_deform = True
gi = {g.index: g.name for g in proxy.vertex_groups}
PW = np.zeros((len(proxy.data.vertices), len(BONES)))
bidx = {n: i for i, n in enumerate(BONES)}
for v in proxy.data.vertices:
    for g in v.groups:
        if gi[g.group] in bidx: PW[v.index, bidx[gi[g.group]]] = g.weight
missing = (PW.sum(1) < 1e-6).sum()
log("proxy weights:", len(proxy.data.vertices), "verts,", missing, "without weights")
bm = bmesh.new(); bm.from_mesh(proxy.data); bmesh.ops.triangulate(bm, faces=bm.faces)
bm.faces.ensure_lookup_table()
TRI = np.array([[v.index for v in f.verts] for f in bm.faces])
BVH = BVHTree.FromBMesh(bm)
PV = np.array([v.co[:] for v in proxy.data.vertices])
bm.free()


def transfer(V, src=None):
    """Weights at points V interpolated from the nearest triangle of the proxy (or of src = (bvh, verts, tris, W))."""
    bvh, pv, tri, pw = src if src else (BVH, PV, TRI, PW)
    W = np.zeros((len(V), len(BONES)))
    for i, p in enumerate(V):
        loc, nor, fi, dist = bvh.find_nearest(Vector(p))
        a, b, c = pv[tri[fi]]
        v0, v1, v2 = b - a, c - a, np.array(loc) - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1; d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-12: w = np.array([1 / 3, 1 / 3, 1 / 3])
        else:
            wb = (d11 * d20 - d01 * d21) / den; wc = (d00 * d21 - d01 * d20) / den
            w = np.clip(np.array([1 - wb - wc, wb, wc]), 0, 1); w /= w.sum()
        W[i] = w @ pw[tri[fi]]
    return W


def mesh_source(ob, W):
    """A weight source (for transfer) from a skinned part's own surface."""
    bm = bmesh.new(); bm.from_mesh(ob.data); bmesh.ops.triangulate(bm, faces=bm.faces); bm.faces.ensure_lookup_table()
    tri = np.array([[v.index for v in f.verts] for f in bm.faces]); bvh = BVHTree.FromBMesh(bm)
    pv = np.array([v.co[:] for v in ob.data.vertices]); bm.free()
    return bvh, pv, tri, W


def chain_weights(P, pts, bones, radius):
    """Weights along a chain of segments (pts[i] -> pts[i+1] belongs to bones[i]); returns (W_chain, influence)."""
    pts = np.asarray(pts)
    n = len(bones)
    best = np.full(len(P), np.inf); seg = np.zeros(len(P), int); tpar = np.zeros(len(P))
    for i in range(n):
        a, b = pts[i], pts[i + 1]; ab = b - a
        t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
        d = np.linalg.norm(P - (a + np.outer(t, ab)), axis=1)
        m = d < best; best[m] = d[m]; seg[m] = i; tpar[m] = t[m]
    W = np.zeros((len(P), len(BONES)))
    for i in range(n):
        m = seg == i
        # blend into the next bone over the last 30% of each segment
        nxt = min(i + 1, n - 1)
        k = np.clip((tpar[m] - 0.7) / 0.3, 0, 1) * 0.5 if nxt != i else np.zeros(m.sum())
        W[m, bidx[bones[i]]] += 1 - k; W[m, bidx[bones[nxt]]] += k
    return W, best < radius


def clump_bone(root, tip):
    phi, el = root
    if el >= 70: return "hair_top"
    if abs(phi) <= 45: return "hair_front"
    if abs(phi) <= 105: return G.bn("hair_side", "L" if phi > 0 else "R")
    return "hair_back_01"


def hair_weights(P, style):
    """The scalp follows the head; each clump bends from its root toward its tip with its hair bone."""
    W = np.zeros((len(P), len(BONES))); W[:, bidx["head"]] = 1.0
    best = np.full(len(P), np.inf); which = np.full(len(P), -1); tval = np.zeros(len(P))
    for k, (root, tip, w, lift) in enumerate(style["clumps"]):
        pts = np.array(G.clump_points(root, tip, lift)); n = len(pts) - 1
        for i in range(n):
            a, b = pts[i], pts[i + 1]; ab = b - a
            t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
            dist = np.linalg.norm(P - (a + np.outer(t, ab)), axis=1)
            m = dist < best; best[m] = dist[m]; which[m] = k; tval[m] = (i + t[m]) / n
    for k, (root, tip, w, lift) in enumerate(style["clumps"]):
        bone = clump_bone(root, tip)
        m = (which == k) & (best < w + 1.5)
        wt = np.clip((tval[m] - 0.15) / 0.6, 0, 1)
        if bone == "hair_back_01":
            w2 = np.clip((tval[m] - 0.55) / 0.45, 0, 1)
            W[m, bidx["head"]] = 1 - wt; W[m, bidx["hair_back_01"]] = wt * (1 - w2); W[m, bidx["hair_back_02"]] = wt * w2
        else:
            W[m, bidx["head"]] = 1 - wt; W[m, bidx[bone]] = wt
    return W


def limit(W, k=4, floor=0.01):
    W = np.where(W < floor, 0, W)
    if W.shape[1] > k:
        idx = np.argsort(-W, axis=1)[:, k:]
        np.put_along_axis(W, idx, 0.0, axis=1)
    s = W.sum(1, keepdims=True); s[s == 0] = 1
    return W / s


def slot_weights(slot):
    ob = PARTS[slot]; P = np.array([v.co[:] for v in ob.data.vertices])
    pieces, offs = PIECES[slot], OFFS[slot]
    if slot.startswith("hair"):
        return limit(hair_weights(P, G.TOUSLED if slot == "hair_tousled" else G.SPIKY))
    W = transfer(P)
    if slot == "head":
        body = slice(0, len(pieces[0].V))
        hi = P[body, 2] > G.Z["neck"] + 6.5                          # the whole head above the jaw is rigid
        Wb = W[body]; Wb[hi] = 0; Wb[hi, bidx["head"]] = 1.0; W[body] = Wb
        for p, o in zip(pieces[1:], offs[1:]):
            W[o:o + len(p.V)] = 0; W[o:o + len(p.V), bidx[p.bone]] = 1.0
    if slot == "tunic":
        # the shirt itself follows the spine and pelvis, not the thighs (bone heat lets them reach up to the waist)
        tl, tr, pel = bidx[G.bn("thigh", "L")], bidx[G.bn("thigh", "R")], bidx["pelvis"]
        W[:, pel] += W[:, tl] + W[:, tr]; W[:, tl] = 0; W[:, tr] = 0
        # the skirt hands over to the thighs below the hips, so it lifts, swings back and steps out with them
        t = np.clip((39.5 - P[:, 2]) / (39.5 - (G.HEM_Z + 1.0)), 0, 1)
        f = t * t * (3 - 2 * t) * 0.95                                # none at the waist, nearly all at the hem
        # the front and sides rest on the thighs as they lift or step out; the back mostly hangs from the pelvis,
        # since lifting moves the thighs away from it (following fully would swing it into the seat)
        f *= 0.3 + 0.7 * np.clip((6.0 - P[:, 1]) / 4.0, 0, 1)
        left = np.clip(0.5 + P[:, 0] / 10.0, 0, 1)                    # left thigh on the left, both in the middle
        W *= (1 - f)[:, None]; W[:, tl] += f * left; W[:, tr] += f * (1 - left)
    if slot == "tunic":                                               # the back of the sailor collar flaps
        zs = G.Z["shoulder"]
        flap = (P[:, 1] > 2.0) & (P[:, 2] < zs - 2.0) & (np.abs(G.collar_sdf(P)) < 0.35)
        w = np.clip((zs - 2.0 - P[flap, 2]) / 5.0, 0, 1) * 0.9
        W[flap] *= (1 - w)[:, None]; W[flap, bidx["collar_back"]] += w
    if slot == "neckerchief":
        c = np.array([0, -8.2, G.Z["chest"] + 1.1])
        tail = (P[:, 2] < c[2] - 1.2) & (P[:, 1] < -6.0)
        w = np.clip((c[2] - 1.2 - P[tail, 2]) / 3.5, 0, 1) * 0.85
        W[tail] *= (1 - w)[:, None]; W[tail, bidx["neckerchief"]] += w
    if slot == "sash":                        # rides on the shirt under it, so it moves with the skirt
        W = transfer(P, mesh_source(PARTS["tunic"], SLOT_W["tunic"]))
        for tail, (pts, wd) in zip("ab", G.sash_tail_points()):
            bones = [f"sash_{tail}_0{j + 1}" for j in range(3)]
            Wc, near = chain_weights(P, pts, bones, 2.6)
            near &= P[:, 2] < pts[0][2] + 0.4
            k = np.clip((G.Z["hip"] - P[near, 2]) / 4.0, 0, 1) * 0.35       # a share for physics flutter, below the hip
            W[near] = W[near] * (1 - k)[:, None] + Wc[near] * k[:, None]
    return limit(W)


def skin(ob, W):
    for i, name in enumerate(BONES):
        ids = np.nonzero(W[:, i] > 0)[0]
        if len(ids) == 0: continue
        g = ob.vertex_groups.new(name=name)
        for vi in ids: g.add([int(vi)], float(W[vi, i]), "REPLACE")
    ob.parent = rig
    ob.modifiers.new("Armature", "ARMATURE").object = rig


SLOT_W = {}
for slot, ob in PARTS.items():
    W = SLOT_W[slot] = slot_weights(slot)
    skin(ob, W)
    log("skinned", slot, "bones used:", int((W.sum(0) > 0).sum()))
bpy.data.objects.remove(proxy)

# mouth expressions as shape keys
head = PARTS["head"]; mp = PIECES["head"][-1]; mo = OFFS["head"][-1]
head.shape_key_add(name="Basis", from_mix=False)
for key, V in mp.keys.items():
    sk = head.shape_key_add(name=key, from_mix=False)
    co = np.empty(len(head.data.vertices) * 3); sk.data.foreach_get("co", co); co = co.reshape(-1, 3)
    co[mo:mo + len(V)] = V
    sk.data.foreach_set("co", co.ravel())
log("shape keys", [k.name for k in head.data.shape_keys.key_blocks])

# drop the painting-only data before export
for ob in PARTS.values():
    me = ob.data
    if "Local" in me.uv_layers: me.uv_layers.remove(me.uv_layers["Local"])
    if "piece" in me.attributes: me.attributes.remove(me.attributes["piece"])


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def export_fbx(path, meshes):
    bpy.ops.object.select_all(action="DESELECT"); rig.select_set(True)
    for m in meshes: m.hide_set(False); m.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, global_scale=1,
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS", axis_forward="X", axis_up="Z",
        use_space_transform=True, bake_space_transform=False, add_leaf_bones=False, primary_bone_axis="Y",
        secondary_bone_axis="X", use_armature_deform_only=True, use_mesh_modifiers=False, mesh_smooth_type="FACE",
        use_tspace=True, bake_anim=False, path_mode="COPY", embed_textures=True)


for slot, ob in PARTS.items():
    export_fbx(os.path.join(OUT, SLOTS[slot][0] + ".fbx"), [ob])
# the default outfit as one skeletal mesh, for a quick start
copies = []
for slot, ob in PARTS.items():
    if not SLOTS[slot][4]: continue
    c = ob.copy(); c.data = ob.data.copy(); CHAR.objects.link(c); copies.append(c)
bpy.ops.object.select_all(action="DESELECT")
for c in copies: c.select_set(True)
bpy.context.view_layer.objects.active = copies[0]
bpy.ops.object.join()
merged = bpy.context.object; merged.name = "SK_Kai"; merged.data.name = "SK_Kai"
export_fbx(os.path.join(OUT, "SK_Kai.fbx"), [merged])
merged.hide_set(True); merged.hide_render = True
for ob in PARTS.values():
    if not SLOTS[[k for k, v in PARTS.items() if v is ob][0]][4]: ob.hide_set(True); ob.hide_render = True
log("exported", len(PARTS) + 1, "FBX files")


# ---------------------------------------------------------------------------
# Posing rig (Blender only, not exported): IK controls for hands and feet with knee and elbow poles, and a
# look-at target for the eyes. Spine, neck, head, fingers, face and secondary bones are posed by rotation.
# ---------------------------------------------------------------------------
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="EDIT")
eb = arm.edit_bones
ctrl = {}
for side, s in G.SIDES:
    H, K, A, Bl, T = G.leg_points(s)
    c = eb.new(G.bn("CTRL_foot", side)); c.head = eb[G.bn("foot", side)].head; c.tail = eb[G.bn("foot", side)].tail
    c.roll = eb[G.bn("foot", side)].roll; c.parent = eb["root"]
    p = eb.new(G.bn("CTRL_knee", side)); p.head = Vector(K + np.array([0, -18.0, 0])); p.tail = p.head + Vector((0, -3, 0)); p.parent = eb["root"]
    S, E, W, d2 = G.arm_points(s)
    c = eb.new(G.bn("CTRL_hand", side)); c.head = eb[G.bn("hand", side)].head; c.tail = eb[G.bn("hand", side)].tail
    c.roll = eb[G.bn("hand", side)].roll; c.parent = eb["root"]
    p = eb.new(G.bn("CTRL_elbow", side)); p.head = Vector(E + np.array([0, 16.0, 0])); p.tail = p.head + Vector((0, 3, 0)); p.parent = eb["root"]
look = eb.new("CTRL_look"); look.head = Vector(G.HEAD_C + np.array([0, -60.0, -3.4])); look.tail = look.head + Vector((0, -4, 0))
look.parent = eb["head"]
for side, s in G.SIDES:                                   # one target per eye, straight down its axis, moved together
    e = G.face_layout()["eyes"][side]
    t = eb.new(G.bn("CTRL_look", side)); t.head = Vector(e["pivot"] + e["n"] * 62.0); t.tail = t.head + Vector(e["n"] * 3.0)
    t.parent = look
for n in [b.name for b in eb if b.name.startswith("CTRL_")]: eb[n].use_deform = False
bpy.ops.object.mode_set(mode="OBJECT")
for b in arm.bones:
    if b.name.startswith("CTRL_"): rig.pose.bones[b.name].rotation_mode = "QUATERNION"
coll_c = arm.collections.new("Controls (Blender only)"); coll_d = arm.collections.new("Deform"); coll_h = arm.collections.new("Helpers and secondary")
for b in arm.bones:
    if b.name.startswith("CTRL_"): coll_c.assign(b); b.color.palette = "THEME09"
    elif b.name.startswith(("ik_", "eye", "eyelid", "brow", "hair", "sash", "collar", "neckerchief")) or b.name == "root": coll_h.assign(b)
    else: coll_d.assign(b)
for side, s in G.SIDES:
    pb = rig.pose.bones
    ik = pb[G.bn("calf", side)].constraints.new("IK"); ik.target = rig; ik.subtarget = G.bn("CTRL_foot", side); ik.chain_count = 2
    ik.pole_target = rig; ik.pole_subtarget = G.bn("CTRL_knee", side)
    cr = pb[G.bn("foot", side)].constraints.new("COPY_ROTATION"); cr.target = rig; cr.subtarget = G.bn("CTRL_foot", side)
    ik = pb[G.bn("lowerarm", side)].constraints.new("IK"); ik.target = rig; ik.subtarget = G.bn("CTRL_hand", side); ik.chain_count = 2
    ik.pole_target = rig; ik.pole_subtarget = G.bn("CTRL_elbow", side)
    cr = pb[G.bn("hand", side)].constraints.new("COPY_ROTATION"); cr.target = rig; cr.subtarget = G.bn("CTRL_hand", side)
    dt = pb[G.bn("eye", side)].constraints.new("DAMPED_TRACK"); dt.target = rig; dt.subtarget = G.bn("CTRL_look", side); dt.track_axis = "TRACK_Y"


def chain_error(names):
    bpy.context.view_layer.update()
    err = 0.0
    for nm in names:
        a = rig.pose.bones[nm].matrix.to_quaternion(); b = arm.bones[nm].matrix_local.to_quaternion()
        e = a.rotation_difference(b).angle; err = max(err, min(e, 2 * math.pi - e))
    return math.degrees(err)


poles = {}
for side, s in G.SIDES:
    for chain, bone in ((["thigh", "calf"], "calf"), (["upperarm", "lowerarm"], "lowerarm")):
        names = [G.bn(n, side) for n in chain]
        ik = rig.pose.bones[G.bn(bone, side)].constraints["IK"]
        def err_at(a): ik.pole_angle = math.radians(a); return chain_error(names)
        best = min((err_at(a), a) for a in range(-180, 180, 5))[1]
        for step in (1.0, 0.1, 0.02):
            best = min((err_at(best + step * k), best + step * k) for k in range(-6, 7))[1]
        ik.pole_angle = math.radians(best)
        poles[G.bn(bone, side)] = dict(pole_angle_deg=round(best, 2), rest_error_deg=round(err_at(best), 4))
# the look target sits straight ahead of the eyes, so the eyes keep their rest aim
log("posing rig poles", poles)

# ---------------------------------------------------------------------------
# Stats and save
# ---------------------------------------------------------------------------
stats = dict(name="Kai", height_cm=None, bones=len(BONES), exported_bones=len(BONES), fps=30, units="cm",
             parts={}, shape_keys=[k.name for k in head.data.shape_keys.key_blocks[1:]],
             lid_close_deg={side: dict(upper=round(math.degrees(G.lid_close_angle(side, "upper")), 1),
                                       lower=round(math.degrees(G.lid_close_angle(side, "lower")), 1)) for side in "LR"},
             posing_rig=poles)
zmax = -1e9
for slot, ob in PARTS.items():
    me = ob.data; me.calc_loop_triangles()
    co = np.array([v.co[:] for v in me.vertices]); zmax = max(zmax, co[:, 2].max()) if SLOTS[slot][4] else zmax
    stats["parts"][SLOTS[slot][0]] = dict(slot=slot, default_outfit=SLOTS[slot][4], vertices=len(me.vertices),
                                          triangles=len(me.loop_triangles), materials=[m.name for m in me.materials],
                                          bones_weighted=len(ob.vertex_groups),
                                          max_influences=max(len(v.groups) for v in me.vertices))
stats["height_cm"] = round(float(zmax), 1)
stats["default_outfit_triangles"] = sum(p["triangles"] for p in stats["parts"].values() if p["default_outfit"])
json.dump(stats, open(os.path.join(OUT, "source_stats.json"), "w"), indent=2)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "Kai.blend"))
bpy.ops.file.make_paths_relative(); bpy.ops.wm.save_mainfile()
log("KAI_BUILD_COMPLETE", json.dumps({k: v for k, v in stats.items() if k != "parts"}))
