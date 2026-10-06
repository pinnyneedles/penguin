#!/usr/bin/env python3
"""Author a looping in-place waddle cycle for the Pebble penguin rig and export it
for Unreal, plus a rendered GIF preview.

Usage (needs the `bpy` module, i.e. Blender as a Python module, or run inside Blender):
    python3 tools/make_pebble_waddle.py --package pebble/Pebble_Penguin --out pebble/Pebble_Penguin

Outputs into --out:
    AN_Pebble_Waddle.fbx      skeletal mesh + 33-frame waddle, 30 fps, root stationary
    Pebble_Waddle.gif         rendered loop
    Preview_Waddle.png        four key poses side by side
    Pebble_Waddle.blend       the scene with the new action (only if the source .blend opened)

The cycle is driven by world-space intent (lean forward, sway right, swing leg
forward...) and mapped onto each bone's local axes from its rest matrix, so it
does not depend on the rig's roll conventions. Planted feet are pinned to the
ground each frame by solving the leg's slide along its own axis.
"""
import argparse, math, os, sys

import bpy
from mathutils import Vector, Matrix

# --------------------------------------------------------------------------
# Parameters (centimetres / radians)
# --------------------------------------------------------------------------
FPS = 30
CYCLE = 32                 # frames per full cycle (two steps); frame 33 == frame 1
SWAY = 5.0                 # pelvis side shift toward the planted foot
ROLL = 0.11                # pelvis roll toward the planted foot
BODY_ROLL = 0.05           # extra roll on the torso (same direction)
HEAD_COUNTER = 0.12        # head counter-rolls so the face stays roughly level
HIP_YAW = 0.07
BOB = 1.6                  # vertical bob, two per cycle
LEAN = 0.05                # constant forward lean of the torso
LEG_SWING = 0.36           # leg pitch amplitude
LIFT = 5.5                 # swing-foot clearance
FLIPPER_OUT = 0.22         # flippers held slightly away from the body
FLIPPER_FLAP = 0.10
FLIPPER_SWING = 0.22
TAIL_WAG = 0.28
CREST_FLOP = 0.14

FORWARD = Vector((0, -1, 0))   # Blender-space: the character faces -Y
UP = Vector((0, 0, 1))
RIGHT = Vector((1, 0, 0))      # character's left side is +X (bones named .L live at +X)


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True, help="folder with Pebble_Penguin.blend / SK_Pebble.fbx")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--size", type=int, default=480)
    ap.add_argument("--samples", type=int, default=16)
    return ap.parse_args(argv)


# --------------------------------------------------------------------------
# Scene loading
# --------------------------------------------------------------------------
def load_scene(package):
    blend = os.path.join(package, "Pebble_Penguin.blend")
    try:
        bpy.ops.wm.open_mainfile(filepath=blend)
        rig = bpy.data.objects["Pebble_Rig"]
        char = bpy.data.objects["SK_Pebble"]
        print("opened", blend)
        return rig, char, True
    except Exception as e:  # version mismatch etc. -> rebuild from the FBX
        print("could not use the .blend (", e, "); importing SK_Pebble.fbx instead")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"; sc.unit_settings.scale_length = 0.01
    bpy.ops.import_scene.fbx(filepath=os.path.join(package, "SK_Pebble.fbx"), use_anim=False,
                             ignore_leaf_bones=False, automatic_bone_orientation=False,
                             force_connect_children=False)
    rig = [o for o in sc.objects if o.type == "ARMATURE"][0]
    char = [o for o in sc.objects if o.type == "MESH"][0]
    rig.name, char.name = "Pebble_Rig", "SK_Pebble"
    # The importer infers connected joints, which silences translated channels.
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for b in rig.data.edit_bones: b.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    # Make sure the body texture is hooked up.
    tex = os.path.join(package, "T_Pebble_Body_BaseColor.png")
    for m in char.data.materials:
        if m and "body" in m.name.lower() and m.use_nodes:
            nt = m.node_tree; bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf and not bsdf.inputs["Base Color"].links:
                img = nt.nodes.new("ShaderNodeTexImage"); img.image = bpy.data.images.load(tex)
                nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
    return rig, char, False


def ensure_render_setup(sc, from_blend):
    sc.render.fps = FPS
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    if sc.camera is None or not from_blend:
        cam_data = bpy.data.cameras.new("WaddleCam"); cam = bpy.data.objects.new("WaddleCam", cam_data)
        sc.collection.objects.link(cam); sc.camera = cam
        cam_data.type = "ORTHO"
    sc.camera.data.type = "ORTHO"
    sc.camera.data.ortho_scale = 250
    sc.camera.location = Vector((265, -470, 250))
    sc.camera.rotation_euler = (Vector((0, 0, 95)) - sc.camera.location).to_track_quat("-Z", "Y").to_euler()
    if not any(o.type == "LIGHT" for o in sc.objects):
        for name, loc, energy, size in [("Key", (300, -400, 500), 4e6, 150), ("Fill", (-450, -250, 250), 1.5e6, 250),
                                        ("Rim", (-100, 400, 400), 2e6, 100)]:
            ld = bpy.data.lights.new(name, "AREA"); ld.energy = energy; ld.size = size
            lo = bpy.data.objects.new(name, ld); sc.collection.objects.link(lo); lo.location = loc
            lo.rotation_euler = (Vector((0, 0, 90)) - lo.location).to_track_quat("-Z", "Y").to_euler()
        sc.world = sc.world or bpy.data.worlds.new("World")
        sc.world.use_nodes = True
        bg = sc.world.node_tree.nodes.get("Background")
        if bg: bg.inputs[0].default_value = (0.55, 0.65, 0.72, 1); bg.inputs[1].default_value = 0.6
    if not any(o.name.lower().startswith(("ground", "floor")) for o in sc.objects):
        bpy.ops.mesh.primitive_plane_add(size=2000, location=(0, 0, 0))
        g = bpy.context.active_object; g.name = "Ground_preview"
        m = bpy.data.materials.new("GroundPreview"); m.diffuse_color = (0.6, 0.68, 0.72, 1); g.data.materials.append(m)


# --------------------------------------------------------------------------
# World-intent -> local-channel mapping
# --------------------------------------------------------------------------
class Poser:
    def __init__(self, rig):
        self.rig = rig
        self.rest = {b.name: b.matrix_local.to_3x3() for b in rig.data.bones}   # local axes in armature space
        self.acc = {}
        for p in rig.pose.bones:
            p.rotation_mode = "XYZ"

    def reset(self):
        self.acc = {}
        for p in self.rig.pose.bones:
            p.location = (0, 0, 0); p.rotation_euler = (0, 0, 0); p.scale = (1, 1, 1)

    def rot(self, bone, world_axis, angle):
        """Compose a rotation of `angle` about `world_axis` (armature space) onto a bone,
        expressed exactly in the bone's local frame."""
        R = self.rest[bone]
        local = R.transposed() @ Matrix.Rotation(angle, 3, Vector(world_axis).normalized()) @ R
        self.acc[bone] = self.acc.get(bone, Matrix.Identity(3)) @ local
        self.rig.pose.bones[bone].rotation_euler = self.acc[bone].to_euler("XYZ")

    def move(self, bone, world_vec):
        R = self.rest[bone]
        p = self.rig.pose.bones[bone]
        p.location = p.location + R.transposed() @ Vector(world_vec)

    def world_tail(self, bone):
        bpy.context.view_layer.update()
        return self.rig.matrix_world @ self.rig.pose.bones[bone].tail

    def world_head(self, bone):
        bpy.context.view_layer.update()
        return self.rig.matrix_world @ self.rig.pose.bones[bone].head


def smoothstep(x):
    x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)


def build_waddle(rig):
    P = Poser(rig)
    P.reset(); bpy.context.view_layer.update()
    rest_sole = {s: min(P.world_tail("toe." + s).z, P.world_head("toe." + s).z) for s in "LR"}

    rig.animation_data_create()
    act = bpy.data.actions.new("Pebble_Waddle"); act.use_fake_user = True
    rig.animation_data.action = act
    # Blender 4.4+ slotted actions: make sure the action is bound to this rig.
    if hasattr(act, "slots") and hasattr(rig.animation_data, "action_slot"):
        if not act.slots:
            act.slots.new(id_type="OBJECT", name="Pebble_Rig")
        rig.animation_data.action_slot = act.slots[0]

    for f in range(1, CYCLE + 2):          # 1..33, frame 33 repeats frame 1
        t = (f - 1) / CYCLE * 2 * math.pi
        s, c = math.sin(t), math.cos(t)
        P.reset()

        # Weight transfer: t in [0, pi) -> standing on the LEFT (+X) foot, right foot swings.
        side = s                           # +1 = weight on left
        P.move("pelvis", RIGHT * (SWAY * side))
        P.move("pelvis", UP * (BOB * (s * s) - BOB * 0.5))
        P.rot("pelvis", FORWARD, -ROLL * side)          # roll top toward the planted foot
        P.rot("pelvis", UP, HIP_YAW * c)                # hips twist with the stride
        P.rot("body", FORWARD, -BODY_ROLL * side)
        P.rot("body", RIGHT, LEAN + 0.02 * math.cos(2 * t))
        P.rot("body", UP, -HIP_YAW * 0.6 * c)
        P.rot("head", FORWARD, HEAD_COUNTER * side)      # keep the face closer to level
        P.rot("head", RIGHT, 0.05 * math.cos(2 * t - 0.6))
        P.rot("head", UP, 0.04 * c)
        P.rot("crest", RIGHT, CREST_FLOP * math.sin(2 * t - 1.2))
        P.rot("tail", UP, TAIL_WAG * math.sin(t + 0.5))   # wag about the up axis
        P.rot("tail", RIGHT, 0.08 * math.sin(2 * t))

        # Flippers: held out, swinging opposite to the leg on the same side.
        for sign, L in ((1, "L"), (-1, "R")):
            leg_fwd = c * sign                           # left leg is forward at t=0
            P.rot("flipper." + L, FORWARD, sign * (FLIPPER_OUT + FLIPPER_FLAP * side * sign))
            P.rot("flipper." + L, RIGHT, FLIPPER_SWING * leg_fwd)
            P.rot("flipper_tip." + L, RIGHT, 0.5 * FLIPPER_SWING * (c * sign * 0.8 + s * sign * 0.3))
            P.rot("flipper_tip." + L, FORWARD, sign * 0.06)

        # Legs: left planted for t in [0, pi), swinging for [pi, 2pi).
        for sign, L in ((1, "L"), (-1, "R")):
            fwd = c * sign                               # +1 = this leg fully forward
            swing_phase = (-s * sign)                    # > 0 while this foot is in the air
            lift = LIFT * smoothstep(swing_phase) * (1 - abs(fwd)) ** 0.5 if swing_phase > 0 else 0.0
            P.rot("leg." + L, RIGHT, -LEG_SWING * fwd)      # negative X pitch swings the foot forward
            P.rot("foot." + L, RIGHT, LEG_SWING * fwd * 0.85)  # keep the sole roughly flat
            if swing_phase > 0:
                P.rot("foot." + L, RIGHT, 0.25 * smoothstep(swing_phase))   # toes drop while in the air
                P.rot("toe." + L, RIGHT, 0.12 * smoothstep(swing_phase))
            # Pin the sole: slide the leg along itself so the lowest toe point sits at rest height + lift.
            for _ in range(3):
                low = min(P.world_tail("toe." + L).z, P.world_head("toe." + L).z)
                target = rest_sole[L] + lift
                err = target - low
                if abs(err) < 0.02: break
                P.move("leg." + L, UP * err)

        for p in rig.pose.bones:
            p.keyframe_insert("location", frame=f, group=p.name)
            p.keyframe_insert("rotation_euler", frame=f, group=p.name)
            p.keyframe_insert("scale", frame=f, group=p.name)

    for fc in action_fcurves(act):
        for k in fc.keyframe_points: k.interpolation = "LINEAR"
    return act


def action_fcurves(act):
    """F-curves of an action across legacy (<4.4) and layered (5.x) action APIs."""
    if hasattr(act, "fcurves") and len(act.fcurves):
        return list(act.fcurves)
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for cb in strip.channelbags:
                out.extend(cb.fcurves)
    return out


# --------------------------------------------------------------------------
# Export / render
# --------------------------------------------------------------------------
def export_fbx(rig, char, path):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, CYCLE + 1
    sc.frame_set(1)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True); char.select_set(True); bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE", "MESH"}, global_scale=1,
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS", axis_forward="X", axis_up="Z",
        use_space_transform=True, bake_space_transform=False, add_leaf_bones=False,
        primary_bone_axis="Y", secondary_bone_axis="X", use_armature_deform_only=True,
        use_mesh_modifiers=True, mesh_smooth_type="FACE", use_tspace=True, bake_anim=True,
        bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False,
        bake_anim_force_startend_keying=True, bake_anim_step=1, bake_anim_simplify_factor=0,
        path_mode="COPY", embed_textures=True)


def render_frames(out_dir, size, samples):
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.image_settings.file_format = "PNG"
    frames_dir = os.path.join(out_dir, "waddle_frames"); os.makedirs(frames_dir, exist_ok=True)
    paths = []
    for f in range(1, CYCLE + 1):
        sc.frame_set(f)
        p = os.path.join(frames_dir, f"{f:03d}.png")
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        paths.append(p); print("rendered frame", f, flush=True)
    return paths


def assemble_gif(paths, gif_path, sheet_path):
    from PIL import Image
    frames = [Image.open(p).convert("RGB") for p in paths]
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0,
                   optimize=False)
    keys = [frames[i] for i in (0, CYCLE // 4, CYCLE // 2, 3 * CYCLE // 4)]
    w, h = keys[0].size
    sheet = Image.new("RGB", (w * 4, h))
    for i, im in enumerate(keys): sheet.paste(im, (i * w, 0))
    sheet.save(sheet_path)


def main():
    a = parse()
    os.makedirs(a.out, exist_ok=True)
    rig, char, from_blend = load_scene(a.package)
    sc = bpy.context.scene
    build_waddle(rig)
    sc.frame_start, sc.frame_end = 1, CYCLE + 1
    export_fbx(rig, char, os.path.join(a.out, "AN_Pebble_Waddle.fbx"))
    print("exported AN_Pebble_Waddle.fbx")
    if from_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.out, "Pebble_Waddle.blend"), copy=True)
    if not a.no_render:
        ensure_render_setup(sc, from_blend)
        paths = render_frames(a.out, a.size, a.samples)
        assemble_gif(paths, os.path.join(a.out, "Pebble_Waddle.gif"), os.path.join(a.out, "Preview_Waddle.png"))
        print("wrote Pebble_Waddle.gif and Preview_Waddle.png")


if __name__ == "__main__":
    main()
