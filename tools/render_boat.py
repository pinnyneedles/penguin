#!/usr/bin/env python3
"""Preview renders of Kai's boat from Boat.blend, with the same cel preview shader and inverted-hull outlines as
Kai's previews.

    python3 tools/render_boat.py [boat] [--only hero,turnaround,motor,steer,checks] [--size 640]

checks renders back faces in red (should be none) and the collision pieces, for the build's own checks.
"""
import math, os, sys
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector, Euler
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boat_geometry as B

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
D = os.path.abspath(argv[0] if argv and not argv[0].startswith("--") else "boat")
ONLY = argv[argv.index("--only") + 1].split(",") if "--only" in argv else ["hero", "turnaround", "motor", "steer"]
SIZE = int(argv[argv.index("--size") + 1]) if "--size" in argv else 640
FRAMES = os.path.join(D, "_previews"); os.makedirs(FRAMES, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "Boat.blend"))
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = 12; sc.cycles.use_denoising = False
sc.view_settings.view_transform = "Standard"
sc.cycles.max_bounces = 0; sc.cycles.transparent_max_bounces = 16
MESHES = [bpy.data.objects[n] for n in ("SM_Boat_Hull", "SM_Boat_Motor", "SM_Boat_Propeller", "SM_Boat_Wheel")]
HULL, MOTOR, PROP, WHEEL = MESHES
WHEEL_REST = WHEEL.matrix_world.copy()
for o in bpy.data.objects:
    if o.name.startswith(("UCX_", "SOCKET_")): o.hide_render = True


def srgb(*c):
    return tuple((x / 255.0) ** 2.2 for x in c)


for m in bpy.data.materials:
    if not m.use_nodes or "CelPreview" not in m.node_tree.nodes: continue
    nt = m.node_tree; out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    nt.links.new(nt.nodes["CelPreview"].outputs[0], out.inputs["Surface"])
w = bpy.data.worlds.new("Preview sky"); sc.world = w
w.node_tree.nodes["Background"].inputs[0].default_value = (*srgb(176, 216, 238), 1)
cam = bpy.data.objects.new("Preview camera", bpy.data.cameras.new("Preview camera")); sc.collection.objects.link(cam)
sc.camera = cam; cam.data.clip_start = 1; cam.data.clip_end = 8000


def flat_material(name, col, alpha=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*srgb(*col), 1)
    if alpha < 1:
        tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = alpha; nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs[0])
    else:
        nt.links.new(em.outputs[0], out.inputs[0])
    return m


def outline_material():
    m = bpy.data.materials.new("PREVIEW • outline"); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); geo = nt.nodes.new("ShaderNodeNewGeometry")
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*srgb(44, 28, 24), 1)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geo.outputs["Backfacing"], mix.inputs[0]); nt.links.new(em.outputs[0], mix.inputs[1]); nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    return m


OUTLINE = outline_material()
OUTLINES = []
for ob in MESHES:
    bm = bmesh.new(); bm.from_mesh(ob.data); bm.normal_update()
    width = 0.32 if ob is HULL else 0.2 if ob is MOTOR else 0.12
    for v in bm.verts: v.co += v.normal * width
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    me = bpy.data.meshes.new(ob.name + "_outline"); bm.to_mesh(me); bm.free()
    me.materials.clear(); me.materials.append(OUTLINE)
    o = bpy.data.objects.new(ob.name + "_outline", me); sc.collection.objects.link(o)
    o.parent = ob
    OUTLINES.append(o)

water = bpy.data.objects.new("Water", bpy.data.meshes.new("Water")); sc.collection.objects.link(water)
bm = bmesh.new(); bmesh.ops.create_circle(bm, cap_ends=True, radius=2500, segments=64); bm.to_mesh(water.data); bm.free()
water.location = (0, 0, B.WATERLINE); water.data.materials.append(flat_material("PREVIEW • water", (74, 156, 206)))
water.hide_render = True


def aim(loc, target, scale=None, lens=None):
    cam.location = Vector(loc)
    if lens:
        cam.data.type = "PERSP"; cam.data.lens = lens
    else:
        cam.data.type = "ORTHO"; cam.data.ortho_scale = scale
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()


def shot(name, loc, target, scale=None, lens=None, w=SIZE, h=None):
    sc.render.resolution_x = w; sc.render.resolution_y = h or int(w * 0.75)
    aim(loc, target, scale, lens)
    path = os.path.join(FRAMES, name + ".png"); sc.render.filepath = path; bpy.ops.render.render(write_still=True)
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
    return out


def steer(amount):
    """amount -1 (full left) .. 1 (full right): the wheel turns, the outboard swings."""
    MOTOR.rotation_euler = (0, 0, math.radians(B.STEER_MAX * amount))
    WHEEL.matrix_world = WHEEL_REST @ Matrix.Rotation(math.radians(B.WHEEL_MAX * amount), 4, "X")
    bpy.context.view_layer.update()


C = Vector((10, 0, 28))
if "hero" in ONLY:
    water.hide_render = False
    a = shot("hero", (310, -340, 120), (0, 0, 22), lens=50, w=SIZE, h=int(SIZE * 0.7))
    water.hide_render = True
    Image.open(a).save(os.path.join(D, "Preview_Boat_Hero.png"))
if "turnaround" in ONLY:
    views = [("Port side", (8, 600, 30), (8, 0, 30), 300), ("Bow 3/4", (380, 380, 260), C, 290),
             ("Stern 3/4", (-380, -380, 260), C, 290), ("Top", (8, 0, 600), (8, 0, 0), 300),
             ("Bow", (600, 0, 40), (0, 0, 40), 150), ("Stern", (-600, 0, 40), (0, 0, 40), 150)]
    paths = [shot("turn_%d" % k, loc, tgt, scale) for k, (lab, loc, tgt, scale) in enumerate(views)]
    sheet(paths, [v[0] for v in views], 3, os.path.join(D, "Preview_Boat_Turnaround.png"), "Kai's boat")
if "motor" in ONLY:
    t = B.MOTOR_PIVOT + np.array([-4.0, 0, -18.0])
    paths = [shot("motor_0", t + np.array([60, 160, 30]), t, 105, w=480, h=600),
             shot("motor_1", t + np.array([-150, -90, 60]), t, 105, w=480, h=600),
             shot("motor_2", B.PROP_C + np.array([-120, -50, 20]), B.PROP_C, 30, w=480, h=600)]
    sheet(paths, ["Outboard, port", "Outboard, from behind", "Propeller"], 3, os.path.join(D, "Preview_Boat_Motor.png"))
if "steer" in ONLY:
    paths = []
    for k, amount in enumerate((-1, 0, 1)):
        steer(amount)
        paths.append(shot("steer_%d" % k, (-180, 0, 330), (-85, 0, 30), 130, w=420, h=420))
    steer(0)
    sheet(paths, ["Full left", "Straight", "Full right"], 3, os.path.join(D, "Preview_Boat_Steering.png"),
          f"Wheel ±{B.WHEEL_MAX:.0f}°, outboard ±{B.STEER_MAX:.0f}°")
if "checks" in ONLY:
    red, ok = flat_material("CHECK • back", (230, 20, 20)), flat_material("CHECK • front", (200, 200, 200))
    nt = ok.node_tree; out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    geo = nt.nodes.new("ShaderNodeNewGeometry"); mix = nt.nodes.new("ShaderNodeMixShader")
    e1 = nt.nodes["Emission"]; e2 = nt.nodes.new("ShaderNodeEmission"); e2.inputs["Color"].default_value = (1, 0.01, 0.01, 1)
    shade = nt.nodes.new("ShaderNodeVectorMath"); shade.operation = "DOT_PRODUCT"; shade.inputs[1].default_value = (-0.45, -0.62, 0.64)
    nt.links.new(geo.outputs["Normal"], shade.inputs[0])
    ramp = nt.nodes.new("ShaderNodeMapRange"); ramp.inputs[3].default_value = 0.35; nt.links.new(shade.outputs["Value"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], e1.inputs["Strength"])
    nt.links.new(geo.outputs["Backfacing"], mix.inputs[0]); nt.links.new(e1.outputs[0], mix.inputs[1]); nt.links.new(e2.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    for o in OUTLINES: o.hide_render = True
    keep = {o.name: list(o.data.materials) for o in MESHES}
    for o in MESHES: o.data.materials.clear(); o.data.materials.append(ok)
    views = [((380, 380, 260), C, 290), ((-380, -380, 260), C, 290), ((0, 0, 600), (0, 0, 0), 280), ((200, -300, -200), C, 290),
             ((-150, 120, 120), (-110, 0, 40), 110)]
    paths = [shot("check_%d" % k, *v) for k, v in enumerate(views)]
    sheet(paths, ["bow", "stern", "top", "below", "motor"], 3, os.path.join(FRAMES, "Check_Backfaces.png"), "back faces show red")
    for o in MESHES: o.hide_render = True
    ucx = flat_material("CHECK • collision", (60, 200, 120), 0.55)
    for o in bpy.data.objects:
        if o.name.startswith("UCX_"):
            o.hide_render = False; o.display_type = "SOLID"; o.data.materials.clear(); o.data.materials.append(ucx)
    HULL.hide_render = False; HULL.data.materials.clear(); HULL.data.materials.append(flat_material("CHECK • hull", (230, 230, 230), 0.25))
    paths = [shot("ucx_%d" % k, *v) for k, v in enumerate(views[:4])]
    sheet(paths, ["bow", "stern", "top", "below"], 2, os.path.join(FRAMES, "Check_Collision.png"), "collision pieces")
print("RENDER_DONE")
