#!/usr/bin/env python3
"""Preview renders for the penguin level kit: a thumbnail per prop and a small level vignette with
the chick for scale. Reads Penguin_Kit.blend written by tools/make_props.py.

    python3 tools/render_props.py props/Kit [--chick pebble/Pebble_Chick/Pebble_Chick_Anims.blend] [--samples 32] [--keep-thumbs]
"""
import json, math, os, sys
import bpy
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
KIT = os.path.abspath(argv[0])
CHICK = argv[argv.index("--chick") + 1] if "--chick" in argv else "pebble/Pebble_Chick/Pebble_Chick_Anims.blend"
SAMPLES = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 32
PREV = os.path.join(KIT, "Previews"); os.makedirs(PREV, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=os.path.join(KIT, "Penguin_Kit.blend"))
sc = bpy.context.scene
props = sorted([o for o in sc.objects if o.type == "MESH" and o.name.startswith("SM_")], key=lambda o: o.name)
helpers = [o for o in sc.objects if o.name.startswith("UCX_") or o.type == "EMPTY"]
for o in helpers: o.hide_render = True; o.hide_viewport = True

# studio: soft sky, key, fill, rim, pale ground
world = bpy.data.worlds.new("Sky"); sc.world = world; world.use_nodes = True
bg = world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.62, 0.72, 0.85, 1); bg.inputs[1].default_value = 0.8
def light(name, loc, energy, size, color):
    d = bpy.data.lights.new(name, "AREA"); d.energy = energy; d.size = size; d.color = color
    o = bpy.data.objects.new(name, d); sc.collection.objects.link(o); o.location = loc; return o
lights = [light("Key", (500, -600, 900), 9e6, 500, (1, .95, .9)), light("Fill", (-700, -300, 400), 3e6, 600, (.8, .88, 1)),
          light("Rim", (-200, 800, 600), 5e6, 400, (1, 1, 1))]
gm = bpy.data.materials.new("Ground"); gm.use_nodes = True
gbase = gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"]
gbase.default_value = (0.20, 0.24, 0.30, 1)                           # darker floor so snow props read in thumbnails
gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
bpy.ops.mesh.primitive_plane_add(size=40000, location=(0, 0, -0.5)); ground = bpy.context.object; ground.data.materials.append(gm)
cd = bpy.data.cameras.new("Cam"); cd.lens = 50; cd.clip_start = 5; cd.clip_end = 100000
cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam); sc.camera = cam
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.render.image_settings.file_format = "PNG"; sc.view_settings.view_transform = "AgX"

def aim(loc, target):
    cam.location = Vector(loc); cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()

def bbox(o):
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi

# ---- thumbnails: each prop alone, framed by its bounding sphere -----------------------------------
sc.render.resolution_x = sc.render.resolution_y = 420
home = {o.name: o.matrix_world.copy() for o in props}
for o in props: o.hide_render = True
thumbs = []
for o in props:
    o.hide_render = False
    lo, hi = bbox(o); r = max((hi - lo).length / 2, 30)
    hang = o.name.startswith("SM_Icicles")
    lift = 250 if hang else max(0.0, -lo.z)                          # hang icicles; stand sloped pieces on the floor
    o.location.z += lift; bpy.context.view_layer.update()
    lo, hi = bbox(o); c = (lo + hi) / 2
    d = r / math.tan(math.radians(18)) * 1.15
    aim(c + Vector((0.62, -0.72, 0.42)).normalized() * d, c)
    sc.render.filepath = os.path.join(PREV, f"thumb_{o.name}.png"); bpy.ops.render.render(write_still=True)
    thumbs.append(sc.render.filepath); o.hide_render = True
    o.location.z -= lift; bpy.context.view_layer.update()
    print("thumb", o.name, flush=True)

from PIL import Image, ImageDraw
stats = json.load(open(os.path.join(KIT, "props_stats.json")))
cols = 6; tw = 300; th = 330
sheet = Image.new("RGB", (cols * tw, math.ceil(len(thumbs) / cols) * th), (244, 244, 242)); dr = ImageDraw.Draw(sheet)
for i, (o, p) in enumerate(zip(props, thumbs)):
    x, y = (i % cols) * tw, (i // cols) * th
    sheet.paste(Image.open(p).convert("RGB").resize((tw - 10, tw - 10)), (x + 5, y + 5))
    s = stats.get(o.name, {})
    size = "x".join(str(int(v)) for v in s.get("size_cm", [])) if s.get("size_cm") else s.get("kind", "")
    dr.text((x + 8, y + tw - 2), o.name.replace("SM_", ""), fill=(20, 20, 20))
    dr.text((x + 8, y + tw + 12), f"{size}  {s.get('triangles', '')} tris", fill=(90, 90, 90))
sheet.save(os.path.join(PREV, "Kit_Sheet.png"))
if "--keep-thumbs" not in argv:                                       # the sheet carries them; keep the repo light
    for p in thumbs: os.remove(p)

# ---- vignette: a little level built from the kit, with the chick for scale -----------------------
gbase.default_value = (0.78, 0.82, 0.88, 1)                           # snowfield for the vignette
for o in props: o.hide_render = False; o.matrix_world = Matrix.Translation((0, 0, -100000))   # park everything
bpy.context.view_layer.update()
def place(name, loc, rot_z=0.0):
    src = bpy.data.objects[name]
    ob = src.copy(); ob.data = src.data; sc.collection.objects.link(ob)
    ob.matrix_world = Matrix.Translation(loc) @ Matrix.Rotation(math.radians(rot_z), 4, "Z"); return ob
def socket_local(name, which):
    for ch in bpy.data.objects[name].children:
        if ch.name.startswith(which): return ch.matrix_parent_inverse @ ch.matrix_basis   # pure data, no stale depsgraph
    raise KeyError(which)
# slide track: straight -> right curve -> slope -> straight -> kicker, chained through the sockets
M = Matrix.Translation((-1500, 750, 100))
track = ["SM_SlideChute_Straight_400", "SM_SlideChute_CurveRight_90", "SM_SlideChute_Slope_400x100",
         "SM_SlideChute_Straight_400", "SM_SlideChute_Kicker_400"]
for nm in track:
    ob = bpy.data.objects[nm].copy(); ob.data = bpy.data.objects[nm].data; sc.collection.objects.link(ob)
    ob.matrix_world = M
    M = M @ socket_local(nm, "SOCKET_End")
# the track starts on a tower of ice blocks
for x in (-1450, -1350, -1250, -1150):
    place("SM_IceBlock_100", (x, 750, -25))                          # the first straight rests on a row of blocks
place("SM_Ramp_Snow_400x200x100", (-1900, 750, -25))
# a ledge with icicles, blocks, a snow-capped block and the fish
place("SM_IceBlock_200", (400, 500, 0)); place("SM_IceBlock_200_SnowCap", (400, 500, 200))
place("SM_IceBlock_100", (200, 650, 0)); place("SM_IceSlab_200x200x50", (650, 500, 200))
place("SM_IceBlock_200", (850, 500, 0))
place("SM_Icicles_Cluster", (650, 410, 200), 0)
place("SM_Fish_Collectible", (-50, 150, 60), 30)
place("SM_Ramp_Ice_400x200x200", (100, 500, 0), 180)
# scenery
place("SM_SnowMound_B", (-300, 900, 0)); place("SM_SnowMound_A", (900, -200, 0), 40)
place("SM_Rock_C", (1200, 700, 0), 20); place("SM_Rock_B", (-600, 600, 0), 70); place("SM_Rock_A", (150, -50, 0), 10)
# water with floes
wm = bpy.data.materials.new("Water"); wm.use_nodes = True
wb = wm.node_tree.nodes["Principled BSDF"]; wb.inputs["Base Color"].default_value = (0.02, 0.08, 0.14, 1); wb.inputs["Roughness"].default_value = 0.05
bpy.ops.mesh.primitive_plane_add(size=1, location=(200, 2100, 2)); water = bpy.context.object; water.scale = (5000, 1800, 1); water.data.materials.append(wm)
place("SM_IceFloe_C", (-400, 1700, -25)); place("SM_IceFloe_B", (500, 1900, -25), 40); place("SM_IceFloe_A", (1200, 1600, -25), 80)
# the chick, idle, standing in front for scale
try:
    with bpy.data.libraries.load(os.path.abspath(CHICK), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in ("Armature", "SK_Pebble_Chick")]
        dst.actions = [n for n in src.actions if n == "Chick_Idle"]
    for o in dst.objects: sc.collection.objects.link(o)
    rig = bpy.data.objects["Armature"]; rig.location = (-150, -250, 0); rig.rotation_euler = (0, 0, 0)   # faces -Y: three-quarter front for this camera, looking toward the track
    rig.animation_data_create(); act = bpy.data.actions["Chick_Idle"]; rig.animation_data.action = act
    if hasattr(act, "slots") and act.slots: rig.animation_data.action_slot = act.slots[0]
    sc.frame_set(1)
except Exception as e:
    print("chick not added:", e)
sc.render.resolution_x, sc.render.resolution_y = 1600, 900
for l in lights: l.location *= 2.2; l.data.energy *= 4.5
aim((1250, -2450, 1250), (-250, 330, 60)); cd.lens = 34
sc.render.filepath = os.path.join(PREV, "Kit_Vignette.png"); bpy.ops.render.render(write_still=True)
print("PROPS_RENDER_DONE", flush=True)
