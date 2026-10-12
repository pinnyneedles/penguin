#!/usr/bin/env python3
"""Assemble the boat's Unreal package: static meshes with collision and sockets, Kai's driving animations, textures,
the import and Blueprint guide, reference data, previews and the Blender sources, zipped.

    python3 tools/build_boat.py --out boat
    python3 tools/render_boat.py boat --only hero,turnaround,motor,steer
    python3 tools/kai_boat_pose.py            # Kai's driving poses (needs kai/Kai.blend), then:
    python3 tools/render_boat.py boat --only driving
    python3 tools/package_boat_unreal.py      # writes dist/Boat_Unreal.zip

Runs the driving-pose checks, the physics simulation and the FBX verification first, and stops if any of them fails.
"""
import csv, datetime, json, os, shutil, subprocess, sys, zipfile
import markdown
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
SRC = os.path.join(ROOT, "boat")
DIST = os.path.join(ROOT, "dist")
NAME = "Boat_Unreal"
PKG = os.path.join(DIST, NAME)
sys.path.insert(0, TOOLS)
import boat_geometry as B

MESHES = ["SM_Boat_Hull", "SM_Boat_Motor", "SM_Boat_Propeller", "SM_Boat_Wheel"]
ANIMS = ["AN_Kai_Boat_Drive", "AN_Kai_Boat_Steer_Left", "AN_Kai_Boat_Steer_Left_Half", "AN_Kai_Boat_Steer_Right_Half",
         "AN_Kai_Boat_Steer_Right"]
PREVIEWS = ["Preview_Kai_Driving.png", "Preview_Kai_Steering.png", "Preview_Kai_Driving_Closeup.png",
            "Preview_Boat_Hero.png", "Preview_Boat_Turnaround.png", "Preview_Boat_Motor.png",
            "Preview_Boat_Steering.png", "Preview_Boat_Physics.png"]
RELINK = r'''
import bpy, os, sys
src, dst = sys.argv[-2], sys.argv[-1]
bpy.ops.wm.open_mainfile(filepath=src)
for img in bpy.data.images:
    if img.filepath and not img.packed_file: img.filepath = "//../Content/Textures/" + os.path.basename(img.filepath)
bpy.ops.wm.save_as_mainfile(filepath=dst, relative_remap=False)
'''


def run_check(args, out_name, ok_word):
    """Run a check script; keep its output as a report; stop if it fails."""
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True, cwd=ROOT)
    lines = [l for l in r.stdout.splitlines() if l.strip() and not l.startswith(("Read blend", "Blender", "FBX version"))
             and "| Read blend" not in l and "Info:" not in l and "export" not in l.lower()]
    open(os.path.join(SRC, out_name), "w").write("\n".join(lines) + "\n")
    if r.returncode != 0 or not any(ok_word in l for l in lines):
        sys.exit(f"{os.path.basename(args[0])} failed, see boat/{out_name}\n{r.stderr[-2000:]}")
    print(lines[-1])


def ue(v):
    """Blender (right-handed) to Unreal (left-handed): flip Y."""
    return [round(float(v[0]), 2) + 0.0, round(-float(v[1]), 2) + 0.0, round(float(v[2]), 2) + 0.0]


def main():
    run_check([os.path.join(TOOLS, "kai_boat_pose.py")], "driving_check.txt", "DRIVING_OK")
    run_check([os.path.join(TOOLS, "boat_sim.py"), SRC], "physics_check.txt", "SIM_OK")
    run_check([os.path.join(TOOLS, "verify_boat.py"), SRC], "verify_log.txt", "VERIFY_OK")

    # the guide's tuning values must be the simulated ones
    guide = open(os.path.join(SRC, "IMPORT_GUIDE.md")).read()
    plain = guide.replace("\u2212", "-")
    bp = json.load(open(os.path.join(SRC, "physics_tuning.json")))["blueprint"]
    for key, label in (("buoy_stiffness", "BuoyStiffness"), ("buoy_damping", "BuoyDamping"), ("thrust", "Thrust"),
                       ("drag_linear", "DragLinear"), ("drag_quadratic", "DragQuadratic"), ("side_drag", "SideDrag")):
        v = bp[key]; txt = f"{v:g}"
        if f"`{label}` | Float | {txt} |" not in plain: sys.exit(f"IMPORT_GUIDE.md: {label} should be {txt}")
    off = bp["com_offset_cm"]
    if f"X {off[0]:g}, Y 0, Z {off[2]:g}" not in plain: sys.exit(f"IMPORT_GUIDE.md: Center Of Mass Offset should be {off}")

    if os.path.exists(PKG):
        shutil.rmtree(PKG)
    for sub in ("Content/Meshes", "Content/Animations", "Content/Textures", "Reference", "Previews", "Source_Blender"):
        os.makedirs(os.path.join(PKG, sub))
    cp = lambda f, sub, to=None: shutil.copy2(os.path.join(SRC, f), os.path.join(PKG, sub, to or f))
    for m in MESHES:
        cp(m + ".fbx", "Content/Meshes"); cp(f"T_{m[3:]}_BaseColor.png", "Content/Textures")
    for a in ANIMS:
        cp(a + ".fbx", "Content/Animations")
    for p in PREVIEWS:
        cp(p, "Previews")
    script = os.path.join(DIST, "_relink_boat.py")
    open(script, "w").write(RELINK)
    for blend in ("Boat.blend", "Kai_Boat.blend"):
        subprocess.run([sys.executable, script, os.path.join(SRC, blend), os.path.join(PKG, "Source_Blender", blend)],
                       check=True, capture_output=True)
    os.remove(script)

    ref = os.path.join(PKG, "Reference")
    with open(os.path.join(ref, "sockets.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["mesh", "socket", "x_cm", "y_cm", "z_cm", "forward_x", "forward_y", "forward_z", "note"])
        for name, (loc, f, u) in B.sockets().items():
            w.writerow(["SM_Boat_Hull", name, *ue(loc), *ue(f), "Unreal coordinates, relative to the hull's origin"])
        for name, (loc, f, u) in B.motor_sockets().items():
            w.writerow(["SM_Boat_Motor", name, *ue(loc - B.MOTOR_PIVOT), *ue(f), "relative to the motor's pivot"])
    for f in ("physics_tuning.json", "driving_check.json", "verify_report.json", "driving_poses.json"):
        shutil.copy2(os.path.join(SRC, f), os.path.join(ref, f))
    shutil.copy2(os.path.join(SRC, "source_stats.json"), os.path.join(ref, "mesh_stats.json"))

    open(os.path.join(PKG, "IMPORT_GUIDE.md"), "w").write(guide)
    body = markdown.markdown(guide, extensions=["tables", "fenced_code"])
    hero = ('<p class="hero"><img src="Previews/Preview_Kai_Driving.png" alt="Kai driving his boat"></p>'
            '<p class="hero"><img src="Previews/Preview_Kai_Driving_Closeup.png" alt="Kai at the wheel"></p>')
    body = body.replace("</h1>", "</h1>" + hero, 1)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Kai's boat guide</title>
<style>
:root{{--bg:#f8fafc;--fg:#18202a;--muted:#55606e;--line:#dbe2ea;--code:#eaf0f6;--accent:#1f4f9a}}
@media (prefers-color-scheme: dark){{:root{{--bg:#12161c;--fg:#e6ebf1;--muted:#9aa6b4;--line:#2c3440;--code:#1d2430;--accent:#7fb0ff}}}}
body{{background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:24px 16px}}
main{{max-width:900px;margin:0 auto}} h1{{font-size:2rem;margin:.2em 0 .4em}} h2{{margin-top:2em;border-top:1px solid var(--line);padding-top:1em}}
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
        "KAI'S BOAT for Unreal Engine 5\n\n"
        "Open IMPORT_GUIDE.html (or IMPORT_GUIDE.md) and follow Steps 1 to 6. Import Kai first (Kai_Unreal.zip).\n\n"
        "Quick start:\n"
        "  1. Import Content/Meshes/*.fbx as Static Meshes: Auto Generate Collision off, One Convex Hull Per UCX on,\n"
        "     import normals, scale 1. The collision and sockets are in the files.\n"
        "  2. Import Content/Animations/*.fbx onto SK_Kai_Skeleton (animations only) and make the blend space\n"
        "     BS_Kai_Boat_Steer (Steer -1 .. 1).\n"
        "  3. Kai's Anim Blueprint: IsDriving and BoatSteer, Blend Poses by bool.\n"
        "  4. Enhanced Input: IA_Boat_Throttle, IA_Boat_Steer, IA_Boat_Exit in IMC_Boat; IA_Interact on Kai.\n"
        "  5. BP_KaiBoat (Pawn): hull simulates physics (150 kg), buoyancy at the Pontoon_* sockets, thrust at the\n"
        "     propeller, water drag; Kai attaches to Seat_Driver and the controller possesses the boat.\n\n"
        "Folders: Content (import these), Reference (sockets, physics tuning, check reports), Previews (renders),\n"
        "Source_Blender (Boat.blend, and Kai_Boat.blend with Kai seated at the wheel).\n")

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
