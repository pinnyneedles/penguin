#!/usr/bin/env python3
"""Build Kai's boat for Unreal: SM_Boat_Hull, SM_Boat_Motor and SM_Boat_Propeller with painted colour textures, toon
preview materials, simple convex collision (UCX_) and sockets (SOCKET_) for the Blueprint.

    python3 tools/build_boat.py [--out boat] [--draft]

Frames: the hull's origin is on the centreline at the bottom of the keel amidships; the motor's origin is on its
steering axis (rotate it about Z to steer); the propeller's origin is its hub (spin it about X). The bow points
along +X, which Unreal imports as the actor's forward axis.
"""
import json, math, os, sys, time
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector
from PIL import Image
from scipy.spatial import ConvexHull

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kai_geometry as KG
import kai_textures as TX
import boat_geometry as B
import boat_textures as BT

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
OUT = os.path.abspath(argv[argv.index("--out") + 1]) if "--out" in argv else os.path.abspath("boat")
DRAFT = "--draft" in argv
os.makedirs(OUT, exist_ok=True)
T0 = time.time()

# mesh: (marching-cubes spacing (cm), triangle budget, texture size)
SPEC = {"SM_Boat_Hull": (None, None, 2048), "SM_Boat_Motor": (0.3, 6000, 1024), "SM_Boat_Propeller": (0.12, 1600, 256),
        "SM_Boat_Wheel": (0.1, 2400, 512)}
if DRAFT:
    SPEC = {k: (h and h * 1.6, n and n // 2, max(256, t // 2)) for k, (h, n, t) in SPEC.items()}


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = "METRIC"; sc.unit_settings.scale_length = 0.01
BOAT = bpy.data.collections.new("BOAT • exported meshes"); sc.collection.children.link(BOAT)
COLL = bpy.data.collections.new("COLLISION • UCX, exported with each mesh"); sc.collection.children.link(COLL)
SOCK = bpy.data.collections.new("SOCKETS • exported with each mesh"); sc.collection.children.link(SOCK)


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------
def make_mesh(name, V, F):
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(V).tolist(), [], [[int(i) for i in f] for f in F]); me.update()
    return me


def np_mesh(me):
    V = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", V)
    return V.reshape(-1, 3), [tuple(p.vertices) for p in me.polygons]


def decimated(V, F, target):
    """Blender's collapse decimation down to about `target` triangles."""
    me = make_mesh("tmp", V, F); ob = bpy.data.objects.new("tmp", me); sc.collection.objects.link(ob)
    ob.modifiers.new("dec", "DECIMATE").ratio = min(1.0, target / max(len(F), 1))
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg); m2 = ev.to_mesh()
    out = np_mesh(m2)
    ev.to_mesh_clear(); bpy.data.objects.remove(ob); bpy.data.meshes.remove(me)
    return out


def mesh_object(name, V, F, piece, sharp_deg):
    """One object with a 'piece' face attribute (what part of the boat a face belongs to). Faces are smooth, with
    hard edges where neighbouring faces meet at more than sharp_deg (plank edges, box corners)."""
    me = make_mesh(name, V, F)
    me.attributes.new("piece", "INT", "FACE").data.foreach_set("value", np.asarray(piece, np.int32))
    me.uv_layers.new(name="UVMap")
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(sharp_deg))
    ob = bpy.data.objects.new(name, me); BOAT.objects.link(ob)
    return ob


def unwrap(ob):
    bpy.ops.object.select_all(action="DESELECT"); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(55), island_margin=0.004, area_weight=0.0, correct_aspect=True,
                             scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def paint(ob, painter, size, offset=(0, 0, 0)):
    """Bake the colour texture: each texel is coloured from its 3D position (boat frame), face normal and piece."""
    me = ob.data; me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    tl = np.empty(nt * 3, np.int64); me.loop_triangles.foreach_get("loops", tl); tl = tl.reshape(-1, 3)
    tv = np.empty(nt * 3, np.int64); me.loop_triangles.foreach_get("vertices", tv); tv = tv.reshape(-1, 3)
    tp = np.empty(nt, np.int64); me.loop_triangles.foreach_get("polygon_index", tp)
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3) + np.asarray(offset)
    fn = np.empty(len(me.polygons) * 3); me.polygons.foreach_get("normal", fn); fn = fn.reshape(-1, 3)
    uv = np.empty(len(me.loops) * 2); me.uv_layers["UVMap"].data.foreach_get("uv", uv); uv = uv.reshape(-1, 2)
    pc = np.empty(len(me.polygons), np.int32); me.attributes["piece"].data.foreach_get("value", pc)
    attr = np.concatenate([co[tv], np.repeat(fn[tp][:, None, :], 3, 1), np.repeat(pc[tp][:, None, None], 3, 1).astype(float),
                           np.zeros((nt, 3, 2))], axis=2)
    img = TX.bake(uv[tl], attr, size, painter)
    tname = "T_" + ob.name[3:] + "_BaseColor"
    path = os.path.join(OUT, tname + ".png"); Image.fromarray(img).save(path)
    return path


LDIR = (-0.45, -0.62, 0.64)
SHADE = (0.62, 0.56, 0.70)


def material(name, tex_path):
    """Principled BSDF with the colour texture (what the FBX carries), plus the same unconnected cel shader as Kai's
    materials (build_kai.material) that render_boat.py switches on for previews."""
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


def finish(ob, painter, size, offset=(0, 0, 0)):
    unwrap(ob)
    ob.data.materials.append(material("M_" + ob.name[3:], paint(ob, painter, size, offset)))
    log(ob.name, len(ob.data.vertices), "verts", sum(len(p.vertices) - 2 for p in ob.data.polygons), "tris")


# ---------------------------------------------------------------------------
# The three meshes
# ---------------------------------------------------------------------------
V, F, piece = [], [], []
o = 0
pieces = [(m.name,) + m.arrays() for m in B.hull_pieces()]
for name, sdf, box, h, budget in (("clamp", B.clamp_sdf, B.CLAMP_BOX, 0.2, 2400), ("bow", B.bow_sdf, B.BOW_BOX, 0.12, 1400),
                                  ("console", B.console_sdf, B.CONSOLE_BOX, 0.22, 4000)):
    v, f = KG.polygonize(sdf, box, h * (1.4 if DRAFT else 1)); n_mc = len(f)
    v, f = decimated(v, f, budget // (2 if DRAFT else 1))
    log(name, "marching cubes", n_mc, "->", len(f), "faces")
    pieces.append((name, B.rake(v) if name == "bow" else v, f))
for name, v, f in pieces:
    V.append(v); F += [[i + o for i in face] for face in f]; piece += [BT.PID[name]] * len(f); o += len(v)
hull = mesh_object("SM_Boat_Hull", np.vstack(V), F, piece, 40)
finish(hull, BT.paint_hull, SPEC["SM_Boat_Hull"][2])

h, budget, size = SPEC["SM_Boat_Motor"]
V, F = KG.polygonize(B.motor_sdf, B.MOTOR_BOX, h); n_mc = len(F)
V, F = decimated(V, F, budget)
log("motor marching cubes", n_mc, "->", len(F), "faces")
motor = mesh_object("SM_Boat_Motor", V - B.MOTOR_PIVOT, F, np.zeros(len(F)), 50)
motor.location = Vector(B.MOTOR_PIVOT)
finish(motor, BT.paint_motor, size, B.MOTOR_PIVOT)

h, budget, size = SPEC["SM_Boat_Propeller"]
V, F = KG.polygonize(B.prop_sdf, B.PROP_BOX, h); n_mc = len(F)
V, F = decimated(V, F, budget)
log("propeller marching cubes", n_mc, "->", len(F), "faces")
prop = mesh_object("SM_Boat_Propeller", V - B.PROP_C, F, np.zeros(len(F)), 50)
prop.parent = motor; prop.location = Vector(B.PROP_C - B.MOTOR_PIVOT)
finish(prop, BT.paint_prop, size, B.PROP_C)

h, budget, size = SPEC["SM_Boat_Wheel"]
V, F = KG.polygonize(B.wheel_sdf, B.WHEEL_BOX, h); n_mc = len(F)
V, F = decimated(V, F, budget)
log("wheel marching cubes", n_mc, "->", len(F), "faces")
wheel = mesh_object("SM_Boat_Wheel", V, F, np.zeros(len(F)), 50)
wheel.matrix_world = Matrix.Translation(Vector(B.WHEEL_C)) @ Matrix(B.WHEEL_FRAME.tolist()).to_4x4()
finish(wheel, BT.paint_wheel, size)


# ---------------------------------------------------------------------------
# Moving parts must clear: the outboard at full lock each way against the hull and its clamp, and the propeller
# through a full turn against the outboard
# ---------------------------------------------------------------------------
from mathutils.bvhtree import BVHTree


def bvh(ob):
    M = ob.matrix_world
    return BVHTree.FromPolygons([M @ v.co for v in ob.data.vertices], [tuple(p.vertices) for p in ob.data.polygons])


CLEARANCE = {}
hull_tree = bvh(hull)
hull_piece = np.empty(len(hull.data.polygons), np.int32); hull.data.attributes["piece"].data.foreach_get("value", hull_piece)
for yaw in (-B.STEER_MAX, 0.0, B.STEER_MAX):
    motor.rotation_euler = (0, 0, math.radians(yaw)); bpy.context.view_layer.update()
    ov = bvh(motor).overlap(hull_tree)
    CLEARANCE[f"motor_vs_hull_yaw_{yaw:+.0f}"] = len(ov)
    if ov:
        Mw = motor.matrix_world
        cen = np.array([(Mw @ motor.data.polygons[i].center)[:] for i, j in ov])
        where = {BT.PIECES[int(k)]: int(n) for k, n in zip(*np.unique(hull_piece[[j for i, j in ov]], return_counts=True))}
        log("  motor overlaps at yaw", yaw, where, "z", np.round(cen[:, 2].min(), 1), "..", np.round(cen[:, 2].max(), 1),
            "x", np.round(cen[:, 0].min(), 1), "..", np.round(cen[:, 0].max(), 1))
motor.rotation_euler = (0, 0, 0); bpy.context.view_layer.update()
motor_tree = bvh(motor)
spin = 0
for a in range(0, 120, 5):
    prop.rotation_euler = (math.radians(a), 0, 0); bpy.context.view_layer.update()
    ov = bvh(prop).overlap(motor_tree)
    if len(ov) > spin:
        cen = np.array([(motor.matrix_world @ motor.data.polygons[j].center)[:] for i, j in ov])
        log("  propeller overlaps at", a, "deg: motor faces x", np.round(cen[:, 0].min(), 1), "..", np.round(cen[:, 0].max(), 1),
            "z", np.round(cen[:, 2].min(), 1), "..", np.round(cen[:, 2].max(), 1))
    spin = max(spin, len(ov))
prop.rotation_euler = (0, 0, 0); bpy.context.view_layer.update()
CLEARANCE["propeller_vs_motor_spinning"] = spin
log("clearance", CLEARANCE)
if any(CLEARANCE.values()) and not DRAFT:
    sys.exit(f"moving parts collide: {CLEARANCE}")


# ---------------------------------------------------------------------------
# Collision: a few convex pieces so Kai can walk on the floorboards inside the boat
# ---------------------------------------------------------------------------
def support_points(P, n=64):
    """The extreme points of P in n directions spread over the sphere: a light convex hull inside the full one."""
    k = np.arange(n) + 0.5
    z = 1 - 2 * k / n; r = np.sqrt(1 - z * z); a = np.pi * (3 - np.sqrt(5)) * k
    dirs = np.stack([r * np.cos(a), r * np.sin(a), z], -1)
    return P[np.unique(np.argmax(P @ dirs.T, axis=0))]


def ucx(owner, k, pts, origin=(0, 0, 0), max_verts=48):
    """A convex collision piece (UCX_<mesh>_<k>): the convex hull of the points (qhull's triangles, wound outward),
    kept to about max_verts corners so the physics stays cheap."""
    P = np.unique(np.round(np.asarray(pts, float) - np.asarray(origin), 3), axis=0)
    hull_ = ConvexHull(P)
    if len(hull_.vertices) > max_verts:
        P = support_points(P[hull_.vertices], 2 * max_verts)
        hull_ = ConvexHull(P)
    used = np.unique(hull_.simplices); remap = {int(v): i for i, v in enumerate(used)}
    c = P[used].mean(0)
    F = []
    for tri in hull_.simplices:
        a, b, cc = P[tri]
        F.append([remap[int(i)] for i in (tri if np.cross(b - a, cc - a) @ (a - c) > 0 else tri[::-1])])
    me = make_mesh(f"UCX_{owner.name}_{k:02d}", P[used], F)
    ob = bpy.data.objects.new(me.name, me); COLL.objects.link(ob)
    ob.parent = owner; ob.display_type = "WIRE"; ob.hide_render = True
    return ob


def section_band(x, z0, z1, inner, n=24):
    """Points of one side of the hull section at station x between heights z0 and z1, both sides (port, starboard)."""
    phis = np.linspace(0, np.pi / 2, 400)
    S = B.section(np.full_like(phis, x), phis, inner=inner)
    zz = np.linspace(z0, z1, n)
    y = np.interp(zz, S[:, 2], S[:, 1])
    return np.stack([np.full_like(zz, x), y, zz], -1)


def hull_collision():
    xb = B.XS + B.U_BULK * (B.XB - B.XS)
    out = []
    # bottom: from the keel up to the top of the floorboards, in four lengths
    edges = np.linspace(B.XS, B.floor_end(), 5)
    for a, b in zip(edges[:-1], edges[1:]):
        pts = []
        for x in (a, b):
            phis = np.linspace(0, np.pi / 2, 60)
            S = B.section(np.full_like(phis, x), phis)
            S = S[S[:, 2] <= B.FLOOR_Z]
            pts += [S, B.mirror(S), section_band(x, B.FLOOR_Z, B.FLOOR_Z, False, 1),
                    B.mirror(section_band(x, B.FLOOR_Z, B.FLOOR_Z, False, 1))]
        out.append(np.vstack(pts))
    # the bow under the foredeck, solid, and the rising bottom between the floorboards and the bulkhead
    xs = np.linspace(xb, B.XB, 12)
    pts = [B.section(np.full(30, x), np.linspace(0, np.pi / 2, 30)) for x in xs]
    pts += [B.mirror(p) for p in pts]
    out.append(np.vstack(pts))
    xs = np.linspace(B.floor_end() - 1.0, xb, 6)
    pts = [B.section(np.full(30, x), np.linspace(0, np.pi / 2, 30), inner=True) for x in xs]
    pts = [p[p[:, 2] <= B.FLOOR_Z + 6] for p in pts]
    pts += [B.section(np.full(30, x), np.linspace(0, np.pi / 2, 30))[:12] for x in xs]
    pts += [B.mirror(p) for p in pts]
    out.append(np.vstack(pts))
    # side walls, six lengths a side, from the floorboards to the gunwale (including the rub rail)
    edges = np.linspace(B.XS, xb, 7)
    for a, b in zip(edges[:-1], edges[1:]):
        pts = []
        for x in (a, b):
            z0 = max(B.FLOOR_Z, float(B.keel_z(x)) + B.T)
            zs = float(B.sheer_z(x))
            o_ = section_band(x, z0, zs, False); i_ = section_band(x, z0, zs, True)
            rail = np.array([[x, float(B.gunwale_w(x)) + 3.5, zs - 1.6]])
            pts += [o_, i_, rail]
        P = np.vstack(pts)
        out += [P, B.mirror(P)]
    # transom, and the motor pad on top of it
    ring = B._ring(B.XS, False)
    out.append(np.vstack([ring, ring + np.array([B.T, 0, 0]), *[c for c in B.motor_pad().arrays()[:1]]]))
    # the helm console
    c = B.CONSOLE
    out.append(np.array([[x, y, z] for x in (c["x0"], c["x1"]) for y in (-c["half_w"], c["half_w"])
                         for z in (B.FLOOR_Z, c["top_back"] + (c["top_front"] - c["top_back"]) * (x - c["x0"]) / (c["x1"] - c["x0"]))]))
    # seats
    for x0, x1, top in B.SEAT.values():
        out.append(B.fitted_plank(x0, x1, top - B.SEAT_T, top, 0.1)[0])
    return out


for k, pts in enumerate(hull_collision()):
    ucx(hull, k, B.rake(pts))
# outboard: the cowl and the leg (not the tiller, which sits in the driver's hand), so traces and the shore find it
MV = np.array([v.co[:] for v in motor.data.vertices]) + B.MOTOR_PIVOT
part = B.motor_part(MV)
head = (part <= 1) & (MV[:, 0] < B.MOTOR_PIVOT[0] + 5.0)
ucx(motor, 0, MV[head], B.MOTOR_PIVOT)
ucx(motor, 1, MV[part == 2], B.MOTOR_PIVOT)
log("collision", len(COLL.objects), "convex pieces")


# ---------------------------------------------------------------------------
# Sockets
# ---------------------------------------------------------------------------
def socket(owner, name, loc, fwd, up, origin):
    e = bpy.data.objects.new("SOCKET_" + name, None); SOCK.objects.link(e)
    e.empty_display_type = "ARROWS"; e.empty_display_size = 8
    f = Vector(fwd).normalized(); u = Vector(up).normalized(); l = u.cross(f)
    R = Matrix((f, l, u)).transposed().to_4x4()
    e.parent = owner
    e.matrix_parent_inverse = Matrix.Identity(4)
    e.matrix_basis = Matrix.Translation(Vector(np.asarray(loc) - np.asarray(origin))) @ R
    return e


for n, (loc, f, u) in B.sockets().items():
    socket(hull, n, loc, f, u, (0, 0, 0))
for n, (loc, f, u) in B.motor_sockets().items():
    socket(motor, n, loc, f, u, B.MOTOR_PIVOT)
log("sockets", len(SOCK.objects))


# ---------------------------------------------------------------------------
# Export: each mesh at the world origin with its own collision and sockets
# ---------------------------------------------------------------------------
def export_fbx(ob):
    keep_parent, keep_matrix = ob.parent, ob.matrix_world.copy()
    ob.parent = None; ob.matrix_world = Matrix.Identity(4)
    kids = [c for c in ob.children if c.name.startswith(("UCX_", "SOCKET_"))]
    bpy.ops.object.select_all(action="DESELECT")
    for o in [ob] + kids: o.hide_set(False); o.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.context.view_layer.update()
    bpy.ops.export_scene.fbx(
        filepath=os.path.join(OUT, ob.name + ".fbx"), use_selection=True, object_types={"MESH", "EMPTY"}, global_scale=1,
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS", axis_forward="X", axis_up="Z",
        use_space_transform=True, bake_space_transform=False, use_mesh_modifiers=False, mesh_smooth_type="FACE",
        use_tspace=True, bake_anim=False, path_mode="COPY", embed_textures=True)
    ob.parent = keep_parent
    ob.matrix_world = keep_matrix
    bpy.context.view_layer.update()


for ob in (hull, motor, prop, wheel):
    export_fbx(ob)
for o in list(COLL.objects): o.hide_set(True)
log("exported", 4, "FBX files")

stats = dict(
    meshes={ob.name: dict(vertices=len(ob.data.vertices), triangles=sum(len(p.vertices) - 2 for p in ob.data.polygons),
                          texture=f"T_{ob.name[3:]}_BaseColor", texture_size=SPEC[ob.name][2],
                          collision=[c.name for c in ob.children if c.name.startswith("UCX_")],
                          sockets=[c.name[7:] for c in ob.children if c.name.startswith("SOCKET_")]) for ob in (hull, motor, prop, wheel)},
    length_cm=round(B.XB - B.XS + 1.6, 1), beam_cm=round(2 * (float(B.gunwale_w(np.linspace(B.XS, B.XB, 400)).max()) + 3.5), 1),
    motor_pivot_cm=B.MOTOR_PIVOT.tolist(), propeller_cm=B.PROP_C.tolist(), steer_max_deg=B.STEER_MAX,
    wheel_cm=B.WHEEL_C.tolist(), wheel_max_deg=B.WHEEL_MAX,
    waterline_cm=B.WATERLINE, floor_cm=B.FLOOR_Z, kai_root_cm=B.KAI_ROOT.tolist(), moving_part_overlaps=CLEARANCE)
json.dump(stats, open(os.path.join(OUT, "source_stats.json"), "w"), indent=2)
for img in bpy.data.images:
    if img.filepath: img.filepath = "//" + os.path.basename(img.filepath)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "Boat.blend"), relative_remap=False)
log("saved", os.path.join(OUT, "Boat.blend"))
