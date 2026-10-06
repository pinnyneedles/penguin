#!/usr/bin/env python3
"""Assemble the Penguin Level Kit Unreal package: meshes with collision and sockets, textures, import guide,
reference data, previews and the Blender source, zipped for dropping into a game project.

    python3 tools/package_props_unreal.py            # writes dist/PenguinKit_Unreal.zip

Run after tools/make_props.py and tools/render_props.py so the files are current.
"""
import csv, glob, json, os, shutil, subprocess, sys, zipfile, datetime
import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "props", "Kit")
DIST = os.path.join(ROOT, "dist")
NAME = "PenguinKit_Unreal"
PKG = os.path.join(DIST, NAME)

# The packaged .blend keeps colour and ORM maps in Content/Textures and its OpenGL normal maps next to it.
RELINK = r'''
import bpy, os, sys
src, dst = sys.argv[-2], sys.argv[-1]
bpy.ops.wm.open_mainfile(filepath=src)
for img in bpy.data.images:
    f = os.path.basename(img.filepath)
    img.filepath = ("//" if "_Normal_GL" in f else "//../Content/Textures/") + f
bpy.ops.wm.save_as_mainfile(filepath=dst, relative_remap=False)
'''


def main():
    if os.path.exists(PKG):
        shutil.rmtree(PKG)
    for sub in ("Content/Meshes", "Content/Textures", "Reference", "Previews", "Source_Blender"):
        os.makedirs(os.path.join(PKG, sub))
    for f in sorted(glob.glob(os.path.join(SRC, "Meshes", "SM_*.fbx"))):
        shutil.copy2(f, os.path.join(PKG, "Content", "Meshes"))
    for f in sorted(glob.glob(os.path.join(SRC, "Textures", "T_*.png"))):
        sub = "Source_Blender" if "_Normal_GL" in f else os.path.join("Content", "Textures")
        shutil.copy2(f, os.path.join(PKG, sub))
    for f in ("Kit_Sheet.png", "Kit_Vignette.png", "Igloo_Views.png"):
        shutil.copy2(os.path.join(SRC, "Previews", f), os.path.join(PKG, "Previews"))
    script = os.path.join(PKG, "_relink.py")
    open(script, "w").write(RELINK)
    subprocess.run([sys.executable, script, os.path.join(SRC, "Penguin_Kit.blend"),
                    os.path.join(PKG, "Source_Blender", "Penguin_Kit.blend")], check=True, capture_output=True)
    os.remove(script)

    stats = json.load(open(os.path.join(SRC, "props_stats.json")))
    shutil.copy2(os.path.join(SRC, "props_stats.json"), os.path.join(PKG, "Reference"))
    with open(os.path.join(PKG, "Reference", "props.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "size_cm", "triangles", "collision_hulls", "sockets", "materials", "pivot", "notes"])
        for name, s in stats.items():
            size = " x ".join(str(round(v)) for v in s["size_cm"]) if "size_cm" in s else s.get("kind", "")
            notes = s.get("note", "")
            if "exit_offset_cm" in s:
                notes = f"SOCKET_End at {tuple(round(v) for v in s['exit_offset_cm'])}, channel {s['inner_width_cm']:.0f} cm wide"
            if "doorway_cm" in s:
                notes = (f"room {s['interior_diameter_cm']:.0f} cm across and {s['interior_height_cm']:.0f} cm high, doorway "
                         f"{s['doorway_cm']['width']:.0f} x {s['doorway_cm']['height']:.0f} cm, bench {s['bench_height_cm']:.0f} cm")
            w.writerow([name + ".fbx", size, s["triangles"], s["collision_hulls"], " ".join(s["sockets"]),
                        " ".join(s["materials"]), s["pivot"], notes])

    guide = open(os.path.join(ROOT, "props", "IMPORT_GUIDE.md")).read()
    open(os.path.join(PKG, "IMPORT_GUIDE.md"), "w").write(guide)
    body = markdown.markdown(guide, extensions=["tables", "fenced_code"])
    hero = ('<p class="hero"><img src="Previews/Kit_Vignette.png" alt="a small level built from the kit"></p>'
            '<p class="hero"><img src="Previews/Kit_Sheet.png" alt="every piece in the kit"></p>'
            '<p class="hero"><img src="Previews/Igloo_Views.png" alt="the igloo outside, from the back and inside"></p>')
    body = body.replace("</h1>", "</h1>" + hero, 1)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Penguin Level Kit import guide</title>
<style>
:root{{--bg:#f8fafb;--fg:#1a1f24;--muted:#56606a;--line:#d9e0e6;--code:#e9eff3;--accent:#2b6a8a}}
@media (prefers-color-scheme: dark){{:root{{--bg:#161a1e;--fg:#e4eaef;--muted:#9aa6b0;--line:#323a42;--code:#222a31;--accent:#7cc0e0}}}}
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
        "PENGUIN LEVEL KIT for Unreal Engine 5\n\n"
        "Open IMPORT_GUIDE.html (or IMPORT_GUIDE.md) and follow Steps 1 to 6.\n\n"
        "Quick start:\n"
        "  1. Import Content/Textures. Normal_DX = Normalmap, ORM = Masks (no sRGB).\n"
        "  2. Build M_PenguinKit_Master and instances MI_Ice, MI_Snow, MI_Rock (guide, Step 3).\n"
        "  3. Import all of Content/Meshes as static meshes, scale 1, with UCX collision and sockets on,\n"
        "     auto-generated collision off.\n"
        "  4. Replace References: M_Ice -> MI_Ice, M_Snow -> MI_Snow, M_Rock -> MI_Rock.\n"
        "  5. Snap pieces on a 100 cm grid. Chain slide-chute pieces through SOCKET_End.\n\n"
        f"{len(stats)} meshes, centimetres, Z up. Folders: Content (import these), Reference (sizes,\n"
        "triangles, pivots, sockets), Previews (renders), Source_Blender (editable scene).\n")

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
