#!/usr/bin/env python3
"""Generate a stylized low-poly penguin mesh for Unreal Engine.

Outputs (into ./models):
  penguin.glb   - glTF binary, metres, Y-up (Unreal's glTF importer converts to cm / Z-up)
  penguin.obj   - Wavefront OBJ in centimetres, Z-up, +X forward, with penguin.mtl
  penguin_preview.png - quick render for eyeballing the result

The model is built in Unreal's own convention (centimetres, Z-up, +X forward,
feet resting on z = 0) and converted on export where a format needs it.

Run:  python3 tools/make_penguin.py
"""
from __future__ import annotations

import os
import numpy as np
import trimesh
from trimesh.visual.material import PBRMaterial

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

# ---------------------------------------------------------------------------
# Palette (linear RGBA 0-255)
# ---------------------------------------------------------------------------
COLORS = {
    "PenguinBody":  (24, 26, 32, 255),      # near-black feathers
    "PenguinBelly": (245, 245, 240, 255),   # off-white belly / face
    "PenguinBeak":  (240, 150, 40, 255),    # orange beak and feet
    "PenguinEye":   (250, 250, 250, 255),   # eye white
    "PenguinPupil": (10, 10, 12, 255),      # pupil
}


def mat(name: str) -> PBRMaterial:
    c = np.array(COLORS[name], dtype=np.float64) / 255.0
    m = PBRMaterial(name=name, baseColorFactor=c, metallicFactor=0.0,
                    roughnessFactor=0.85 if name != "PenguinEye" else 0.3)
    return m


# ---------------------------------------------------------------------------
# Primitive helpers (all in cm, Z-up, +X forward)
# ---------------------------------------------------------------------------
def ellipsoid(radii, center, subdiv=3, rot=None) -> trimesh.Trimesh:
    m = trimesh.creation.icosphere(subdivisions=subdiv, radius=1.0)
    v = m.vertices * np.asarray(radii, dtype=float)
    if rot is not None:
        v = v @ rot.T
    m.vertices = v + np.asarray(center, dtype=float)
    return m


def rot_y(deg: float) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_x(deg: float) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_z(deg: float) -> np.ndarray:
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def cone(radius, height, center, axis_rot=None, sections=24) -> trimesh.Trimesh:
    """Cone with base at origin pointing +Z, then rotated/translated."""
    m = trimesh.creation.cone(radius=radius, height=height, sections=sections)
    v = m.vertices.copy()
    if axis_rot is not None:
        v = v @ axis_rot.T
    m.vertices = v + np.asarray(center, dtype=float)
    return m


# ---------------------------------------------------------------------------
# Build the penguin
# ---------------------------------------------------------------------------
def build_parts() -> dict[str, tuple[trimesh.Trimesh, str]]:
    parts: dict[str, tuple[trimesh.Trimesh, str]] = {}

    # Body: tall egg. Slightly squash the top so the head sits naturally.
    body = ellipsoid((19, 17, 26), (0, 0, 29), subdiv=3)
    # Give the egg a bit of taper: pull upper vertices inward.
    v = body.vertices
    t = np.clip((v[:, 2] - 29) / 26, 0, 1)
    scale = 1.0 - 0.18 * t ** 2
    v[:, 0] *= scale
    v[:, 1] *= scale
    body.vertices = v
    parts["Body"] = (body, "PenguinBody")

    # Head: sphere sitting on top of the body, nudged forward.
    head = ellipsoid((14, 13.5, 13), (2.5, 0, 53), subdiv=3)
    parts["Head"] = (head, "PenguinBody")

    # Belly: white ellipsoid pushed forward so it pokes out of the body.
    belly = ellipsoid((14, 13.5, 21), (6.5, 0, 27), subdiv=3)
    parts["Belly"] = (belly, "PenguinBelly")

    # Face patches: two white ovals on the front of the head.
    for side in (-1, 1):
        patch = ellipsoid((5.5, 5.0, 6.5), (11.0, side * 6.0, 55.0), subdiv=2,
                          rot=rot_z(side * 20))
        parts[f"Face_{'L' if side > 0 else 'R'}"] = (patch, "PenguinBelly")

    # Eyes
    for side in (-1, 1):
        eye = ellipsoid((2.6, 2.6, 2.6), (15.4, side * 5.4, 56.5), subdiv=2)
        pupil = ellipsoid((1.3, 1.3, 1.3), (17.4, side * 5.6, 56.8), subdiv=2)
        parts[f"Eye_{'L' if side > 0 else 'R'}"] = (eye, "PenguinEye")
        parts[f"Pupil_{'L' if side > 0 else 'R'}"] = (pupil, "PenguinPupil")

    # Beak: cone pointing +X, slightly flattened.
    beak = cone(radius=3.2, height=9.0, center=(13.5, 0, 52.0), axis_rot=rot_y(90))
    bv = beak.vertices
    bv[:, 2] = 52.0 + (bv[:, 2] - 52.0) * 0.7   # flatten vertically
    beak.vertices = bv
    parts["Beak"] = (beak, "PenguinBeak")

    # Flippers: flattened ellipsoids on each side, angled back and down.
    for side in (-1, 1):
        rot = rot_x(side * 14) @ rot_y(-12)
        flip = ellipsoid((5.5, 2.0, 15.0), (-1.0, side * 19.5, 29.0), subdiv=3, rot=rot)
        parts[f"Flipper_{'L' if side > 0 else 'R'}"] = (flip, "PenguinBody")

    # Tail: small flattened cone at the back, pointing -X and down.
    tail = cone(radius=4.5, height=10.0, center=(-9.0, 0, 11.0),
                axis_rot=rot_y(-110))
    parts["Tail"] = (tail, "PenguinBody")

    # Feet: orange flattened ellipsoids, toes splayed outward.
    for side in (-1, 1):
        foot = ellipsoid((9.0, 4.5, 2.0), (7.0, side * 7.5, 2.0), subdiv=2,
                         rot=rot_z(side * 15))
        parts[f"Foot_{'L' if side > 0 else 'R'}"] = (foot, "PenguinBeak")

    return parts


def assemble(parts) -> trimesh.Scene:
    scene = trimesh.Scene()
    for name, (mesh, mat_name) in parts.items():
        mesh = mesh.copy()
        mesh.visual = trimesh.visual.TextureVisuals(material=mat(mat_name))
        mesh.metadata["name"] = name
        scene.add_geometry(mesh, node_name=name, geom_name=name)
    return scene


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def export_glb(parts, path):
    """glTF: metres, Y-up. Rotate Z-up -> Y-up and scale cm -> m."""
    to_yup = rot_x(-90)
    scene = trimesh.Scene()
    for name, (mesh, mat_name) in parts.items():
        m = mesh.copy()
        m.vertices = (m.vertices @ to_yup.T) * 0.01
        m.visual = trimesh.visual.TextureVisuals(material=mat(mat_name))
        scene.add_geometry(m, node_name=name, geom_name=name)
    scene.export(path)


def export_obj(parts, path):
    """OBJ: centimetres, Z-up, +X forward, one group + material per part."""
    mtl_path = os.path.splitext(path)[0] + ".mtl"
    lines = [f"mtllib {os.path.basename(mtl_path)}"]
    offset = 1
    for name, (mesh, mat_name) in parts.items():
        mesh = mesh.copy()
        mesh.fix_normals()
        vn = mesh.vertex_normals
        lines.append(f"o {name}")
        lines.append(f"g {name}")
        lines.append(f"usemtl {mat_name}")
        for p in mesh.vertices:
            lines.append(f"v {p[0]:.4f} {p[1]:.4f} {p[2]:.4f}")
        for n in vn:
            lines.append(f"vn {n[0]:.4f} {n[1]:.4f} {n[2]:.4f}")
        for f in mesh.faces:
            a, b, c = (f + offset)
            lines.append(f"f {a}//{a} {b}//{b} {c}//{c}")
        offset += len(mesh.vertices)
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")

    mtl = []
    for name, rgba in COLORS.items():
        r, g, b = (x / 255.0 for x in rgba[:3])
        mtl += [f"newmtl {name}", f"Kd {r:.4f} {g:.4f} {b:.4f}",
                "Ka 0 0 0", "Ks 0.05 0.05 0.05", "Ns 10", "d 1", "illum 2", ""]
    with open(mtl_path, "w") as fh:
        fh.write("\n".join(mtl))


def _raster(tris, cols, R, size=560, pad=1.1):
    """Tiny orthographic z-buffer rasteriser (flat shaded) -> HxWx3 float image."""
    light = np.array([-0.45, -0.55, 0.70]); light /= np.linalg.norm(light)
    img = np.ones((size, size, 3)) * np.array([0.93, 0.95, 0.97])
    zbuf = np.full((size, size), -np.inf)
    v = tris @ R.T                      # camera space: x right, y up, z toward viewer
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    nl = np.linalg.norm(n, axis=1, keepdims=True); n = n / np.maximum(nl, 1e-9)
    shade = cols * (0.30 + 0.70 * np.clip(n @ (R @ light), 0, 1))[:, None]
    allxy = v[:, :, :2].reshape(-1, 2)
    c = (allxy.max(0) + allxy.min(0)) / 2
    half = (allxy.max(0) - allxy.min(0)).max() / 2 * pad
    px = (v[:, :, 0] - c[0]) / half * (size / 2) + size / 2
    py = size / 2 - (v[:, :, 1] - c[1]) / half * (size / 2)
    pz = v[:, :, 2]
    order = np.argsort(-pz.mean(1))[::-1]  # far to near (z-buffer makes this optional)
    for i in order:
        if n[i, 2] <= 0:
            continue                      # back-face cull
        x0, x1 = int(np.floor(px[i].min())), int(np.ceil(px[i].max()))
        y0, y1 = int(np.floor(py[i].min())), int(np.ceil(py[i].max()))
        x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = zip(px[i], py[i])
        det = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(det) < 1e-9:
            continue
        w0 = ((bx - xs) * (cy - ys) - (cx - xs) * (by - ys)) / det
        w1 = ((cx - xs) * (ay - ys) - (ax - xs) * (cy - ys)) / det
        w2 = 1 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        z = w0 * pz[i, 0] + w1 * pz[i, 1] + w2 * pz[i, 2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        upd = inside & (z > sub)
        sub[upd] = z[upd]
        img[y0:y1 + 1, x0:x1 + 1][upd] = shade[i]
    return img


def render_preview(parts, path):
    from PIL import Image
    tris = np.vstack([m.vertices[m.faces] for m, _ in parts.values()])
    cols = np.vstack([np.repeat([np.array(COLORS[k][:3]) / 255.0], len(m.faces), 0)
                      for m, k in parts.values()])
    # world: Z-up, +X forward.  Camera basis rows = (right, up, toward-viewer).
    def cam(yaw_deg, pitch_deg):
        yaw, pitch = np.radians(yaw_deg), np.radians(pitch_deg)
        fwd = np.array([np.cos(pitch) * np.cos(yaw), np.cos(pitch) * np.sin(yaw), np.sin(pitch)])
        right = np.cross(np.array([0, 0, 1.0]), fwd); right /= np.linalg.norm(right)
        up = np.cross(fwd, right)
        return np.vstack([right, up, fwd])
    views = [cam(-35, 18), cam(0, 5), cam(-90, 10), cam(180, 15)]
    frames = [_raster(tris, cols, R) for R in views]
    strip = (np.hstack(frames) * 255).astype(np.uint8)
    Image.fromarray(strip).save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    parts = build_parts()

    glb = os.path.join(OUT, "penguin.glb")
    obj = os.path.join(OUT, "penguin.obj")
    png = os.path.join(OUT, "penguin_preview.png")
    export_glb(parts, glb)
    export_obj(parts, obj)
    render_preview(parts, png)

    tris = sum(len(m.faces) for m, _ in parts.values())
    verts = sum(len(m.vertices) for m, _ in parts.values())
    allv = np.vstack([m.vertices for m, _ in parts.values()])
    lo, hi = allv.min(0), allv.max(0)
    print(f"parts: {len(parts)}  triangles: {tris}  vertices: {verts}")
    print(f"bounds (cm): x {lo[0]:.1f}..{hi[0]:.1f}  y {lo[1]:.1f}..{hi[1]:.1f}  z {lo[2]:.1f}..{hi[2]:.1f}")
    for p in (glb, obj, png):
        print("wrote", p, os.path.getsize(p), "bytes")


if __name__ == "__main__":
    main()
