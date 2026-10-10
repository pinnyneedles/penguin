"""Hand-painted-style colour textures for Kai, in a flat, bright toon palette.

Every texel is coloured from its 3D position, normal and, for the face pieces, local coordinates, so the UV layout
can be anything. Lighting is left to the cel shader: the textures hold flat colours with a few soft accents (blush,
lash lines, stripes, stitches, glints in the eyes). NumPy and SciPy only.
"""
import math
import numpy as np
from scipy.ndimage import distance_transform_edt

import kai_geometry as G


def rgb(*c):
    return np.array(c, float) / 255.0


PAL = dict(
    skin=rgb(252, 206, 160), skin_shadow=rgb(236, 170, 130), blush=rgb(246, 150, 130), lash=rgb(52, 28, 22),
    hair=rgb(92, 52, 30), hair_hi=rgb(140, 86, 48), brow=rgb(70, 38, 22),
    mouth=rgb(118, 34, 30), tongue=rgb(228, 108, 100),
    white=rgb(252, 252, 247), white_shade=rgb(214, 224, 238), iris=rgb(36, 86, 150), iris_hi=rgb(92, 152, 212),
    iris_dark=rgb(14, 28, 62), pupil=rgb(12, 12, 20),
    tunic=rgb(212, 46, 40), navy=rgb(36, 60, 128), navy_dark=rgb(28, 52, 108), nail=rgb(255, 226, 206),
    pants=rgb(218, 182, 124), pants_dark=rgb(188, 150, 96), patch=rgb(104, 140, 92), stitch=rgb(250, 238, 210),
    sole=rgb(96, 58, 32), strap=rgb(150, 92, 48), strap_hi=rgb(184, 124, 70),
    wrap=rgb(240, 228, 200), wrap_line=rgb(200, 180, 140),
    sash=rgb(246, 184, 40), sash_edge=rgb(226, 120, 30), kerchief=rgb(252, 204, 64), kerchief_dark=rgb(226, 150, 34),
)

PIECES = dict(body=0, sclera=1, iris=2, lid_upper=3, lid_lower=4, brow=5, mouth=6)


def mix(a, b, t):
    t = np.asarray(t, float)
    if t.ndim == 1: t = t[:, None]
    return a * (1 - t) + b * t


def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# ---------------------------------------------------------------------------
# Rasteriser
# ---------------------------------------------------------------------------
def rasterize(tri_uv, tri_attr, N):
    """tri_uv (T,3,2) in 0..1; tri_attr (T,3,K). Returns pixel index (P,) and interpolated attributes (P,K)."""
    px = tri_uv * N
    out_i, out_a = [], []
    for k in range(len(px)):
        (x0, y0), (x1, y1), (x2, y2) = px[k]
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-12: continue
        xa, xb = max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), N - 1)
        ya, yb = max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), N - 1)
        X, Y = np.meshgrid(np.arange(xa, xb + 1) + 0.5, np.arange(ya, yb + 1) + 0.5)
        w0 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / d
        w1 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / d
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any(): continue
        A = tri_attr[k]
        out_i.append((Y[m] - 0.5).astype(np.int64) * N + (X[m] - 0.5).astype(np.int64))
        out_a.append((w0[m, None] * A[0] + w1[m, None] * A[1] + w2[m, None] * A[2]).astype(np.float32))
    return np.concatenate(out_i), np.concatenate(out_a)


def dilate(img, mask, pad=10):
    dist, (iy, ix) = distance_transform_edt(~mask, return_indices=True)
    fill = (~mask) & (dist <= pad)
    out = img.copy(); out[fill] = img[iy[fill], ix[fill]]
    return out


def bake(tri_uv, tri_attr, N, painter):
    """Paint a texture of size N: painter(attr (P,K)) -> sRGB colours (P,3). Returns uint8 (N,N,3), image top row first."""
    idx, attr = rasterize(tri_uv, tri_attr, N)
    idx, first = np.unique(idx, return_index=True)
    attr = attr[first]
    img = np.zeros((N * N, 3)); mask = np.zeros(N * N, bool)
    col = np.clip(painter(attr), 0, 1)
    img[idx] = col; mask[idx] = True
    img = dilate(img.reshape(N, N, 3), mask.reshape(N, N))
    return (np.flipud(img) * 255 + 0.5).astype(np.uint8)


# ---------------------------------------------------------------------------
# Painters. attr columns: P (3), N (3), piece (1), local (2)
# ---------------------------------------------------------------------------
def unpack(a):
    P = a[:, 0:3].astype(np.float64); Nn = a[:, 3:6].astype(np.float64)
    Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-9)
    piece = np.rint(a[:, 6]).astype(int); loc = a[:, 7:9].astype(np.float64)
    return P, Nn, piece, loc


def eye_coords(P, e):
    q = P - e["pivot"]
    return q @ e["u"] / e["a"], q @ e["v"] / e["b"], np.linalg.norm(q, axis=1) - e["R"]


def paint_head(a):
    P, Nn, piece, loc = unpack(a)
    col = np.tile(PAL["skin"], (len(P), 1))
    F = G.face_layout()
    body = piece == PIECES["body"]
    if body.any():
        Pb = P[body]; c = col[body]
        for side, s in G.SIDES:
            e = F["eyes"][side]
            x, y, depth = eye_coords(Pb, e)
            r = np.sqrt(x * x + y * y)
            # an inked upper lid: the top half of the opening's wall, and a line on the skin rim that is bold across
            # the top and tapers away by the middle of each side
            rim = depth > G.EYE["rim"] - 0.08
            th = 0.13 * sstep(-0.05, 0.6, y)
            line = (r < 1.0 + th) & (depth < G.EYE["rim"] + 0.4) & (y > -0.05) & (~rim | (r > 0.97))
            c[line] = mix(c[line], PAL["lash"], sstep(-0.05, 0.25, y[line]))
        # the hollow of each ear: a crisp, slightly darker oval on the bowl floor, so the ear reads in any light
        for side, s in G.SIDES:
            L = G.ear_local(Pb, s) / G.EAR_K
            (cu, cv), (ru, rv) = G.EAR_BOWL["c"], G.EAR_BOWL["r"]
            e = np.hypot((L[:, 0] - cu) / ru, (L[:, 1] - cv) / rv)
            near = (L[:, 2] > -0.2) & (L[:, 2] < 1.9) & (G.ear_zone(Pb, s) < 1.0)
            c[near] = mix(c[near], PAL["skin_shadow"], 0.6 * (1 - sstep(0.74, 0.8, e[near])))
        col[body] = c
    m = piece == PIECES["lid_upper"]
    if m.any():
        col[m] = mix(np.tile(PAL["skin"], (m.sum(), 1)), PAL["lash"], 1 - sstep(0.3, 0.45, loc[m, 1]))
    m = piece == PIECES["brow"]
    col[m] = PAL["brow"]
    return col


def paint_eye(a):
    """Eye whites and irises (their own material, so the eye colour is easy to change)."""
    P, Nn, piece, loc = unpack(a)
    col = np.tile(PAL["white"], (len(P), 1))
    m = piece == PIECES["sclera"]
    if m.any():
        col[m] = mix(col[m], PAL["white_shade"], sstep(0.45, 0.95, loc[m, 1]))      # the lid shades the top
    m = piece == PIECES["iris"]
    if m.any():
        x, y = loc[m, 0], loc[m, 1]
        r = np.sqrt(x * x + y * y)
        c = mix(np.tile(PAL["iris"], (m.sum(), 1)), PAL["iris_hi"], sstep(-0.1, -0.8, y) * 0.75)
        c = mix(c, PAL["iris_dark"], sstep(0.55, 0.0, y + 0.3) * sstep(0.2, 0.9, y) * 0.0 + sstep(0.15, 0.85, y) * 0.55)
        c = mix(c, PAL["iris_dark"], sstep(0.8, 0.9, r))                              # dark rim
        c = mix(c, PAL["pupil"], 1 - sstep(0.4, 0.46, np.sqrt((x / 0.92) ** 2 + ((y - 0.04) / 1.0) ** 2)))
        g1 = np.sqrt(((x + 0.32) / 0.26) ** 2 + ((y - 0.38) / 0.24) ** 2)
        g2 = np.sqrt(((x - 0.3) / 0.12) ** 2 + ((y + 0.42) / 0.11) ** 2)
        c = mix(c, PAL["white"], 1 - sstep(0.85, 1.0, np.minimum(g1, g2)))
        col[m] = c
    m = piece == PIECES["mouth"]
    if m.any():                                     # dark mouth with a tongue, laid out in (s, t) of the mouth shape
        s_, t_ = loc[m, 0], loc[m, 1]
        tongue = 1 - sstep(0.85, 1.0, np.sqrt((s_ / 0.62) ** 2 + (t_ / 0.48) ** 2))
        col[m] = mix(np.tile(PAL["mouth"], (m.sum(), 1)), PAL["tongue"], tongue)
    return col


def paint_hair(a):
    """Flat hair colour; the cel shader gives it its light and shade."""
    P, Nn, piece, loc = unpack(a)
    return np.tile(PAL["hair"], (len(P), 1))


def paint_skin(a):
    P, Nn, piece, loc = unpack(a)
    return np.tile(PAL["skin"], (len(P), 1))


def _closest(P, fns):
    D = np.column_stack([np.abs(f(P)) for f in fns])
    return np.argmin(D, axis=1), D


def paint_tunic(a):
    P, Nn, piece, loc = unpack(a)
    col = np.tile(PAL["tunic"], (len(P), 1))
    which, D = _closest(P, [G.tunic_sdf, G.collar_sdf])
    cloth = which == 0
    # navy band at the hem and at the sleeve ends, each with a thin navy line above
    col[cloth & (P[:, 2] < G.HEM_Z + 1.9)] = PAL["navy"]
    col[cloth & (np.abs(P[:, 2] - (G.HEM_Z + 2.35)) < 0.22)] = PAL["navy"]
    for side, s in G.SIDES:
        S, E, W, d2 = G.arm_points(s)
        d1 = G.nrm(E - S); end = S + d1 * 6.6
        along = (P - end) @ d1; near = np.linalg.norm(P - end, axis=1) < 5.5
        col[cloth & near & (along > -1.4)] = PAL["navy"]
        col[cloth & near & (np.abs(along + 1.85) < 0.2)] = PAL["navy"]
    # a striped undershirt shows in the V between the collar's lapels
    vx = np.abs(P[:, 0]) - 0.62 * (P[:, 2] - (G.Z["chest"] + 0.6))
    vee = cloth & (vx < 0) & (P[:, 1] < -2.0) & (P[:, 2] > G.Z["chest"] + 0.2)
    stripe = np.sin(P[:, 2] * math.pi / 0.55) > 0
    col[vee] = PAL["white"]; col[vee & stripe] = PAL["navy"]
    # sailor collar: navy with two white stripes along its outer edge
    cm = which == 1
    if cm.any():
        edge = -G.collar_region(P[cm])
        c = np.tile(PAL["navy"], (cm.sum(), 1))
        c[(np.abs(edge - 0.75) < 0.2) | (np.abs(edge - 1.35) < 0.2)] = PAL["white"]
        col[cm] = c
    return col


def paint_pants(a):
    P, Nn, piece, loc = unpack(a)
    col = np.tile(PAL["pants"], (len(P), 1))
    for side, s in G.SIDES:
        H, K, A, Bl, T = G.leg_points(s)
        C = G.cuff_point(s); ax = G.nrm(C - K)
        along = (P - C) @ ax
        cuff = (np.linalg.norm(P - C, axis=1) < 8.0) & (along > -1.8)
        col[cuff] = PAL["pants_dark"]
        col[cuff & (np.abs(along + 0.3) < 0.18)] = PAL["pants"]
    # a green patch with white stitches on Kai's right knee
    K = G.leg_points(-1)[1]
    q = P - (K + np.array([0, -4.6, 1.2]))
    inp = (np.abs(q[:, 0]) < 2.3) & (np.abs(q[:, 2]) < 2.1) & (Nn[:, 1] < -0.4)
    col[inp] = PAL["patch"]
    st = inp & ((np.abs(np.abs(q[:, 0]) - 1.95) < 0.14) | (np.abs(np.abs(q[:, 2]) - 1.75) < 0.14))
    st &= (np.sin((q[:, 0] + q[:, 2]) * 6.0) > -0.2)
    col[st] = PAL["stitch"]
    return col


def paint_sandals(a):
    """Feet (skin, with toenails) and sandals: dark sole with a light insole edge, leather straps with stitching."""
    P, Nn, piece, loc = unpack(a)
    col = np.tile(PAL["strap"], (len(P), 1))
    foot = np.minimum(G.foot_skin_sdf(P, 1.0), G.foot_skin_sdf(P, -1.0))
    sole = P[:, 2] < G.SOLE_TOP + 0.02
    skin = (np.abs(foot) < 0.12) & ~sole
    col[skin] = PAL["skin"]
    for s in (1.0, -1.0):
        for c, r in G.toe_points(s):
            nail = np.linalg.norm((P - (c + np.array([0, -r * 0.55, r * 0.55]))) / np.array([r * 0.55, r * 0.5, r * 0.6]), axis=1) < 1.0
            col[skin & nail & (Nn[:, 2] > 0.2)] = PAL["nail"]
    col[sole] = PAL["sole"]
    col[sole & (P[:, 2] > G.SOLE_TOP - 0.3)] = PAL["strap_hi"]
    strap = ~skin & ~sole
    edge = strap & (np.abs(foot - 0.25) > 0.18)
    col[strap & (np.sin((P[:, 0] + P[:, 1] * 1.3 + P[:, 2]) * 7.0) > 0.85) & ~edge] = PAL["strap_hi"]
    return col


def paint_sash(a):
    P, Nn, piece, loc = unpack(a)
    col = np.tile(PAL["sash"], (len(P), 1))
    zc = G.Z["waist"] - 1.2
    band = np.abs(P[:, 2] - zc) < 2.6
    col[band & (np.abs(np.abs(P[:, 2] - zc) - 1.75) < 0.25)] = PAL["sash_edge"]
    tails = P[:, 2] < zc - 3.0
    col[tails & (P[:, 2] < zc - 11.0)] = PAL["sash_edge"]
    return col


def paint_kerchief(a):
    P, Nn, piece, loc = unpack(a)
    col = np.tile(PAL["kerchief"], (len(P), 1))
    c = np.array([0, -8.2, G.Z["chest"] + 1.1])
    knot = np.linalg.norm((P - c) / np.array([2.0, 1.3, 1.6]), axis=1) < 1.05
    col[knot] = mix(col[knot], PAL["kerchief_dark"], 0.25)
    return col


PAINTERS = dict(head=paint_head, eye=paint_eye, hair_tousled=paint_hair, hair_spiky=paint_hair, arms=paint_skin,
                tunic=paint_tunic, pants=paint_pants, legs=paint_skin, sandals=paint_sandals, sash=paint_sash,
                neckerchief=paint_kerchief)
