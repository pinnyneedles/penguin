#!/usr/bin/env python3
"""Assemble the Pebble Chick Unreal package: mesh, skeleton, animations, textures, import guide,
reference data, previews and the Blender sources, zipped for dropping into a game project.

    python3 tools/package_chick_unreal.py            # writes dist/PebbleChick_Unreal.zip

Run after tools/build_pebble_chick.py and tools/make_chick_anims.py so the files are current.
Reference photos are not included.
"""
import csv, json, os, shutil, zipfile, datetime
import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "pebble", "Pebble_Chick")
DIST = os.path.join(ROOT, "dist")
NAME = "PebbleChick_Unreal"
PKG = os.path.join(DIST, NAME)

CLIPS = ["Idle", "Waddle", "Waddle_RootMotion", "Jump_Start", "Jump_Loop", "Jump_Land", "BellySlide_Start",
         "BellySlide_Loop", "BellySlide_Loop_LeanLeft", "BellySlide_Loop_LeanRight", "BellySlide_End"]
MATERIALS = [  # slot, used for, base colour (linear), roughness, textures
    ("M_Chick_Body", "down: body, flippers, tail", "texture", 0.80, "T_Chick_Body_BaseColor + T_Chick_Body_Normal_DX"),
    ("M_Chick_Foot", "legs, feet, eyelids", (0.030, 0.028, 0.030), 0.62, ""),
    ("M_Chick_Claw", "claws", (0.075, 0.070, 0.065), 0.35, ""),
    ("M_Chick_Iris", "eyeballs", (0.030, 0.016, 0.009), 0.12, ""),
    ("M_Chick_Pupil", "pupils", (0.009, 0.008, 0.010), 0.19, ""),
    ("M_Chick_Glint", "eye highlights", (1.000, 0.980, 0.900), 0.20, ""),
    ("M_Chick_Bill", "upper bill", (0.022, 0.019, 0.021), 0.32, ""),
    ("M_Chick_BillLower", "lower bill", (0.050, 0.043, 0.043), 0.38, ""),
]


def shrink_gif(src, dst, width, colors=96):
    """Smaller preview copy: resized, one shared palette, no dithering."""
    from PIL import Image, ImageSequence
    im = Image.open(src)
    dur = im.info.get("duration", 33)
    frames = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
    h = round(frames[0].height * width / frames[0].width)
    frames = [f.resize((width, h), Image.LANCZOS) for f in frames]
    k = max(1, len(frames) // 6)
    sample = Image.new("RGB", (width, h * 6))
    for i, j in enumerate(range(0, len(frames), k)):
        if i < 6: sample.paste(frames[j], (0, i * h))
    pal = sample.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    q[0].save(dst, save_all=True, append_images=q[1:], duration=dur, loop=0, optimize=True)


def copy(src_name, dst_dir, dst_name=None):
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(os.path.join(SRC, src_name), os.path.join(dst_dir, dst_name or src_name))


def main():
    if os.path.exists(PKG):
        shutil.rmtree(PKG)
    os.makedirs(PKG)
    copy("SK_Pebble_Chick.fbx", os.path.join(PKG, "Content", "Meshes"))
    for c in CLIPS:
        copy(f"AN_Pebble_Chick_{c}.fbx", os.path.join(PKG, "Content", "Animations"))
    for t in ("T_Chick_Body_BaseColor.png", "T_Chick_Body_Normal_DX.png"):
        copy(t, os.path.join(PKG, "Content", "Textures"))
    for f in ("Pebble_Chick_Anims.blend", "Pebble_Chick.blend", "T_Chick_Body_Normal_GL.png"):
        copy(f, os.path.join(PKG, "Source_Blender"))
    for f in ("Preview_Sheet.png", "Preview_Hero.png", "Preview_Animations.png", "Preview_SlideLean.png"):
        copy(f, os.path.join(PKG, "Previews"))
    for f, w in (("Pebble_Chick_Idle.gif", 300), ("Pebble_Chick_Waddle.gif", 300), ("Pebble_Chick_Jump.gif", 300),
                 ("Pebble_Chick_BellySlide_Travel.gif", 400)):
        shrink_gif(os.path.join(SRC, f), os.path.join(PKG, "Previews", f), w)

    ref = os.path.join(PKG, "Reference"); os.makedirs(ref)
    with open(os.path.join(ref, "materials.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["slot", "used_for", "base_color_linear_r", "g", "b", "roughness", "metallic", "textures"])
        for slot, use, col, rough, tex in MATERIALS:
            r, g, b = ("", "", "") if col == "texture" else col
            w.writerow([slot, use, r, g, b, rough, 0, tex])
    stats = json.load(open(os.path.join(SRC, "anim_stats.json")))
    with open(os.path.join(ref, "animations.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["file", "sequence", "frames", "seconds_at_30fps", "loops", "root_motion"])
        for c in CLIPS:
            n = stats["clips"]["Chick_" + c]["frames"]
            loops = c in ("Idle", "Waddle", "Waddle_RootMotion", "Jump_Loop") or c.startswith("BellySlide_Loop")
            w.writerow([f"AN_Pebble_Chick_{c}.fbx", "Chick_" + c, n, round((n - 1) / 30, 2), "yes" if loops else "no",
                        "yes" if c == "Waddle_RootMotion" else "no"])
    json.dump(dict(fps=30, waddle_ground_speed_cm_s=stats["waddle_speed_cm_s"], events=stats["events"],
                   notes="Frame numbers are 1-based, as shown in Unreal's sequence timeline."),
              open(os.path.join(ref, "anim_events.json"), "w"), indent=2)
    shutil.copy2(os.path.join(SRC, "anim_validation.json"), os.path.join(ref, "anim_validation.json"))
    shutil.copy2(os.path.join(SRC, "source_stats.json"), os.path.join(ref, "mesh_stats.json"))

    guide = open(os.path.join(SRC, "IMPORT_GUIDE.md")).read()
    open(os.path.join(PKG, "IMPORT_GUIDE.md"), "w").write(guide)
    body = markdown.markdown(guide, extensions=["tables", "fenced_code"])
    hero = ('<p class="hero"><img src="Previews/Preview_Sheet.png" alt="Pebble Chick from four angles"></p>'
            '<p class="hero"><img src="Previews/Pebble_Chick_Waddle.gif" alt="waddle"> '
            '<img src="Previews/Pebble_Chick_BellySlide_Travel.gif" alt="belly slide"></p>')
    body = body.replace("</h1>", "</h1>" + hero, 1)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Pebble Chick import guide</title>
<style>
:root{{--bg:#fbfaf8;--fg:#1f1d1a;--muted:#5f5a52;--line:#e2ddd5;--code:#f1ede6;--accent:#8a5a2b}}
@media (prefers-color-scheme: dark){{:root{{--bg:#1b1916;--fg:#ece7df;--muted:#a9a196;--line:#3a352e;--code:#28241f;--accent:#d9a26a}}}}
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
        "PEBBLE CHICK for Unreal Engine 5\n\n"
        "Open IMPORT_GUIDE.html (or IMPORT_GUIDE.md) and follow Steps 1 to 7.\n\n"
        "Quick start:\n"
        "  1. Import Content/Meshes/SK_Pebble_Chick.fbx as a Skeletal Mesh (new skeleton, scale 1).\n"
        "  2. Import Content/Textures and build M_Chick_Body with the colour and DX normal map.\n"
        "  3. Import all of Content/Animations onto SK_Pebble_Chick_Skeleton (animations only).\n"
        "  4. Character Blueprint: capsule 76 / 45, mesh Z -76, yaw so the bill faces the arrow.\n"
        "  5. Anim Blueprint: Idle/Waddle blend space, jump and belly-slide states (guide, Step 7).\n\n"
        "Folders: Content (import these), Reference (materials, clip list, notify frames),\n"
        "Previews (renders and GIFs), Source_Blender (editable scenes).\n")

    os.makedirs(DIST, exist_ok=True)
    zpath = os.path.join(DIST, NAME + ".zip")
    if os.path.exists(zpath):
        os.remove(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _, files in os.walk(PKG):
            for f in sorted(files):
                full = os.path.join(dirpath, f)
                z.write(full, os.path.relpath(full, DIST))
    print("wrote", zpath, round(os.path.getsize(zpath) / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
