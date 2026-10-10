#!/usr/bin/env python3
"""Assemble the Kai Unreal package: skeletal meshes, textures, import guide, reference data, previews and the Blender
source, zipped for dropping into a game project.

    python3 tools/build_kai.py --out kai
    python3 tools/render_kai.py kai --size 560 --only turnaround,closeup,parts,faces
    python3 tools/package_kai_unreal.py            # writes dist/Kai_Unreal.zip

Runs the clearance audit, the leg-pose clipping check and the FBX verification first, and stops if any of them fails.
"""
import csv, datetime, json, os, shutil, subprocess, sys, zipfile
import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
SRC = os.path.join(ROOT, "kai")
DIST = os.path.join(ROOT, "dist")
NAME = "Kai_Unreal"
PKG = os.path.join(DIST, NAME)
sys.path.insert(0, TOOLS)
import kai_geometry as G

PARTS = ["Head", "Hair_Tousled", "Hair_Spiky", "Arms", "Tunic", "Pants", "Legs", "Sandals", "Sash", "Neckerchief"]
PREVIEWS = {"Preview_Turnaround.png": "Preview_Turnaround.png", "Preview_Hero.png": "Preview_Hero.png",
            "Preview_Face.png": "Preview_Face.png", "Preview_Ears.png": "Preview_Ears.png", "Preview_Feet.png": "Preview_Feet.png",
            "Preview_Parts.png": "Preview_Parts.png", "Preview_Expressions.png": "Preview_Face_Controls.png"}
USED_FOR = {"Head": "head skin, ears, eyelids, brows", "Eye": "eye whites, irises and the mouth", "Hair_Tousled": "tousled hair",
            "Hair_Spiky": "spiky hair", "Arms": "arms and hands", "Tunic": "shirt and sailor collar", "Pants": "trousers",
            "Legs": "calves", "Sandals": "feet and sandals", "Sash": "sash", "Neckerchief": "neckerchief"}
# The packaged .blend looks for its textures in Content/Textures.
RELINK = r'''
import bpy, os, sys
src, dst = sys.argv[-2], sys.argv[-1]
bpy.ops.wm.open_mainfile(filepath=src)
for img in bpy.data.images:
    if img.filepath: img.filepath = "//../Content/Textures/" + os.path.basename(img.filepath)
bpy.ops.wm.save_as_mainfile(filepath=dst, relative_remap=False)
'''


def run_check(args, out_name):
    """Run a check script; keep its output as a report; stop if it fails."""
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, cwd=ROOT)
    lines = [l for l in r.stdout.splitlines() if l.strip() and not l.startswith(("Read blend", "Blender", "FBX version"))
             and "| Read blend" not in l]
    open(os.path.join(SRC, out_name), "w").write("\n".join(lines) + "\n")
    if r.returncode != 0:
        sys.exit(f"{args[0]} failed, see kai/{out_name}")
    print(lines[-1])


def role(name):
    if name == "root": return "root"
    if name.startswith("ik_"): return "IK goal (no skin, Mannequin convention)"
    if name.startswith(("eye", "eyelid", "brow")): return "face"
    if name.startswith(("hair", "sash", "collar", "neckerchief")): return "secondary motion"
    return "body"


def main():
    run_check([os.path.join(TOOLS, "kai_clearance.py")], "clearance_report.txt")
    run_check([os.path.join(TOOLS, "kai_pose_check.py"), SRC], "pose_check.txt")
    run_check([os.path.join(TOOLS, "verify_kai.py"), SRC], "verify_log.txt")

    if os.path.exists(PKG):
        shutil.rmtree(PKG)
    for sub in ("Content/Meshes", "Content/Textures", "Reference", "Previews", "Source_Blender"):
        os.makedirs(os.path.join(PKG, sub))
    cp = lambda f, sub, to=None: shutil.copy2(os.path.join(SRC, f), os.path.join(PKG, sub, to or f))
    cp("SK_Kai.fbx", "Content/Meshes")
    for p in PARTS:
        cp(f"SK_Kai_{p}.fbx", "Content/Meshes")
        cp(f"T_Kai_{p}_BaseColor.png", "Content/Textures")
    cp("T_Kai_Eye_BaseColor.png", "Content/Textures")
    script = os.path.join(DIST, "_relink_kai.py")
    open(script, "w").write(RELINK)
    subprocess.run([sys.executable, script, os.path.join(SRC, "Kai.blend"), os.path.join(PKG, "Source_Blender", "Kai.blend")],
                   check=True, capture_output=True)
    os.remove(script)
    for f, to in PREVIEWS.items():
        cp(f, "Previews", to)

    ref = os.path.join(PKG, "Reference")
    stats = json.load(open(os.path.join(SRC, "source_stats.json")))
    with open(os.path.join(ref, "bones.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["bone", "parent", "head_x_cm", "head_y_cm", "head_z_cm", "role"])
        for name, h, t, z, parent, deform in G.skeleton():
            w.writerow([name, parent or "", round(h[0], 2), round(h[1], 2), round(h[2], 2), role(name)])
    with open(os.path.join(ref, "parts.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "slot", "default_outfit", "vertices", "triangles", "materials", "bones_weighted", "max_influences"])
        for part, s in stats["parts"].items():
            w.writerow([part + ".fbx", s["slot"], "yes" if s["default_outfit"] else "no", s["vertices"], s["triangles"],
                        " ".join(s["materials"]), s["bones_weighted"], s["max_influences"]])
    with open(os.path.join(ref, "materials.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["slot", "texture", "used_for"])
        for p in ["Head", "Eye"] + PARTS[1:]:
            w.writerow([f"M_Kai_{p}", f"T_Kai_{p}_BaseColor", USED_FOR[p]])
        w.writerow(["toon shading", "", "two tones: shadow = base colour x (0.62, 0.56, 0.70); sun direction (-0.45, -0.62, 0.64)"])
    face = dict(
        eyelid_close_deg=stats["lid_close_deg"],
        eyelids="Rotate eyelid_upper_l/r about their local X by -upper degrees to close the eyes; eyelid_lower_l/r by "
                "+lower degrees closes the lower lid up to the middle of the eye (use part of it for squints).",
        eyes="eye_l and eye_r turn the eyeballs about their pivots; keep within about 20 degrees side to side, 12 up and down.",
        brows="brow_l and brow_r: move along local Z (about +1 cm) to raise, roll to tilt.",
        morph_targets=stats["shape_keys"],
        morph_target_mesh="SK_Kai_Head (and SK_Kai)")
    json.dump(face, open(os.path.join(ref, "face_rig.json"), "w"), indent=2)
    shutil.copy2(os.path.join(SRC, "source_stats.json"), os.path.join(ref, "mesh_stats.json"))
    shutil.copy2(os.path.join(SRC, "verify_report.json"), os.path.join(ref, "verify_report.json"))
    shutil.copy2(os.path.join(SRC, "clearance_report.txt"), os.path.join(ref, "clearance_report.txt"))
    shutil.copy2(os.path.join(SRC, "pose_check.txt"), os.path.join(ref, "pose_check.txt"))

    guide = open(os.path.join(SRC, "IMPORT_GUIDE.md")).read()
    open(os.path.join(PKG, "IMPORT_GUIDE.md"), "w").write(guide)
    body = markdown.markdown(guide, extensions=["tables", "fenced_code"])
    hero = ('<p class="hero"><img src="Previews/Preview_Turnaround.png" alt="Kai from five angles"></p>'
            '<p class="hero"><img src="Previews/Preview_Face.png" alt="face close-ups"></p>')
    body = body.replace("</h1>", "</h1>" + hero, 1)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Kai import guide</title>
<style>
:root{{--bg:#fbf9f8;--fg:#1f1b1a;--muted:#5f5752;--line:#e4dcd8;--code:#f2ebe8;--accent:#b8322a}}
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
        "KAI for Unreal Engine 5\n\n"
        "Open IMPORT_GUIDE.html (or IMPORT_GUIDE.md) and follow Steps 1 to 7.\n\n"
        "Quick start:\n"
        "  1. Import Content/Meshes/SK_Kai_Tunic.fbx as a Skeletal Mesh (new skeleton, scale 1, morph targets on,\n"
        "     import normals). Rename the skeleton SK_Kai_Skeleton.\n"
        "  2. Import the other SK_Kai_*.fbx parts onto SK_Kai_Skeleton (or just SK_Kai.fbx for one mesh).\n"
        "  3. Make a two-tone toon material and an instance per part with its T_Kai_*_BaseColor texture.\n"
        "  4. BP_Kai: capsule 52 / 20, mesh Z -52, yaw so he faces the arrow; add the parts and\n"
        "     Set Leader Pose Component on each.\n"
        "  5. Face: eyelid bones blink, eye bones look, five Mouth_* morph targets.\n\n"
        "Folders: Content (import these), Reference (bones, parts, materials, face rig, check reports),\n"
        "Previews (renders), Source_Blender (Kai.blend with a posing rig).\n")

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
