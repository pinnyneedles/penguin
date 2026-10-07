#!/usr/bin/env python3
"""Render the crab's four levels of detail side by side: shaded on top, wireframe below.

    python3 tools/render_crab_lods.py [crab]        # writes crab/Preview_LODs.png
"""
import json, os, sys
import bpy
from PIL import Image, ImageDraw, ImageFont

D = os.path.abspath(sys.argv[-1] if len(sys.argv) > 1 and not sys.argv[-1].endswith(".py") else "crab")
bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "Crab.blend"))
sc = bpy.context.scene; cam = sc.camera
obs = [bpy.data.objects["SK_Crab"]] + [bpy.data.objects[f"SK_Crab_LOD{i}"] for i in (1, 2, 3)]
for c in bpy.data.collections: c.hide_render = False
tris = json.load(open(os.path.join(D, "source_stats.json")))["lod_triangles"]

# wireframe look: light grey with dark triangle edges, eyes included
wire = bpy.data.materials.new("PREVIEW • LOD wire"); wire.use_nodes = True
wn = wire.node_tree; bs = wn.nodes["Principled BSDF"]; bs.inputs["Roughness"].default_value = 0.8
wf = wn.nodes.new("ShaderNodeWireframe"); wf.use_pixel_size = True; wf.inputs["Size"].default_value = 1.0
mix = wn.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
rgba = [i for i in mix.inputs if i.type == "RGBA"]
rgba[0].default_value = (0.62, 0.60, 0.58, 1); rgba[1].default_value = (0.03, 0.03, 0.03, 1)
wn.links.new(wf.outputs["Fac"], mix.inputs[0])
wn.links.new(next(o for o in mix.outputs if o.type == "RGBA"), bs.inputs["Base Color"])

cam.location = (150, -220, 140); cam.data.ortho_scale = 118
from mathutils import Vector
cam.rotation_euler = (Vector((0, -6, 12)) - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.render.resolution_x = sc.render.resolution_y = 600; sc.cycles.samples = 32
shots = {}
for lv, ob in enumerate(obs):
    for o in obs: o.hide_render = o is not ob; o.hide_set(o is not ob)
    keep = list(ob.data.materials)
    for wired in (False, True):
        if wired:
            for k in range(len(ob.data.materials)): ob.data.materials[k] = wire
        p = os.path.join(D, f"_lod{lv}_{int(wired)}.png"); sc.render.filepath = p
        bpy.ops.render.render(write_still=True); shots[(lv, wired)] = p
    for k, m in enumerate(keep): ob.data.materials[k] = m

try:
    font = ImageFont.truetype("DejaVuSans.ttf", 22)
except OSError:
    font = ImageFont.load_default()
sheet = Image.new("RGB", (2400, 1240), (240, 240, 238)); dr = ImageDraw.Draw(sheet)
for (lv, wired), p in shots.items():
    sheet.paste(Image.open(p).convert("RGB").crop((0, 40, 600, 600)), (lv * 600, wired * 600))
    os.remove(p)
for lv in range(4):
    dr.text((lv * 600 + 14, 1206), f"LOD{lv}: {tris[lv]:,} triangles", fill=(30, 30, 30), font=font)
sheet.save(os.path.join(D, "Preview_LODs.png"))
print("LOD_PREVIEW", os.path.join(D, "Preview_LODs.png"), flush=True)
