"""Texture atlas for the crab (pure NumPy): pack the UV islands, rasterize the mesh into texture space and paint
colour, roughness and fine relief from each texel's 3D position and normal. Relief becomes a tangent-space
normal map (OpenGL and DirectX copies).
"""
from __future__ import annotations
import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree

KINDS = ["carapace_top", "carapace_bottom", "leg_upper", "leg_lower", "leg_tip", "claw_arm", "claw_wrist",
         "claw_hand", "claw_pincer", "eye_stalk", "joint", "antenna", "mouth", "eyeball", "abdomen", "joint_hip"]
KIND = {k: i for i, k in enumerate(KINDS)}


def kind_of(tile):
    if tile.startswith("leg"):
        return "leg_" + tile.split("_")[1]
    if tile.startswith("claw"):
        return tile.rsplit("_", 1)[0]          # claw_hand_L -> claw_hand
    return tile


# ---------------------------------------------------------------------------
# Island packing
# ---------------------------------------------------------------------------
def pack(sizes, N, pad=8):
    """sizes: {tile: (w_cm, h_cm)} -> {tile: (u0, v0, u1, v1)} with one shared texel density, shelf packed."""
    items = sorted(sizes.items(), key=lambda kv: -kv[1][1])
    def attempt(ppc):
        x = y = shelf = pad
        rects = {}
        for name, (w, h) in items:
            pw, ph = int(np.ceil(w * ppc)), int(np.ceil(h * ppc))
            if x + pw + pad > N:
                x = pad; y += shelf + pad; shelf = 0
            if pw + 2 * pad > N or y + ph + pad > N:
                return None
            rects[name] = (x, y, x + pw, y + ph); x += pw + pad; shelf = max(shelf, ph)
        return rects
    lo, hi = 0.1, 200.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if attempt(mid) is None: hi = mid
        else: lo = mid
    rects = attempt(lo)
    return {k: (x0 / N, y0 / N, x1 / N, y1 / N) for k, (x0, y0, x1, y1) in rects.items()}, lo


# ---------------------------------------------------------------------------
# Rasterization: per covered texel, interpolated corner attributes plus cm-per-texel along U and V
# ---------------------------------------------------------------------------
def rasterize(tri_uv, tri_attr, tri_kind, N):
    """tri_uv (T,3,2) in 0..1; tri_attr (T,3,K). Returns pixel index, attributes (P,K), kind (P,), scale (P,2)."""
    px = tri_uv * N
    out_i, out_a, out_k, out_s = [], [], [], []
    for k in range(len(px)):
        (x0, y0), (x1, y1), (x2, y2) = px[k]
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-10:
            continue
        xa, xb = max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), N - 1)
        ya, yb = max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), N - 1)
        X, Y = np.meshgrid(np.arange(xa, xb + 1) + 0.5, np.arange(ya, yb + 1) + 0.5)
        w0 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / d
        w1 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / d
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any():
            continue
        A = tri_attr[k]
        vals = w0[m, None] * A[0] + w1[m, None] * A[1] + w2[m, None] * A[2]
        out_i.append((Y[m] - 0.5).astype(np.int64) * N + (X[m] - 0.5).astype(np.int64))
        out_a.append(vals.astype(np.float32)); out_k.append(np.full(m.sum(), tri_kind[k], np.int16))
        # world cm per texel along +U and +V from this triangle's affine map
        e1, e2 = px[k][1] - px[k][0], px[k][2] - px[k][0]
        E1, E2 = A[1, :3] - A[0, :3], A[2, :3] - A[0, :3]
        det = e1[0] * e2[1] - e1[1] * e2[0]
        dPdx = (E1 * e2[1] - E2 * e1[1]) / det; dPdy = (E2 * e1[0] - E1 * e2[0]) / det
        out_s.append(np.repeat([[np.linalg.norm(dPdx), np.linalg.norm(dPdy)]], m.sum(), 0).astype(np.float32))
    return np.concatenate(out_i), np.concatenate(out_a), np.concatenate(out_k), np.concatenate(out_s)


def dilate(img, mask, pad=12):
    """Fill uncovered texels within pad of an island with the nearest covered value (stops mip bleeding)."""
    dist, (iy, ix) = distance_transform_edt(~mask, return_indices=True)
    fill = (~mask) & (dist <= pad)
    out = img.copy()
    out[fill] = img[iy[fill], ix[fill]]
    return out


# ---------------------------------------------------------------------------
# Noise
# ---------------------------------------------------------------------------
def _hash(ix, iy, iz, seed):
    n = (ix.astype(np.uint64) * np.uint64(73856093)) ^ (iy.astype(np.uint64) * np.uint64(19349663)) \
        ^ (iz.astype(np.uint64) * np.uint64(83492791)) ^ np.uint64(seed * 2654435761 % (1 << 32))
    n = (n ^ (n >> np.uint64(13))) * np.uint64(1274126177)
    n = n ^ (n >> np.uint64(16))
    return (n & np.uint64(0xFFFFFF)).astype(np.float64) / float(0xFFFFFF)


def vnoise(P, freq, seed=0):
    """Smooth value noise in -1..1 at points P (n,3), feature size 1/freq."""
    p = P * freq + 1000.0
    i = np.floor(p).astype(np.int64); f = p - i
    u = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (u[:, 0] if dx else 1 - u[:, 0]) * (u[:, 1] if dy else 1 - u[:, 1]) * (u[:, 2] if dz else 1 - u[:, 2])
                out = out + w * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
    return out * 2 - 1


def fbm(P, freq, octaves=4, seed=0, gain=0.5):
    out, a, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        out = out + a * vnoise(P, freq * 2 ** o, seed + o); tot += a; a *= gain
    return out / tot


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a * (1 - t) + b * t


def mix(a, b, t):
    t = np.asarray(t)[..., None] if np.ndim(t) else t
    return a * (1 - t) + b * t


# Linear colours
RED_DK = np.array([0.11, 0.008, 0.006])
RED = np.array([0.24, 0.012, 0.006])
ORANGE = np.array([0.46, 0.06, 0.012])
CREAM = np.array([0.66, 0.46, 0.25])
PALE = np.array([0.62, 0.26, 0.11])
JOINT = np.array([0.30, 0.05, 0.02])
KNUCKLE = np.array([0.34, 0.085, 0.035])
TIP = np.array([0.016, 0.011, 0.010])
EYE = np.array([0.008, 0.007, 0.008])


def tubercle_field(P, seeds, rng, r=(0.35, 0.75), h=(0.14, 0.32)):
    """Sum of round bumps centred on seed points; returns height (cm) and a 0..1 'on a bump' mask."""
    if len(seeds) == 0:
        return np.zeros(len(P)), np.zeros(len(P))
    rad = rng.uniform(*r, len(seeds)); hgt = rng.uniform(*h, len(seeds))
    tree = cKDTree(seeds)
    d, j = tree.query(P, k=min(6, len(seeds)))
    if d.ndim == 1: d, j = d[:, None], j[:, None]
    g = np.exp(-(d / rad[j]) ** 2)
    return (g * hgt[j]).sum(1), np.clip(g.max(1), 0, 1)


def paint(attr, kind, groove_fn, rim_s_fn, rng_seed=7):
    """attr columns: P(3) N(3) t u. Returns colour (P,3), roughness (P,), height in cm (P,)."""
    rng = np.random.default_rng(rng_seed)
    P, Nn, t, u = attr[:, :3].astype(np.float64), attr[:, 3:6].astype(np.float64), attr[:, 6].astype(np.float64), attr[:, 7].astype(np.float64)
    Nn = Nn / np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-6)
    n = len(P)
    col = np.zeros((n, 3)); rough = np.full(n, 0.45); hgt = 0.035 * fbm(P, 3.5, 3, seed=11)
    mott = fbm(P, 0.25, 4, seed=3)                       # broad mottling
    speck = vnoise(P, 2.6, seed=5)
    # the outer, upper side of every leg and claw is red; the inner, lower side is pale, like a real crab
    radial = P[:, :2] - np.array([0.0, 1.0]); radial /= np.maximum(np.linalg.norm(radial, axis=1, keepdims=True), 1e-6)
    outdir = np.column_stack([0.8 * radial, np.full(n, 0.6)])
    dorsal = smoothstep(-0.35, 0.35, np.sum(Nn * outdir, 1))
    K = {k: kind == KIND[k] for k in KINDS}

    # carapace top: dark red centre, brighter toward the margin, orange teeth, tubercles and speckles
    m = K["carapace_top"]
    if m.any():
        s = rim_s_fn(P[m])
        base = mix(RED_DK, RED, smoothstep(0.0, 0.85, s)) * (0.88 + 0.24 * mott[m, None])
        base = mix(base, ORANGE, smoothstep(0.9, 1.08, s) * 0.55)
        w = rng.random(m.sum()) < (0.00055 * (0.35 + smoothstep(0.3, 0.9, s)))
        th, onbump = tubercle_field(P[m], P[m][w], rng, h=(0.08, 0.2))
        base = mix(base, ORANGE * 0.8, np.clip(onbump * 1.3 - 0.35, 0, 1) * 0.25)
        base = mix(base, RED_DK * 0.55, smoothstep(0.55, 0.75, speck[m]) * 0.6)
        gd = groove_fn(P[m])
        base = mix(base, RED_DK * 0.7, np.exp(-(gd / 0.5) ** 2) * 0.15)
        col[m] = base
        hgt[m] += th - 0.09 * np.exp(-(gd / 0.45) ** 2)
        rough[m] = 0.52 + 0.08 * mott[m] - 0.05 * onbump

    # underside: cream, warmer near the rim, plate seams across the sternum
    m = K["carapace_bottom"]
    if m.any():
        s = rim_s_fn(P[m])
        rim = mix(RED, ORANGE, 0.15 + 0.2 * mott[m])
        base = mix(CREAM, rim, smoothstep(0.58, 0.86, s)) * (0.92 + 0.12 * mott[m, None])
        y = P[m, 1]
        seams = np.zeros(m.sum())
        for yc in (-8.0, -3.5, 1.0, 5.5, 10.0):
            seams = np.maximum(seams, np.exp(-((y - yc) / 0.35) ** 2) * smoothstep(0.75, 0.45, s))
        col[m] = mix(base, PALE * 0.7, seams * 0.5)
        hgt[m] += -0.12 * seams
        rough[m] = 0.62

    # walking legs: red on top with paler joints, cream underneath, dark pointed tips
    for kname in ("leg_upper", "leg_lower", "leg_tip"):
        m = K[kname]
        if not m.any(): continue
        top = mix(RED, ORANGE, 0.08 + 0.22 * mott[m]) * (0.85 + 0.2 * mott[m, None])
        band = np.maximum(smoothstep(0.16, 0.04, t[m]), smoothstep(0.84, 0.96, t[m]))
        top = mix(top, PALE, band * 0.3)                          # paler knuckles at both ends
        base = mix(CREAM, top, dorsal[m])
        if kname == "leg_tip":
            base = mix(base, TIP, smoothstep(0.45, 0.85, t[m]))
        col[m] = base
        ridge = np.exp(-((u[m] - 0.5) / 0.035) ** 2) + 0.6 * (np.exp(-((u[m] - 0.25) / 0.03) ** 2) + np.exp(-((u[m] - 0.75) / 0.03) ** 2))
        hgt[m] += 0.10 * ridge * (kname != "leg_tip")
        rough[m] = lerp(0.62, 0.5, dorsal[m]) - 0.16 * (kname == "leg_tip") * smoothstep(0.45, 0.85, t[m])

    # claws: bumpy red armour, cream underneath, black fingers
    for kname, black0, black1 in (("claw_arm", 9, 9), ("claw_wrist", 9, 9), ("claw_hand", 0.62, 0.80), ("claw_pincer", 0.30, 0.55)):
        m = K[kname]
        if not m.any(): continue
        top = mix(RED, ORANGE, 0.08 + 0.22 * mott[m]) * (0.85 + 0.2 * mott[m, None])
        pale = mix(RED, ORANGE * 0.8, 0.55)                       # claws are only a little paler underneath
        base = mix(pale, top, smoothstep(-0.85, -0.15, np.sum(Nn[m] * outdir[m], 1)))
        dens = 0.0045 if kname == "claw_hand" else 0.0025
        w = rng.random(m.sum()) < 0.6 * dens * smoothstep(-0.2, 0.5, Nn[m, 2]) * (t[m] < black0)
        th, onbump = tubercle_field(P[m], P[m][w], rng, r=(0.3, 0.6), h=(0.12, 0.26))
        base = mix(base, ORANGE * 0.85, np.clip(onbump * 1.4 - 0.4, 0, 1) * 0.3)
        blk = smoothstep(black0, black1, t[m]) if black0 < 5 else np.zeros(m.sum())
        col[m] = mix(base, TIP, blk)
        hgt[m] += th * (1 - blk)
        rough[m] = lerp(0.50, 0.30, blk) - 0.05 * onbump

    # abdomen flap: tan plates with seams between the segments
    m = K["abdomen"]
    if m.any():
        seg = np.abs(((t[m] - 0.08) * 6.0) % 1.0 - 0.5) > 0.44
        base = mix(CREAM, PALE, 0.25 + 0.25 * mott[m]) * (0.95 + 0.1 * mott[m, None])
        col[m] = mix(base, PALE * 0.6, seg * 0.6)
        hgt[m] += -0.15 * seg
        rough[m] = 0.6
    for kname, c, r_ in (("eye_stalk", RED * 1.2, 0.5), ("joint", KNUCKLE, 0.58), ("joint_hip", JOINT, 0.6),
                         ("antenna", ORANGE * 0.8, 0.5), ("mouth", mix(RED_DK, RED, 0.5), 0.55), ("eyeball", EYE, 0.08)):
        m = K[kname]
        if m.any():
            col[m] = c * (0.9 + 0.15 * mott[m, None]); rough[m] = r_
            if kname in ("joint", "joint_hip", "eyeball"): hgt[m] = 0.0
    return np.clip(col, 0, 1), np.clip(rough, 0.05, 1), hgt


def normals_from_height(H, scale_u, scale_v):
    """H (N,N) cm, scale_* cm per texel. Rows are V (bottom to top), columns U. OpenGL and DirectX maps."""
    dhu = (np.roll(H, -1, 1) - np.roll(H, 1, 1)) / (2 * np.maximum(scale_u, 1e-4))
    dhv = (np.roll(H, -1, 0) - np.roll(H, 1, 0)) / (2 * np.maximum(scale_v, 1e-4))
    n = np.stack([-dhu, -dhv, np.ones_like(H)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    gl = n * 0.5 + 0.5
    dx = gl.copy(); dx[..., 1] = 1 - dx[..., 1]
    return gl, dx


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)
