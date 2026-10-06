#!/usr/bin/env python3
"""Render fixed look-development views of a built chick .blend for side-by-side review.

    python3 tools/render_chick_lookdev.py path/to/Pebble_Chick.blend out_dir [--samples 48] [--size 560]

Views: ref34 (three-quarter front at chest height, like a field photo), side, back34, down (chest close-up),
head (face close-up). Fixed perspective cameras so different builds compare directly.
"""
import sys, os, bpy
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
blend, out = argv[0], argv[1]
samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 48
size = int(argv[argv.index("--size") + 1]) if "--size" in argv else 560
os.makedirs(out, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=blend)
sc = bpy.context.scene; sc.frame_set(1)
cd = bpy.data.cameras.new("Look"); cd.type = "PERSP"; cd.clip_start = 1; cd.clip_end = 10000
cam = bpy.data.objects.new("Look", cd); sc.collection.objects.link(cam); sc.camera = cam
sc.render.resolution_x = sc.render.resolution_y = size; sc.render.resolution_percentage = 100
sc.cycles.samples = samples; sc.cycles.use_denoising = True; sc.cycles.device = "CPU"
sc.render.image_settings.file_format = "PNG"
def shot(name, loc, target, lens):
    cam.location = Vector(loc); cd.lens = lens
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(out, name + ".png"); bpy.ops.render.render(write_still=True)
shot("ref34", (230, -560, 125), (0, 0, 76), 70)
shot("side", (620, -40, 110), (0, -10, 76), 70)
shot("back34", (-300, 520, 150), (0, 0, 76), 70)
shot("down", (120, -260, 95), (0, -38, 72), 85)
shot("head", (120, -260, 140), (2, -25, 125), 110)
print("LOOKDEV_DONE", out)
