"""Tileable PBR texture sets for the penguin level kit (pure numpy, no Blender).

Each set returns linear base colour, a tangent-space normal map (OpenGL and DirectX) and an ORM map
(R = ambient occlusion, G = roughness, B = metallic), all (N, N, 3) floats in 0..1 that tile seamlessly.

    python3 tools/prop_textures.py out_dir [--size 1024]
"""
from __future__ import annotations
import os, sys
import numpy as np
from scipy.ndimage import zoom
from scipy.spatial import cKDTree


def _noise(rng, N, cells, amp=1.0, order=3):
    g = rng.standard_normal((cells, cells))
    return amp * zoom(g, N / cells, order=order, mode="grid-wrap", grid_mode=True)   # grid_mode keeps it truly periodic


def fbm(rng, N, base=4, octaves=6, gain=0.55):
    out = np.zeros((N, N)); a = 1.0; c = base
    for _ in range(octaves):
        if c > N: break
        out += _noise(rng, N, c, a); a *= gain; c *= 2
    return out / (np.abs(out).max() + 1e-9)


def voronoi(rng, N, count):
    """Periodic Voronoi: distance to nearest (F1) and second-nearest (F2) seed, in texels."""
    pts = rng.uniform(0, N, (count, 2))
    tiles = np.concatenate([pts + np.array([dx, dy]) * N for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    tree = cKDTree(tiles)
    yy, xx = np.mgrid[0:N, 0:N]
    d, _ = tree.query(np.stack([yy.ravel() + .5, xx.ravel() + .5], 1), k=2)
    return d[:, 0].reshape(N, N), d[:, 1].reshape(N, N)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def normals_from_height(H, strength):
    """Tileable tangent-space normals (OpenGL: +Y up). strength is tuned at 1024 px and scaled with the
    resolution so the bumps look the same at any texture size."""
    strength *= H.shape[0] / 1024
    hx = (np.roll(H, -1, 1) - np.roll(H, 1, 1)) / 2
    hy = (np.roll(H, -1, 0) - np.roll(H, 1, 0)) / 2
    n = np.stack([-strength * hx, -strength * hy, np.ones_like(H)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    gl = n * 0.5 + 0.5
    dx = gl.copy(); dx[..., 1] = 1 - dx[..., 1]
    return gl, dx


def ice(N=1024, seed=1):
    """Clear blue glacier ice: depth variation, white fracture lines, tiny bubbles, frosted patches."""
    rng = np.random.default_rng(seed)
    depth = fbm(rng, N, 3, 5)
    f1, f2 = voronoi(rng, N, 26)
    cracks = 1 - smoothstep(0.0, 2.2 * N / 1024, f2 - f1)              # thin fracture lines
    f1b, f2b = voronoi(rng, N, 90)
    fine = 1 - smoothstep(0.0, 1.2 * N / 1024, f2b - f1b)
    fine *= smoothstep(0.15, 0.6, fbm(rng, N, 6, 3))                    # only some fine cracks
    frost = smoothstep(0.25, 0.75, fbm(rng, N, 5, 5))
    bubbles = (rng.random((N, N)) > 0.9994).astype(float)                   # tiny trapped air bubbles
    deep = np.array([0.20, 0.45, 0.62]); light = np.array([0.62, 0.82, 0.92]); white = np.array([0.90, 0.96, 1.0])
    k = smoothstep(-0.6, 0.8, depth)
    col = deep * (1 - k[..., None]) + light * k[..., None]
    col = col * (1 - 0.35 * frost[..., None]) + white * 0.35 * frost[..., None]
    lines = np.clip(0.75 * cracks + 0.4 * fine + bubbles, 0, 1)
    col = col * (1 - lines[..., None]) + white * lines[..., None]
    rough = np.clip(0.06 + 0.30 * frost + 0.25 * lines, 0, 1)
    ao = 1 - 0.15 * cracks
    H = 0.6 * depth - 1.6 * cracks - 0.7 * fine + 0.25 * fbm(rng, N, 24, 4)
    gl, dx = normals_from_height(H, 3.0)
    return np.clip(col, 0, 1), gl, dx, np.stack([ao, rough, np.zeros_like(ao)], -1)


def snow(N=1024, seed=2):
    """Packed snow: soft drifts, fine grain, faint blue shadows, sparkle in the roughness."""
    rng = np.random.default_rng(seed)
    drift = fbm(rng, N, 3, 5)
    grain = fbm(rng, N, 64, 4)
    sparkle = (rng.random((N, N)) > 0.997).astype(float)
    base = np.array([0.86, 0.90, 0.95]); shade = np.array([0.70, 0.78, 0.88])
    k = smoothstep(-0.7, 0.6, drift)
    col = shade * (1 - k[..., None]) + base * k[..., None]
    col = col * (1 + 0.04 * grain[..., None])
    rough = np.clip(0.78 + 0.08 * grain - 0.55 * sparkle, 0, 1)
    ao = 0.92 + 0.08 * smoothstep(-0.5, 0.5, drift)
    H = 1.0 * drift + 0.35 * grain
    gl, dx = normals_from_height(H, 10.0)
    return np.clip(col, 0, 1), gl, dx, np.stack([ao, rough, np.zeros_like(ao)], -1)


def rock(N=1024, seed=3):
    """Dark volcanic rock: faceted plates, speckles, pale lichen spots."""
    rng = np.random.default_rng(seed)
    f1, f2 = voronoi(rng, N, 40)
    plates = smoothstep(0, 18 * N / 1024, f2 - f1)
    rough_n = fbm(rng, N, 8, 6)
    speck = (rng.random((N, N)) > 0.985).astype(float) * 0.6
    lichen = smoothstep(0.55, 0.8, fbm(rng, N, 10, 4)) * 0.5
    base = np.array([0.055, 0.055, 0.060]) * (1 + 0.35 * rough_n[..., None])
    col = base + speck[..., None] * 0.05
    col = col * (1 - lichen[..., None]) + np.array([0.32, 0.33, 0.27]) * lichen[..., None]
    rough = np.clip(0.78 + 0.1 * rough_n - 0.1 * lichen, 0, 1)
    ao = 0.75 + 0.25 * plates
    H = 1.2 * plates + 0.8 * rough_n
    gl, dx = normals_from_height(H, 2.2)
    return np.clip(col, 0, 1), gl, dx, np.stack([ao, rough, np.zeros_like(ao)], -1)


SETS = {"Ice": ice, "Snow": snow, "Rock": rock}


def to_srgb(c):
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def save_set(out, name, N=1024):
    from PIL import Image
    col, gl, dx, orm = SETS[name](N)
    os.makedirs(out, exist_ok=True)
    img = lambda a: Image.fromarray((np.flipud(np.clip(a, 0, 1)) * 255 + .5).astype(np.uint8))
    img(to_srgb(col)).save(os.path.join(out, f"T_{name}_BaseColor.png"))
    img(gl).save(os.path.join(out, f"T_{name}_Normal_GL.png"))
    img(dx).save(os.path.join(out, f"T_{name}_Normal_DX.png"))
    img(orm).save(os.path.join(out, f"T_{name}_ORM.png"))
    return col, gl, orm


if __name__ == "__main__":
    out = sys.argv[1]
    N = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 1024
    for n in SETS:
        save_set(out, n, N); print("wrote", n)
