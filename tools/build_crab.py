#!/usr/bin/env python3
"""Build the rigged crab for the penguin game: one skinned mesh, a 36-bone skeleton, a painted texture atlas
(colour, normal map, ORM with baked ambient occlusion), an Unreal FBX and preview renders.

    python3 tools/build_crab.py [--out crab] [--tex 2048] [--no-previews]

Geometry and the rest skeleton come from tools/crab_geometry.py; texture painting from tools/crab_textures.py.
Animations are authored separately by tools/make_crab_anims.py.
"""
import json, math, os, sys
import bpy, bmesh
import numpy as np
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crab_geometry as G
import crab_textures as TX

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
OUT = os.path.abspath(argv[argv.index("--out") + 1]) if "--out" in argv else os.path.abspath("crab")
NTEX = int(argv[argv.index("--tex") + 1]) if "--tex" in argv else 2048
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = "METRIC"; sc.unit_settings.scale_length = 0.01
sc.render.fps = 30
CHAR = bpy.data.collections.new("CHARACTER • export mesh + skeleton"); sc.collection.children.link(CHAR)
STUDIO = bpy.data.collections.new("STUDIO • excluded from FBX"); sc.collection.children.link(STUDIO)

# ---------------------------------------------------------------------------
# Parts -> one mesh with packed UVs
# ---------------------------------------------------------------------------
parts = G.build_parts()
sizes = {}
for p in parts:
    if p.owner:
        for t in set(p.ftile):
            sizes.setdefault(t, p.size)
rects, ppc = TX.pack(sizes, NTEX, pad=int(NTEX / 256))
print("ATLAS", NTEX, "px, texels per cm", round(ppc / 1.0, 2), flush=True)

verts, faces, loop_uv, loop_u, face_mat, face_kind, face_part, vt, vbone = [], [], [], [], [], [], [], [], []
for pi, p in enumerate(parts):
    o = len(verts)
    verts.extend(p.verts.tolist()); vt.extend(p.vt.tolist()); vbone.extend([p.bone] * len(p.verts))
    for f, fu, tile in zip(p.faces, p.fuv, p.ftile):
        u0, v0, u1, v1 = rects[tile]
        faces.append([i + o for i in f])
        loop_uv.extend([(u0 + (u1 - u0) * u, v0 + (v1 - v0) * v) for u, v in fu])
        loop_u.extend([u for u, v in fu])
        face_mat.append(1 if p.mat == "eye" else 0)
        face_kind.append(TX.KIND[TX.kind_of(tile)]); face_part.append(pi)

me = bpy.data.meshes.new("Crab_DeformMesh")
me.from_pydata(verts, [], faces); me.update()
uvl = me.uv_layers.new(name="UVMap")
uvl.data.foreach_set("uv", np.array(loop_uv, np.float32).ravel())
for f, m in zip(me.polygons, face_mat): f.material_index = m
# outward normals per closed part, smooth shading with crisp creases at the teeth and fingertips
bm = bmesh.new(); bm.from_mesh(me)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
for f in bm.faces: f.smooth = True
for e in bm.edges:
    e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(65))
bm.to_mesh(me); bm.free(); me.update()
char = bpy.data.objects.new("SK_Crab", me); CHAR.objects.link(char)
print("MESH", len(me.vertices), "verts", sum(len(p.vertices) - 2 for p in me.polygons), "tris", flush=True)

# ---------------------------------------------------------------------------
# Texture atlas: rasterize the owner parts, paint, relief -> normal map
# ---------------------------------------------------------------------------
me.calc_loop_triangles()
owner = np.array([parts[i].owner for i in face_part])
co = np.array([v.co[:] for v in me.vertices]); vn = np.array([v.normal[:] for v in me.vertices])
vt_a = np.array(vt)
L_uv = np.array(loop_uv); L_u = np.array(loop_u)
tri_uv, tri_attr, tri_kind = [], [], []
loops_v = np.array([l.vertex_index for l in me.loops])
for lt in me.loop_triangles:
    if not owner[lt.polygon_index]: continue
    li = np.array(lt.loops); vi = loops_v[li]
    tri_uv.append(L_uv[li]); tri_kind.append(face_kind[lt.polygon_index])
    tri_attr.append(np.column_stack([co[vi], vn[vi], vt_a[vi], L_u[li]]))
idx, attr, kind, scl = TX.rasterize(np.array(tri_uv), np.array(tri_attr), np.array(tri_kind), NTEX)
print("RASTER", len(idx), "texels", flush=True)

def groove_dist(P):
    x, y = P[:, 0] - G.C[0], P[:, 1] - G.C[1]
    return np.min([G._seg_dist(x, y, a, b) for a, b in G.H_GROOVE], axis=0)

def rim_s(P):
    x, y = P[:, 0] - G.C[0], P[:, 1] - G.C[1]
    th = np.degrees(np.arctan2(y, x))
    return np.hypot(x, y) / G._OUT(G.sym_deg(th))

col, rough, hgt = TX.paint(attr, kind, groove_dist, rim_s)
mask = np.zeros(NTEX * NTEX, bool); mask[idx] = True
def img(vals, ch, fill=0.0):
    a = np.full((NTEX * NTEX, ch), fill, np.float32); a[idx] = vals.reshape(len(idx), ch)
    return TX.dilate(a.reshape(NTEX, NTEX, ch), mask.reshape(NTEX, NTEX), pad=int(NTEX / 64))
COL = img(col, 3); ROUGH = img(rough, 1, 0.5)[..., 0]; HGT = img(hgt, 1)[..., 0]
SU = img(scl[:, 0], 1, 1.0)[..., 0]; SV = img(scl[:, 1], 1, 1.0)[..., 0]
NGL, NDX = TX.normals_from_height(HGT, SU, SV)

from PIL import Image as PI
def save_png(arr, name):
    PI.fromarray((np.flipud(np.clip(arr, 0, 1)) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, name))
save_png(TX.to_srgb(COL), "T_Crab_BaseColor.png")
save_png(NGL, "T_Crab_Normal_GL.png"); save_png(NDX, "T_Crab_Normal_DX.png")

def bl_image(name, path, color=True):
    im = bpy.data.images.load(path); im.name = name
    if not color: im.colorspace_settings.name = "Non-Color"
    return im

# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def principled(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    return m, m.node_tree, m.node_tree.nodes.get("Principled BSDF")
shell, nt, bs = principled("M_Crab_Shell")
tcol = nt.nodes.new("ShaderNodeTexImage"); tcol.image = bl_image("T_Crab_BaseColor", os.path.join(OUT, "T_Crab_BaseColor.png"))
tnrm = nt.nodes.new("ShaderNodeTexImage"); tnrm.image = bl_image("T_Crab_Normal_GL", os.path.join(OUT, "T_Crab_Normal_GL.png"), False)
nmap = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(tcol.outputs["Color"], bs.inputs["Base Color"])
nt.links.new(tnrm.outputs["Color"], nmap.inputs["Color"]); nt.links.new(nmap.outputs["Normal"], bs.inputs["Normal"])
for k, v in (("Coat Weight", 0.08), ("Coat Roughness", 0.2), ("Roughness", 0.5)):
    if k in bs.inputs: bs.inputs[k].default_value = v
shell.diffuse_color = (0.48, 0.034, 0.014, 1)
eye, ent, ebs = principled("M_Crab_Eye")
ebs.inputs["Base Color"].default_value = (0.008, 0.007, 0.008, 1); ebs.inputs["Roughness"].default_value = 0.06
if "Coat Weight" in ebs.inputs: ebs.inputs["Coat Weight"].default_value = 1.0
eye.diffuse_color = (0.01, 0.01, 0.01, 1)
me.materials.append(shell); me.materials.append(eye)

# ---------------------------------------------------------------------------
# Ambient occlusion baked into the atlas, packed with roughness as ORM
# ---------------------------------------------------------------------------
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 48
world = bpy.data.worlds.new("Bake"); sc.world = world; world.use_nodes = True
world.light_settings.distance = 9.0
ao_img = bpy.data.images.new("T_Crab_AO", NTEX, NTEX, alpha=False); ao_img.colorspace_settings.name = "Non-Color"
bake_nodes = []
for m in (shell, eye):
    n = m.node_tree.nodes.new("ShaderNodeTexImage"); n.image = ao_img
    m.node_tree.nodes.active = n; bake_nodes.append((m, n))
bpy.ops.object.select_all(action="DESELECT"); char.select_set(True); bpy.context.view_layer.objects.active = char
bpy.ops.object.bake(type="AO", margin=int(NTEX / 128), use_clear=True)
ao = np.array(ao_img.pixels[:], np.float32).reshape(NTEX, NTEX, 4)[..., 0]
for m, n in bake_nodes: m.node_tree.nodes.remove(n)
bpy.data.images.remove(ao_img)
ao = np.clip(0.18 + 0.82 * ao, 0, 1)
kimg = np.full(NTEX * NTEX, -1, np.int16); kimg[idx] = kind
kimg = TX.dilate(kimg.reshape(NTEX, NTEX, 1).astype(np.float32), mask.reshape(NTEX, NTEX), pad=int(NTEX / 64))[..., 0]
ao[np.isin(np.round(kimg), [TX.KIND["joint"], TX.KIND["joint_hip"], TX.KIND["eyeball"]])] = 1.0   # shared islands: no baked shadow
ORM = np.stack([ao, ROUGH, np.zeros_like(ao)], -1)
save_png(ORM, "T_Crab_ORM.png")
torm = nt.nodes.new("ShaderNodeTexImage"); torm.image = bl_image("T_Crab_ORM", os.path.join(OUT, "T_Crab_ORM.png"), False)
sep = nt.nodes.new("ShaderNodeSeparateColor")
nt.links.new(torm.outputs["Color"], sep.inputs["Color"]); nt.links.new(sep.outputs["Green"], bs.inputs["Roughness"])
print("TEXTURES_DONE", flush=True)

# ---------------------------------------------------------------------------
# Skeleton and rigid skinning (every piece of shell belongs to one bone)
# ---------------------------------------------------------------------------
arm = bpy.data.armatures.new("Crab_Skeleton"); rig = bpy.data.objects.new("Crab_Rig", arm); CHAR.objects.link(rig)
bpy.context.view_layer.objects.active = rig; char.select_set(False); rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
SK = G.skeleton()
for name, h, t, z, parent in SK:
    b = arm.edit_bones.new(name); b.head = Vector(h); b.tail = Vector(t); b.align_roll(Vector(z))
    if parent: b.parent = arm.edit_bones[parent]
    b.use_connect = False
bpy.ops.object.mode_set(mode="OBJECT")
rig.show_in_front = True; arm.display_type = "OCTAHEDRAL"
for name, *_ in SK:
    char.vertex_groups.new(name=name)
groups = {}
for i, b in enumerate(vbone): groups.setdefault(b, []).append(i)
for b, ids in groups.items(): char.vertex_groups[b].add(ids, 1.0, "REPLACE")
char.parent = rig
mod = char.modifiers.new("Deform • Crab_Skeleton", "ARMATURE"); mod.object = rig
for p in rig.pose.bones: p.rotation_mode = "QUATERNION"
for side, s in G.SIDES:                                   # knee tilt per leg, read by the animation solver
    for i in range(1, 5): arm.bones[f"leg{i}_upper.{side}"]["knee_tilt_deg"] = G.LEGS[i - 1]["knee"]
rig["Design"] = "Crab for the penguin game | rigid shell pieces, one bone each | right crusher claw, left cutter"
rig["Units"] = "centimeters; +Z up; crab faces -Y in Blender (its left is +X); FBX converts to +X forward"

# ---------------------------------------------------------------------------
# Export and stats
# ---------------------------------------------------------------------------
def select_character():
    bpy.ops.object.select_all(action="DESELECT"); rig.select_set(True); char.select_set(True)
    bpy.context.view_layer.objects.active = rig
rig.name = "Armature"          # Unreal drops a root node named "Armature" instead of adding an extra bone
select_character()
bpy.ops.export_scene.fbx(
    filepath=os.path.join(OUT, "SK_Crab.fbx"), use_selection=True, object_types={"ARMATURE", "MESH"}, global_scale=1,
    apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS", axis_forward="X", axis_up="Z",
    use_space_transform=True, bake_space_transform=False, add_leaf_bones=False, primary_bone_axis="Y",
    secondary_bone_axis="X", use_armature_deform_only=True, use_mesh_modifiers=True, mesh_smooth_type="FACE",
    use_tspace=True, bake_anim=False, path_mode="COPY", embed_textures=True)

me.calc_loop_triangles()
bad = sum(1 for v in me.vertices if abs(sum(g.weight for g in v.groups) - 1) > 1e-4 or len(v.groups) != 1)
dims = [round(d, 1) for d in char.dimensions]
lo = np.min(co, 0); hi = np.max(co, 0)
stats = dict(vertices=len(me.vertices), triangles=len(me.loop_triangles), bones=len(arm.bones),
             material_slots=[m.name for m in me.materials], uv_layers=len(me.uv_layers), texture_px=NTEX,
             texels_per_cm=round(ppc, 2), max_weight_influences=1, invalid_weight_vertices=bad,
             bounds_cm=dict(min=[round(v, 1) for v in lo], max=[round(v, 1) for v in hi]),
             size_cm=dict(span_x=round(hi[0] - lo[0], 1), length_y=round(hi[1] - lo[1], 1), height=round(hi[2], 1)),
             carapace_cm=dict(width=round(2 * max(G.rim_radius(np.linspace(-90, 90, 721), 1.0)), 1)),
             claws="right: heavy crusher, 32% larger; left: slimmer cutter", fps=30, blender_version=bpy.app.version_string)
json.dump(stats, open(os.path.join(OUT, "source_stats.json"), "w"), indent=2)
print("CRAB_STATS", json.dumps(stats), flush=True)

# ---------------------------------------------------------------------------
# Animator controls (Blender only, never exported): drag a foot target and its leg follows, with a pole
# above each knee. Claws, eyes and the shell are posed by rotating or moving their bones directly.
# ---------------------------------------------------------------------------
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="EDIT")
eb = arm.edit_bones
for side, s in G.SIDES:
    for i in range(1, 5):
        tip, low = eb[f"leg{i}_tip.{side}"], eb[f"leg{i}_lower.{side}"]
        T, Dp, K = tip.tail.copy(), tip.head.copy(), low.head.copy()
        c = eb.new(f"IK_foot{i}.{side}"); c.head = T; c.tail = T + Vector((0, 0, 6)); c.parent = eb["root"]
        d = eb.new(f"IK_tipbase{i}.{side}"); d.head = Dp; d.tail = Dp + (Dp - T).normalized() * 3; d.parent = c
        H = eb[f"leg{i}_upper.{side}"].head.copy(); u = (Dp - H).normalized(); w = ((K - H) - u * (K - H).dot(u)).normalized()
        pole = eb.new(f"POLE_knee{i}.{side}"); pole.head = K + w * 14; pole.tail = pole.head + w * 4
        pole.parent = eb["body"]
        for b in (c, d, pole): b.use_deform = False
bpy.ops.object.mode_set(mode="OBJECT")
deform_coll = arm.collections.new("Deform"); ctrl_coll = arm.collections.new("Controls")
for b in arm.bones:
    (deform_coll if b.use_deform else ctrl_coll).assign(b)
    if not b.use_deform: b.color.palette = "THEME09" if b.name.startswith("IK_foot") else "THEME04"
for side, s in G.SIDES:
    for i in range(1, 5):
        ik = rig.pose.bones[f"leg{i}_lower.{side}"].constraints.new("IK")
        ik.target = rig; ik.subtarget = f"IK_tipbase{i}.{side}"; ik.chain_count = 2
        ik.pole_target = rig; ik.pole_subtarget = f"POLE_knee{i}.{side}"
        dt = rig.pose.bones[f"leg{i}_tip.{side}"].constraints.new("DAMPED_TRACK")
        dt.target = rig; dt.subtarget = f"IK_foot{i}.{side}"; dt.track_axis = "TRACK_Y"
def leg_error(side, i):
    bpy.context.view_layer.update()
    err = 0.0
    for seg in ("upper", "lower", "tip"):
        nm = f"leg{i}_{seg}.{side}"
        a = rig.pose.bones[nm].matrix.to_quaternion(); b = arm.bones[nm].matrix_local.to_quaternion()
        err = max(err, a.rotation_difference(b).angle)
    return math.degrees(min(err, 2 * math.pi - err))
pole_report = {}
for side, s in G.SIDES:
    for i in range(1, 5):
        ik = rig.pose.bones[f"leg{i}_lower.{side}"].constraints["IK"]
        best = min(((leg_error(side, i) if not setattr(ik, "pole_angle", math.radians(a)) else 0), a) for a in range(-180, 180, 5))
        lo_a = best[1]
        for step in (1.0, 0.1, 0.02):                         # refine the pole angle around the best coarse value
            cands = [lo_a + step * k for k in range(-6, 7)]
            best = min(((leg_error(side, i) if not setattr(ik, "pole_angle", math.radians(a)) else 0), a) for a in cands)
            lo_a = best[1]
        ik.pole_angle = math.radians(lo_a)
        pole_report[f"leg{i}.{side}"] = dict(pole_angle_deg=round(lo_a, 2), rest_error_deg=round(leg_error(side, i), 4))
# a moved foot target must carry the foot with it
pb = rig.pose.bones["IK_foot2.L"]; pb.location = (0, 0, 0)
before = rig.pose.bones["leg2_tip.L"].tail.copy()
pb.matrix = Matrix.Translation(Vector((6, -4, 5))) @ pb.matrix; bpy.context.view_layer.update()
follow = (rig.pose.bones["leg2_tip.L"].tail - rig.pose.bones["IK_foot2.L"].head).length
for p in rig.pose.bones: p.location = (0, 0, 0); p.rotation_quaternion = (1, 0, 0, 0)
bpy.context.view_layer.update()
stats["control_rig"] = dict(legs=pole_report, foot_follow_error_cm=round(follow, 4),
                            note="IK_foot*: drag to place a foot; POLE_knee*: knee direction; other bones are FK")
json.dump(stats, open(os.path.join(OUT, "source_stats.json"), "w"), indent=2)
print("CONTROL_RIG", json.dumps(stats["control_rig"]), flush=True)

# ---------------------------------------------------------------------------
# Studio and previews (kept out of the FBX)
# ---------------------------------------------------------------------------
gm = bpy.data.materials.new("STUDIO • sand"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.40, 0.36, 1)
gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
bpy.ops.mesh.primitive_plane_add(size=20000, location=(0, 0, -0.2)); ground = bpy.context.object
ground.name = "Studio floor"; ground.data.materials.append(gm)
for c in list(ground.users_collection): c.objects.unlink(ground)
STUDIO.objects.link(ground)
def track(o, p): o.rotation_euler = (Vector(p) - o.location).to_track_quat("-Z", "Y").to_euler()
def light(name, loc, energy, size, color):
    d = bpy.data.lights.new(name, "AREA"); d.energy = energy; d.shape = "DISK"; d.size = size; d.color = color
    o = bpy.data.objects.new(name, d); STUDIO.objects.link(o); o.location = loc; track(o, (0, -5, 15))
light("Key • warm softbox", (180, -260, 300), 2.2e6, 200, (1, .9, .78))
light("Fill • sky", (-220, -120, 160), 1.1e6, 220, (.8, .88, 1))
light("Rim", (60, 240, 220), 2.0e6, 160, (1, .95, .9))
world.node_tree.nodes["Background"].inputs[0].default_value = (.45, .5, .56, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = .55
camd = bpy.data.cameras.new("Preview camera"); cam = bpy.data.objects.new("Preview camera", camd)
STUDIO.objects.link(cam); sc.camera = cam
camd.type = "ORTHO"; camd.clip_start = 1; camd.clip_end = 100000
sc.cycles.samples = 48; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 800
sc.view_settings.view_transform = "AgX"; sc.render.image_settings.file_format = "PNG"
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "Crab.blend"))
bpy.ops.file.make_paths_relative(); bpy.ops.wm.save_mainfile()          # textures load from next to the .blend
VIEWS = [("Preview_Hero", (150, -220, 140), (0, -6, 12), 125), ("Preview_Front", (0, -300, 60), (0, -6, 18), 120),
         ("Preview_Side", (300, -10, 50), (0, -6, 16), 125), ("Preview_Top", (0, -4, 300), (0, -4, 0), 125),
         ("Preview_Back", (-150, 220, 130), (0, -4, 12), 125)]
if "--no-previews" not in argv:
    for name, loc, tgt, scale in VIEWS:
        cam.location = loc; track(cam, tgt); camd.ortho_scale = scale
        if name == "Preview_Top": cam.rotation_euler = (0, 0, 0)
        sc.render.filepath = os.path.join(OUT, name + ".png"); bpy.ops.render.render(write_still=True)
    from PIL import Image
    ims = [Image.open(os.path.join(OUT, n + ".png")).convert("RGB") for n, *_ in VIEWS[:4]]
    sheet = Image.new("RGB", (1600, 1600))
    for k, im in enumerate(ims): sheet.paste(im, ((k % 2) * 800, (k // 2) * 800))
    sheet.save(os.path.join(OUT, "Preview_Sheet.png"))
print("CRAB_BUILD_COMPLETE", flush=True)
