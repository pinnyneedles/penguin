#!/usr/bin/env python3
"""Assemble the Crab Unreal package: skeletal mesh, animations, textures, import guide, reference data,
previews and the Blender sources, zipped for dropping into a game project.

    python3 tools/package_crab_unreal.py            # writes dist/Crab_Unreal.zip

Run after tools/build_crab.py, tools/make_crab_anims.py and tools/verify_crab.py so the files are current.
"""
import csv, datetime, json, os, shutil, subprocess, sys, zipfile
import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "crab")
DIST = os.path.join(ROOT, "dist")
NAME = "Crab_Unreal"
PKG = os.path.join(DIST, NAME)
CLIPS = ["Idle", "Scuttle_Left", "Scuttle_Right", "Walk_Forward", "Walk_Backward", "Turn_Left", "Turn_Right", "Threat",
         "Attack_Snap", "Claw_Snap", "Hit", "Death"]
WHAT = {"Idle": "breathing, eye stalks glance around, antenna flicks, mouthparts, claw snips, two leg shuffles",
        "Scuttle_Left": "sideways run toward the crab's own left", "Scuttle_Right": "sideways run toward its right",
        "Walk_Forward": "slow forward walk", "Walk_Backward": "backs away with its claws up",
        "Turn_Left": "turns in place, counter-clockwise seen from above", "Turn_Right": "turns in place, clockwise",
        "Threat": "rears up, claws raised wide and open, two snaps",
        "Attack_Snap": "wind-up, lunge and double pinch", "Claw_Snap": "claws only, for a layered blend: left snap, right snap",
        "Hit": "flinch: knocked back, eyes fold, claws tucked", "Death": "curls up, flips onto its back, legs twitch, then still"}
# The packaged .blend files keep colour and ORM maps in Content/Textures and the OpenGL normal map next to them.
RELINK = r'''
import bpy, os, sys
src, dst = sys.argv[-2], sys.argv[-1]
bpy.ops.wm.open_mainfile(filepath=src)
for img in bpy.data.images:
    if not img.filepath: continue
    f = os.path.basename(img.filepath)
    img.filepath = ("//" if "_Normal_GL" in f else "//../Content/Textures/") + f
bpy.ops.wm.save_as_mainfile(filepath=dst, relative_remap=False)
'''


def shrink_gif(src, dst, width, colors=128):
    from PIL import Image, ImageSequence
    im = Image.open(src)
    dur = im.info.get("duration", 33)
    frames = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
    h = round(frames[0].height * width / frames[0].width)
    frames = [f.resize((width, h), Image.LANCZOS) for f in frames]
    pal = frames[len(frames) // 2].quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(dst, save_all=True, append_images=q[1:], duration=dur, loop=0, optimize=True)


def main():
    if os.path.exists(PKG):
        shutil.rmtree(PKG)
    for sub in ("Content/Meshes", "Content/Animations", "Content/Textures", "Reference", "Previews", "Source_Blender"):
        os.makedirs(os.path.join(PKG, sub))
    cp = lambda f, sub: shutil.copy2(os.path.join(SRC, f), os.path.join(PKG, sub, f))
    for f in ("SK_Crab.fbx", "SK_Crab_LOD1.fbx", "SK_Crab_LOD2.fbx", "SK_Crab_LOD3.fbx"):
        cp(f, "Content/Meshes")
    for c in CLIPS:
        cp(f"AN_Crab_{c}.fbx", "Content/Animations")
    for t in ("T_Crab_BaseColor.png", "T_Crab_Normal_DX.png", "T_Crab_ORM.png"):
        cp(t, "Content/Textures")
    cp("T_Crab_Normal_GL.png", "Source_Blender")
    script = os.path.join(DIST, "_relink_crab.py")
    open(script, "w").write(RELINK)
    for f in ("Crab.blend", "Crab_Anims.blend"):
        subprocess.run([sys.executable, script, os.path.join(SRC, f), os.path.join(PKG, "Source_Blender", f)],
                       check=True, capture_output=True)
    os.remove(script)
    for f in ("Preview_Sheet.png", "Preview_Hero.png", "Preview_Back.png", "Preview_Animations.png", "Preview_LODs.png"):
        cp(f, "Previews")
    for f, w in (("Crab_Scuttle_Travel.gif", 360), ("Crab_Procedural_Terrain.gif", 360), ("Crab_Idle.gif", 300),
                 ("Crab_Walk.gif", 300), ("Crab_Walk_Backward.gif", 300), ("Crab_Turn.gif", 300), ("Crab_Threat.gif", 300),
                 ("Crab_Attack.gif", 300), ("Crab_Claw_Snap.gif", 300), ("Crab_Hit.gif", 300), ("Crab_Death.gif", 300)):
        shrink_gif(os.path.join(SRC, f), os.path.join(PKG, "Previews", f), w)

    ref = os.path.join(PKG, "Reference")
    stats = json.load(open(os.path.join(SRC, "anim_stats.json")))
    with open(os.path.join(ref, "animations.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "sequence", "frames", "seconds_at_30fps", "loops", "ground_speed_cm_s", "turn_deg_s", "what"])
        for c in CLIPS:
            s = stats["clips"]["Crab_" + c]
            w.writerow([f"AN_Crab_{c}.fbx", "Crab_" + c, s["frames"], round((s["frames"] - 1) / 30, 2),
                        "yes" if s["loop"] else "no", s.get("speed_cm_s", ""), s.get("turn_deg_s", ""), WHAT[c]])
    with open(os.path.join(ref, "materials.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["slot", "used_for", "base_color", "roughness", "metallic", "normal", "notes"])
        w.writerow(["M_Crab_Shell", "shell, legs, claws, eye stalks", "T_Crab_BaseColor", "T_Crab_ORM (G)", "T_Crab_ORM (B)",
                    "T_Crab_Normal_DX", "ORM red channel is baked ambient occlusion; optional clear coat 0.1"])
        w.writerow(["M_Crab_Eye", "eyes", "0.008, 0.007, 0.008 (linear)", 0.06, 0, "", "optional clear coat 1.0"])
    json.dump(dict(fps=stats["fps"], scuttle_speed_cm_s=stats["scuttle_speed_cm_s"], walk_speed_cm_s=stats["walk_speed_cm_s"],
                   walk_backward_speed_cm_s=stats["walk_backward_speed_cm_s"], turn_rate_deg_s=stats["turn_rate_deg_s"],
                   events=stats["events"], attack=stats.get("attack"),
                   notes="Frame numbers are 1-based, as shown in Unreal's sequence timeline."),
              open(os.path.join(ref, "anim_events.json"), "w"), indent=2)
    shutil.copy2(os.path.join(SRC, "anim_validation.json"), os.path.join(ref, "anim_validation.json"))
    shutil.copy2(os.path.join(SRC, "source_stats.json"), os.path.join(ref, "mesh_stats.json"))
    for f in ("procedural_rig.json", "Rig_Diagram.png"):
        shutil.copy2(os.path.join(SRC, f), os.path.join(ref, f))

    guide = open(os.path.join(SRC, "IMPORT_GUIDE.md")).read()
    open(os.path.join(PKG, "IMPORT_GUIDE.md"), "w").write(guide)
    body = markdown.markdown(guide, extensions=["tables", "fenced_code"])
    hero = ('<p class="hero"><img src="Previews/Preview_Sheet.png" alt="the crab from four angles"></p>'
            '<p class="hero"><img src="Previews/Crab_Scuttle_Travel.gif" alt="scuttle"> '
            '<img src="Previews/Crab_Procedural_Terrain.gif" alt="procedural feet on uneven ground"></p>'
            '<p class="hero"><img src="Previews/Crab_Attack.gif" alt="attack"> <img src="Previews/Crab_Turn.gif" alt="turn"> '
            '<img src="Previews/Crab_Death.gif" alt="death"></p>')
    body = body.replace("</h1>", "</h1>" + hero, 1)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Crab import guide</title>
<style>
:root{{--bg:#fbf9f8;--fg:#1f1b1a;--muted:#5f5752;--line:#e4dcd8;--code:#f2ebe8;--accent:#a8341f}}
@media (prefers-color-scheme: dark){{:root{{--bg:#1b1716;--fg:#eee7e4;--muted:#a99f9a;--line:#3a3230;--code:#2a2321;--accent:#f08a6c}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:24px 16px}}
main{{max-width:880px;margin:0 auto}} h1{{font-size:2rem;margin:.2em 0 .4em}} h2{{margin-top:2em;border-top:1px solid var(--line);padding-top:1em}}
table{{border-collapse:collapse;width:100%;margin:1em 0;font-size:.92rem;display:block;overflow-x:auto}}
th,td{{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}} th{{background:var(--code)}}
code,pre{{background:var(--code);border-radius:4px}} code{{padding:1px 4px}} pre{{padding:12px;overflow-x:auto}}
blockquote{{margin:1em 0;padding:.5em 1em;border-left:4px solid var(--accent);color:var(--muted)}}
.hero img{{max-width:100%;border-radius:6px}} .hero{{margin:.5em 0}} a{{color:var(--accent)}}
hr{{display:none}} code{{overflow-wrap:anywhere}} main{{overflow-wrap:break-word}}
</style></head><body><main>{body}
<p style="color:var(--muted);font-size:.85rem">Package built {datetime.date.today().isoformat()}.</p></main></body></html>"""
    open(os.path.join(PKG, "IMPORT_GUIDE.html"), "w").write(html)
    open(os.path.join(PKG, "README_FIRST.txt"), "w").write(
        "CRAB for Unreal Engine 5\n\n"
        "Open IMPORT_GUIDE.html (or IMPORT_GUIDE.md) and follow Steps 1 to 9.\n"
        "Step 10 (optional) sets up procedural animation: feet on uneven ground, claw IK, secondary motion.\n\n"
        "Quick start:\n"
        "  1. Import Content/Meshes/SK_Crab.fbx as a Skeletal Mesh (new skeleton, scale 1),\n"
        "     then add SK_Crab_LOD1-3.fbx as its levels of detail.\n"
        "  2. Import Content/Textures: Normal_DX = Normalmap, ORM = Masks (no sRGB).\n"
        "  3. Build M_Crab_Shell (colour, DX normal, ORM) and M_Crab_Eye (glossy black).\n"
        "  4. Import all twelve files in Content/Animations onto SK_Crab_Skeleton (animations only).\n"
        "  5. Character Blueprint: capsule 34 / 34, mesh Z -34, yaw so the eyes face the arrow,\n"
        "     Max Walk Speed 50, Orient Rotation to Movement off (crabs strafe).\n"
        "  6. Anim Blueprint: 2D blend space Side/Forward, turn-in-place clips, a Dead state,\n"
        "     montages for Threat, Attack, Hit, and Claw_Snap layered on the claws.\n\n"
        "Folders: Content (import these), Reference (materials, clip list, notify frames,\n"
        "procedural_rig.json and Rig_Diagram.png for procedural setups),\n"
        "Previews (renders and GIFs), Source_Blender (posing rig and editable clips).\n")

    os.makedirs(DIST, exist_ok=True)
    zpath = os.path.join(DIST, NAME + ".zip")
    if os.path.exists(zpath):
        os.remove(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _, files in sorted(os.walk(PKG)):
            for f in sorted(files):
                full = os.path.join(dirpath, f)
                z.write(full, os.path.relpath(full, DIST))
    print("wrote", zpath, round(os.path.getsize(zpath) / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
