#!/usr/bin/env python3
"""Render the belly-slide chain (start, loop twice, end) travelling over snow with a following
camera, for previewing how the in-place clips read once gameplay moves the character.

    python3 tools/render_chick_slide_travel.py pebble/Pebble_Chick [--size 480x308] [--samples 12]

Writes Pebble_Chick_BellySlide_Travel.gif into the folder. Display only: in Unreal the clips play in
place and gameplay sets the speed. Here the speed surges after each push and eases off in the glide.
"""
import sys, os, math, random, glob
import bpy
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
D = argv[0]
size = argv[argv.index("--size") + 1] if "--size" in argv else "480x308"
SX, SY = (int(v) for v in size.split("x"))
SAMPLES = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 12
sys.argv = [sys.argv[0]]
import make_chick_anims as M

bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "Pebble_Chick_Anims.blend"))
sc = bpy.context.scene
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
A = {n: bpy.data.actions[n] for n in ("Chick_BellySlide_Start", "Chick_BellySlide_Loop", "Chick_BellySlide_End")}

# snow ground with drifts and grain
floor = next(o for o in bpy.data.objects if o.type == "MESH" and o.parent is None and "floor" in o.name.lower())
m = bpy.data.materials.new("Snow"); m.use_nodes = True; nt = m.node_tree; N = nt.nodes; Lk = nt.links
bs = N.get("Principled BSDF"); tc = N.new("ShaderNodeTexCoord")
big = N.new("ShaderNodeTexNoise"); big.inputs["Scale"].default_value = 0.018; big.inputs["Detail"].default_value = 4
fine = N.new("ShaderNodeTexNoise"); fine.inputs["Scale"].default_value = 0.06; fine.inputs["Detail"].default_value = 8
ramp = N.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = (0.50, 0.60, 0.74, 1); ramp.color_ramp.elements[1].color = (0.93, 0.96, 1.0, 1)
ramp.color_ramp.elements[0].position = 0.35; ramp.color_ramp.elements[1].position = 0.65
add = N.new("ShaderNodeMath"); add.operation = "ADD"
bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.7; bump.inputs["Distance"].default_value = 3.0
for nd in (big, fine): Lk.new(tc.outputs["Object"], nd.inputs["Vector"])
Lk.new(big.outputs["Fac"], add.inputs[0]); Lk.new(fine.outputs["Fac"], add.inputs[1])
Lk.new(big.outputs["Fac"], ramp.inputs["Fac"]); Lk.new(ramp.outputs["Color"], bs.inputs["Base Color"])
Lk.new(add.outputs["Value"], bump.inputs["Height"]); Lk.new(bump.outputs["Normal"], bs.inputs["Normal"])
bs.inputs["Roughness"].default_value = 0.45
floor.data.materials.clear(); floor.data.materials.append(m)
w = sc.world.node_tree.nodes.get("Background"); w.inputs[0].default_value = (0.62, 0.72, 0.84, 1); w.inputs[1].default_value = 0.75

# pebbles and snow mounds beside the path
rnd = random.Random(7)
rock = bpy.data.materials.new("Pebble"); rock.use_nodes = True
rock.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value = (0.16, 0.18, 0.22, 1)
for i in range(110):
    x = rnd.uniform(-420, 420)
    if abs(x) < 110: x = 110 * (1 if x >= 0 else -1) + x
    y = rnd.uniform(-1100, 250)
    if rnd.random() < 0.6:
        r = rnd.uniform(3, 11)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=r, location=(x, y, r * 0.35))
        o = bpy.context.object; o.scale = (rnd.uniform(0.8, 1.4), rnd.uniform(0.8, 1.4), rnd.uniform(0.5, 0.8)); o.data.materials.append(rock)
    else:
        r = rnd.uniform(18, 55)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=r, location=(x, y, -r * 0.55))
        o = bpy.context.object; o.scale = (rnd.uniform(0.9, 1.6), rnd.uniform(0.9, 1.6), 1.0); o.data.materials.append(m)
    bpy.ops.object.shade_smooth()

cam = sc.camera; cam.data.type = "PERSP"; cam.data.lens = 38; cam.data.clip_start = 5; cam.data.clip_end = 50000
lights = [o for o in bpy.data.objects if o.type == "LIGHT"]; light0 = {o.name: o.location.copy() for o in lights}
CAM_OFF = Vector((330, -300, 150)); AIM_OFF = Vector((0, -5, 50))
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = SX, SY, 100
sc.render.image_settings.file_format = "PNG"


def smooth(u):
    u = min(max(u, 0.0), 1.0); return u * u * (3 - 2 * u)


def loop_speed(f):
    t = (f - 1) / (M.SLIDE_N - 1)
    surge = sum(math.exp(-((t - t0 - 0.12) % 1.0) / 0.35) for _, t0 in M.PUSHES)   # push, then coast
    return 2.6 + 1.1 * surge                    # cm per frame


V0 = loop_speed(1)
seq = [("Chick_BellySlide_Start", f, V0 * smooth((f - 10) / 8)) for f in range(1, 29)]
for _ in range(2):
    seq += [("Chick_BellySlide_Loop", f, loop_speed(f)) for f in range(1, M.SLIDE_N)]
seq += [("Chick_BellySlide_End", f, V0 * (1 - smooth((f - 1) / 13))) for f in range(1, 29)]
frames_dir = os.path.join(D, "_anim_frames", "travel"); os.makedirs(frames_dir, exist_ok=True)
for p in glob.glob(os.path.join(frames_dir, "*.png")): os.remove(p)
travel = 0.0; paths = []
for i, (name, f, v) in enumerate(seq, start=1):
    travel += v
    act = A[name]; rig.animation_data.action = act
    if hasattr(act, "slots") and act.slots: rig.animation_data.action_slot = act.slots[0]
    pos = Vector((0, -travel, 0)); rig.location = pos; sc.frame_set(f)
    cam.location = pos + CAM_OFF
    cam.rotation_euler = (pos + AIM_OFF - cam.location).to_track_quat("-Z", "Y").to_euler()
    for o in lights: o.location = light0[o.name] + pos
    fp = os.path.join(frames_dir, f"t_{i:03d}.png"); sc.render.filepath = fp; bpy.ops.render.render(write_still=True); paths.append(fp)

from PIL import Image
frames = [Image.open(p).convert("RGB") for p in paths]
sample = Image.new("RGB", (SX, SY * 6))
for j, k in enumerate(range(0, len(frames), max(1, len(frames) // 6))[:6]): sample.paste(frames[k], (0, j * SY))
pal = sample.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
q = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in frames]
out = os.path.join(D, "Pebble_Chick_BellySlide_Travel.gif")
q[0].save(out, save_all=True, append_images=q[1:], duration=33, loop=0, optimize=True)
print("TRAVEL_DONE", round(travel, 1), "cm", len(seq), "frames", round(os.path.getsize(out) / 1e6, 2), "MB", flush=True)
