#!/usr/bin/env python3
"""Preview renders of Kai from Kai.blend: turnaround, face close-up, the modular parts (and, on request, the
facial rig's expressions).

    python3 tools/render_kai.py [kai] [--only turnaround,closeup,parts,faces] [--size 480]

Uses the cel preview shader built into each material (two tones from a fixed light direction, the same model as the
Unreal toon material in the guide) and inverted-hull outlines.
"""
import json, math, os, sys
import bpy, bmesh
import numpy as np
from mathutils import Vector, Matrix, Euler, Quaternion
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kai_geometry as G

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
D = os.path.abspath(argv[0] if argv and not argv[0].startswith("--") else "kai")
ONLY = argv[argv.index("--only") + 1].split(",") if "--only" in argv else ["turnaround", "closeup", "parts"]
SIZE = int(argv[argv.index("--size") + 1]) if "--size" in argv else 480
FRAMES = os.path.join(D, "_previews"); os.makedirs(FRAMES, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "Kai.blend"))
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = 12; sc.cycles.use_denoising = False
sc.view_settings.view_transform = "Standard"
sc.cycles.max_bounces = 0; sc.cycles.transparent_max_bounces = 16
rig = bpy.data.objects["Armature"]; arm = rig.data
PARTS = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("SK_Kai_")]
DEFAULT = [o for o in PARTS if o.users_collection[0].name.startswith("CHARACTER")]


def srgb(*c):
    return tuple((x / 255.0) ** 2.2 for x in c)


# cel shading on, background and camera
for m in bpy.data.materials:
    if not m.use_nodes or "CelPreview" not in m.node_tree.nodes: continue
    nt = m.node_tree; out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    nt.links.new(nt.nodes["CelPreview"].outputs[0], out.inputs["Surface"])
w = bpy.data.worlds.new("Preview sky"); sc.world = w
w.node_tree.nodes["Background"].inputs[0].default_value = (*srgb(176, 216, 238), 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
cam = bpy.data.objects.new("Preview camera", bpy.data.cameras.new("Preview camera")); sc.collection.objects.link(cam)
sc.camera = cam; cam.data.type = "ORTHO"; cam.data.clip_start = 1; cam.data.clip_end = 5000


def outline_material():
    m = bpy.data.materials.new("PREVIEW • outline"); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); geo = nt.nodes.new("ShaderNodeNewGeometry")
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*srgb(44, 28, 24), 1)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geo.outputs["Backfacing"], mix.inputs[0]); nt.links.new(em.outputs[0], mix.inputs[1]); nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    return m


OUTLINE = outline_material()
OUTLINES = {}
for ob in PARTS:
    bm = bmesh.new(); bm.from_mesh(ob.data)
    for layer in list(bm.verts.layers.shape): bm.verts.layers.shape.remove(layer)
    bm.normal_update()
    me = bpy.data.meshes.new(ob.name + "_outline")
    width = 0.2 if "Head" not in ob.name else 0.16
    for v in bm.verts: v.co += v.normal * width
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    me.materials.clear(); me.materials.append(OUTLINE)
    o = bpy.data.objects.new(ob.name + "_outline", me); sc.collection.objects.link(o)
    for g in ob.vertex_groups: o.vertex_groups.new(name=g.name)
    # copy weights
    gi = {g.index: g.name for g in ob.vertex_groups}
    for v in ob.data.vertices:
        for g in v.groups: o.vertex_groups[gi[g.group]].add([v.index], g.weight, "REPLACE")
    o.parent = rig; o.modifiers.new("Armature", "ARMATURE").object = rig
    OUTLINES[ob.name] = o


def show(objs):
    vis = set(o.name for o in objs)
    for ob in PARTS:
        on = ob.name in vis
        ob.hide_render = not on; OUTLINES[ob.name].hide_render = not on


def reset_pose():
    for pb in rig.pose.bones:
        pb.location = (0, 0, 0); pb.rotation_quaternion = (1, 0, 0, 0); pb.scale = (1, 1, 1)
    head = bpy.data.objects["SK_Kai_Head"]
    for kb in head.data.shape_keys.key_blocks[1:]: kb.value = 0.0
    bpy.context.view_layer.update()


def move(name, d=(0, 0, 0), rot=(0, 0, 0)):
    """Move a control bone by d (world cm) and rotate it by rot (world XYZ degrees) about its head."""
    pb = rig.pose.bones[name]; rest = arm.bones[name].matrix_local
    R = Euler([math.radians(a) for a in rot], "XYZ").to_matrix().to_4x4()
    h = rest.translation
    pb.matrix = Matrix.Translation(h + Vector(d)) @ R @ Matrix.Translation(-h) @ rest
    bpy.context.view_layer.update()


def place(name, p, rot=(0, 0, 0)):
    move(name, Vector(p) - arm.bones[name].matrix_local.translation, rot)


def turn(name, x=0, y=0, z=0):
    """Rotate a bone in its own local axes (degrees). Spine, neck, head: +x bends forward."""
    rig.pose.bones[name].rotation_quaternion = Euler((math.radians(x), math.radians(y), math.radians(z)), "XYZ").to_quaternion()
    bpy.context.view_layer.update()


def grip(side, amount=1.0, thumb=0.6):
    for fn in ("index", "middle", "ring", "pinky"):
        for j in range(1, 4): turn(G.bn(f"{fn}_0{j}", side), x=-amount * (55 if j == 1 else 70))
    for j in range(2, 4): turn(G.bn(f"thumb_0{j}", side), x=-thumb * 35)


def face(smile=0, open_=0, shout=0, o=0, frown=0, blink=0, squint=0, brows=0, brow_tilt=0, look=(0, 0)):
    kb = bpy.data.objects["SK_Kai_Head"].data.shape_keys.key_blocks
    kb["Mouth_Smile"].value = smile; kb["Mouth_Open"].value = open_; kb["Mouth_Shout"].value = shout
    kb["Mouth_O"].value = o; kb["Mouth_Frown"].value = frown
    st = json.load(open(os.path.join(D, "source_stats.json")))["lid_close_deg"]
    for side, s in G.SIDES:
        up, lo = st[side]["upper"], st[side]["lower"]
        turn(G.bn("eyelid_upper", side), x=-up * max(blink, squint * 0.45))
        turn(G.bn("eyelid_lower", side), x=lo * squint * 0.9)
        rig.pose.bones[G.bn("brow", side)].location = (0, 0, brows * 0.9)
        turn(G.bn("brow", side), y=brow_tilt * 14 * s)
    place("CTRL_look", arm.bones["CTRL_look"].matrix_local.translation + Vector((look[0] * 30, 0, look[1] * 30)))


def aim(loc, target, scale):
    cam.location = Vector(loc); cam.data.ortho_scale = scale
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()


def shot(path, loc, target, scale, w=SIZE, h=None):
    sc.render.resolution_x = w; sc.render.resolution_y = h or int(w * 1.25)
    aim(loc, target, scale); sc.render.filepath = path; bpy.ops.render.render(write_still=True)
    return path


try:
    FONT = ImageFont.truetype("DejaVuSans.ttf", 20); FONT_B = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
except OSError:
    FONT = FONT_B = ImageFont.load_default()


def sheet(paths, labels, cols, out, title=None):
    ims = [Image.open(p).convert("RGB") for p in paths]
    w, h = ims[0].size; top = 46 if title else 0
    rows = math.ceil(len(ims) / cols)
    S = Image.new("RGB", (cols * w, top + rows * (h + 30)), (246, 244, 240)); dr = ImageDraw.Draw(S)
    if title: dr.text((14, 10), title, fill=(30, 30, 30), font=FONT_B)
    for k, (im, lab) in enumerate(zip(ims, labels)):
        x, y = (k % cols) * w, top + (k // cols) * (h + 30)
        S.paste(im, (x, y)); dr.text((x + 10, y + h + 4), lab, fill=(40, 40, 40), font=FONT)
    S.save(out)


C = G.HEAD_C
FULL = (0, 0, 52)
if "turnaround" in ONLY:
    reset_pose(); show(DEFAULT)
    views = [("Front", (0, -400, 52)), ("Three-quarter", (260, -300, 110)), ("Side", (400, 0, 52)), ("Back", (0, 400, 52)),
             ("Back three-quarter", (-260, 300, 110))]
    paths = [shot(os.path.join(FRAMES, f"turn_{k}.png"), loc, FULL, 118) for k, (n, loc) in enumerate(views)]
    sheet(paths, [n for n, _ in views], 5, os.path.join(D, "Preview_Turnaround.png"))
    paths[1] and Image.open(paths[1]).save(os.path.join(D, "Preview_Hero.png"))

if "closeup" in ONLY:
    reset_pose(); show(DEFAULT)
    paths = [shot(os.path.join(FRAMES, "close_front.png"), (0, -400, C[2] - 2), C + np.array([0, 0, -4.0]), 50, 520, 520),
             shot(os.path.join(FRAMES, "close_3q.png"), (150, -380, C[2] + 4), C + np.array([0, 0, -4.0]), 50, 520, 520),
             shot(os.path.join(FRAMES, "close_side.png"), (400, 0, C[2] - 2), C + np.array([0, 2.0, -4.0]), 50, 520, 520)]
    sheet(paths, ["Face, front", "Face, three-quarter", "Face, side"], 3, os.path.join(D, "Preview_Face.png"))
    feet = [shot(os.path.join(FRAMES, "feet_3q.png"), (90, -160, 40), (0, -5, 4), 34, 520, 360),
            shot(os.path.join(FRAMES, "feet_side.png"), (200, -20, 12), (7, -4, 4), 26, 520, 360),
            shot(os.path.join(FRAMES, "feet_back.png"), (-60, 160, 45), (0, -2, 4), 34, 520, 360)]
    sheet(feet, ["Feet, three-quarter", "Left foot, side", "Feet, from behind"], 3, os.path.join(D, "Preview_Feet.png"))

if "faces" in ONLY:
    reset_pose(); show(DEFAULT)
    exprs = [("Neutral", {}), ("Smile", dict(smile=1, squint=0.25)), ("Happy", dict(smile=1, squint=1.0, brows=0.4)),
             ("Talking", dict(open_=0.8)), ("Effort (jump)", dict(shout=1, brows=0.6, squint=0.3)),
             ("Surprised", dict(o=1, brows=1.0)), ("Blink", dict(blink=1)), ("Determined", dict(frown=1, brow_tilt=-1, brows=-0.4)),
             ("Look left", dict(look=(0.5, 0.05))), ("Look up", dict(look=(0, 0.45), brows=0.3))]
    paths = []
    for k, (n, kw) in enumerate(exprs):
        reset_pose(); face(**kw)
        paths.append(shot(os.path.join(FRAMES, f"face_{k}.png"), (120, -400, C[2] + 1), C + np.array([0, 0, -2.5]), 44, 420, 420))
    sheet(paths, [n for n, _ in exprs], 5, os.path.join(D, "Preview_Expressions.png"))
    reset_pose()

if "parts" in ONLY:
    reset_pose()
    order = ["SK_Kai_Head", "SK_Kai_Hair_Tousled", "SK_Kai_Hair_Spiky", "SK_Kai_Arms", "SK_Kai_Tunic", "SK_Kai_Pants",
             "SK_Kai_Legs", "SK_Kai_Sandals", "SK_Kai_Sash", "SK_Kai_Neckerchief"]
    paths, labels = [], []
    for k, n in enumerate(order):
        ob = bpy.data.objects[n]; show([ob])
        co = np.array([ob.matrix_world @ v.co for v in ob.data.vertices])
        lo, hi = co.min(0), co.max(0); c = (lo + hi) / 2; ext = max(hi - lo) * 1.15 + 4
        paths.append(shot(os.path.join(FRAMES, f"part_{k}.png"), c + np.array([220, -300, 150]), c, ext, 360, 360)); labels.append(n)
    alt = [o for o in DEFAULT if "Hair" not in o.name and "Sash" not in o.name] + [bpy.data.objects["SK_Kai_Hair_Spiky"]]
    show(alt)
    paths.append(shot(os.path.join(FRAMES, "part_alt.png"), (260, -300, 110), FULL, 118, 360, 360)); labels.append("Swapped: spiky hair, no sash")
    sheet(paths, labels, 5, os.path.join(D, "Preview_Parts.png"))
print("RENDER_DONE", flush=True)
