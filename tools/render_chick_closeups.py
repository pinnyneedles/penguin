#!/usr/bin/env python3
"""Render close-ups of the chick's eye, bill and feet from a built .blend, for A/B review.

    python3 tools/render_chick_closeups.py path/to/Pebble_Chick.blend out_dir [--samples 64] [--size 640]

Writes out_dir/close_head34.png, close_head_side.png, close_eye.png, close_feet.png, close_feet_side.png.
Uses a fixed perspective camera so different builds are directly comparable.
"""
import sys, os, bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
blend, out = argv[0], argv[1]
samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 64
size = int(argv[argv.index("--size") + 1]) if "--size" in argv else 640
os.makedirs(out, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=blend)
sc = bpy.context.scene
sc.frame_set(1)
cd = bpy.data.cameras.new("Closeup"); cd.type = "PERSP"; cd.lens = 85; cd.clip_start = 1; cd.clip_end = 5000
cam = bpy.data.objects.new("Closeup", cd); sc.collection.objects.link(cam); sc.camera = cam
sc.render.resolution_x = sc.render.resolution_y = size; sc.render.resolution_percentage = 100
sc.cycles.samples = samples; sc.cycles.use_denoising = True; sc.cycles.device = "CPU"
sc.render.image_settings.file_format = "PNG"

def shot(name, loc, target, lens=85):
    cam.location = Vector(loc); cd.lens = lens
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(out, name + ".png")
    bpy.ops.render.render(write_still=True)

# Units are centimetres; the character faces -Y, eyes near z 130, bill base near z 121.
shot("close_head34", (110, -235, 160), (2, -40, 126), lens=105)
shot("close_head_side", (265, -45, 130), (0, -42, 125), lens=105)
shot("close_eye", (150, -175, 138), (17, -24, 129), lens=200)
shot("close_feet", (85, -245, 48), (0, -24, 7), lens=105)
shot("close_feet_side", (245, -110, 30), (22, -22, 7), lens=110)
print("CLOSEUPS_DONE", out)
