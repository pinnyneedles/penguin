"""Geometry for the brown king-penguin-chick variant of Pebble (pure numpy, no Blender).

Everything is in metres, Blender axes: +Z up, character faces -Y, left side is +X.
The build script scales to centimetres when it creates the Blender objects.

Main pieces
  Profile        pear-shaped body + neck + head as a lofted surface of revolution with
                 per-height width, depth and forward offset.
  TuftField      overlapping teardrop-shaped down tufts that hang downward, laid out in
                 rows over the surface. Used for real mesh displacement AND, at the same
                 coordinates, for the base-colour texture, so paint and geometry line up.
  body_mesh()    dense adaptive grid of the profile, displaced by the tuft field.
  loft()/grid_solid()  helpers for the bill, toes, claws, webbing and flippers.
"""
from __future__ import annotations
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.ndimage import zoom

TAU = 2 * np.pi

# (z, half-width x, half-depth y, forward offset of the section centre; negative = forward)
CTRL = np.array([
    (0.100, 0.000, 0.000, -0.020),
    (0.110, 0.150, 0.140, -0.020),
    (0.150, 0.310, 0.290, -0.025),
    (0.220, 0.400, 0.370, -0.035),
    (0.320, 0.455, 0.415, -0.045),
    (0.450, 0.480, 0.435, -0.050),   # widest: the low, heavy belly of a chick
    (0.580, 0.470, 0.425, -0.045),
    (0.720, 0.430, 0.390, -0.035),
    (0.860, 0.365, 0.335, -0.025),
    (0.980, 0.290, 0.275, -0.020),
    (1.080, 0.230, 0.228, -0.025),   # neck
    (1.150, 0.218, 0.226, -0.035),
    (1.240, 0.232, 0.250, -0.050),   # head, slightly longer front to back
    (1.330, 0.228, 0.250, -0.055),
    (1.410, 0.196, 0.215, -0.050),
    (1.470, 0.140, 0.155, -0.045),
    (1.505, 0.070, 0.078, -0.040),
    (1.518, 0.000, 0.000, -0.040),
])


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


class Profile:
    def __init__(self, ctrl=CTRL):
        z, rx, ry, cy = ctrl.T
        rm = (rx + ry) / 2
        p = np.concatenate([[0], np.cumsum(np.hypot(np.diff(rm), np.diff(z)))])
        pp = np.linspace(0, p[-1], 40000)
        Z, RX, RY, CY = (CubicSpline(p, c)(pp) for c in (z, rx, ry, cy))
        RX = np.maximum(RX, 0); RY = np.maximum(RY, 0)
        RX[0] = RY[0] = RX[-1] = RY[-1] = 0
        RM = (RX + RY) / 2
        t = np.concatenate([[0], np.cumsum(np.hypot(np.diff(RM), np.diff(Z)))])
        self.t, self.Z, self.RX, self.RY, self.CY = t, Z, RX, RY, CY
        self.T = t[-1]
        i0, i1 = int(np.argmin(Z)), int(np.argmax(Z))
        self._zi = slice(i0, i1 + 1)

    def at(self, t):
        t = np.asarray(t, dtype=float)
        return tuple(np.interp(t, self.t, c) for c in (self.Z, self.RX, self.RY, self.CY))

    def t_at_z(self, z):
        s = self._zi
        return np.interp(z, self.Z[s], self.t[s])

    def point(self, a, t):
        z, rx, ry, cy = self.at(t)
        a = np.asarray(a, dtype=float)
        return np.stack([rx * np.sin(a), cy - ry * np.cos(a), z * np.ones_like(a)], axis=-1)

    def normal(self, a, t, eps=1e-4):
        a = np.asarray(a, dtype=float); t = np.asarray(t, dtype=float)
        pa = self.point(a + eps, t) - self.point(a - eps, t)
        pt = self.point(a, np.clip(t + eps, 0, self.T)) - self.point(a, np.clip(t - eps, 0, self.T))
        n = np.cross(pa, pt)
        ln = np.linalg.norm(n, axis=-1, keepdims=True)
        return n / np.maximum(ln, 1e-12)


def tuft_size(z):
    """Tuft width and length (m): long shaggy down on the body, short down on the head."""
    b = smoothstep((np.asarray(z) - 1.0) / 0.16)
    W = 0.11 * (1 - b) + 0.050 * b
    L = 0.17 * (1 - b) + 0.075 * b
    return W, L


class TuftField:
    def __init__(self, prof: Profile, seed=11):
        rng = np.random.default_rng(seed)
        rows = []
        t = 0.02
        while t < prof.T - 0.01:
            z, rx, ry, cy = prof.at(t)
            W, L = tuft_size(z)
            r = (rx + ry) / 2
            n = max(3, int(round(TAU * r / (0.75 * W))))
            phase = rng.uniform(0, 1)
            ang = (np.arange(n) + phase + rng.uniform(-0.3, 0.3, n)) / n * TAU - np.pi
            tc = t + rng.uniform(-0.15, 0.15, n) * L
            amp = rng.uniform(0.65, 1.15, n)
            rows.append((t, n, phase, ang, tc, amp))
            t += 0.5 * L
        K = len(rows); nmax = max(r[1] for r in rows)
        self.row_t = np.array([r[0] for r in rows])
        self.N = np.array([r[1] for r in rows]); self.PH = np.array([r[2] for r in rows])
        self.A = np.zeros((K, nmax)); self.TC = np.zeros((K, nmax)); self.AMP = np.zeros((K, nmax))
        for k, (_, n, _, ang, tc, amp) in enumerate(rows):
            self.A[k, :n] = ang; self.TC[k, :n] = tc; self.AMP[k, :n] = amp
        W, L = tuft_size(prof.at(self.TC)[0])
        jit = rng.uniform(0.78, 1.28, W.shape)
        self.W, self.L = W * jit, L * jit * rng.uniform(0.85, 1.2, W.shape)
        self.prof = prof
        self.count = int(self.N.sum())

    def __call__(self, a, t, p=6.0):
        a = np.asarray(a, dtype=float); t = np.asarray(t, dtype=float)
        z, rx, ry, cy = self.prof.at(t)
        r = (rx + ry) / 2
        K = len(self.row_t)
        k0 = np.searchsorted(self.row_t, t)
        acc = np.zeros_like(a)
        for dk in (-3, -2, -1, 0, 1):
            k = np.clip(k0 + dk, 0, K - 1)
            n = self.N[k]
            base = np.floor((a + np.pi) / TAU * n - self.PH[k]).astype(int)
            for di in (-1, 0, 1, 2):
                i = np.mod(base + di, n)
                du = (np.mod(a - self.A[k, i] + np.pi, TAU) - np.pi) * r
                dv = t - self.TC[k, i]
                x = du / (self.W[k, i] / 2); y = dv / (self.L[k, i] / 2)
                yy = np.clip(y, -1, 1)
                wp = np.sqrt(np.clip(1 - yy ** 2, 0, 1)) * (1 - 0.35 * np.clip(-yy, 0, 1)) + 1e-4
                thick = 0.2 + 0.8 * ((1 - yy) / 2) ** 0.8          # thickest toward the hanging tip
                h = thick * np.sqrt(np.clip(1 - (x / wp) ** 2, 0, 1))
                h = np.where(np.abs(y) < 1, h, 0.0) * self.AMP[k, i]
                acc += h ** p
        return acc ** (1 / p)


# Feature anchors shared by the body mask, the texture and the face parts.
BILL_Z = 1.215
EYE_Z = 1.300
EYE_A = 0.80


def anchors(prof: Profile):
    tb = prof.t_at_z(BILL_Z)
    bill_surface = prof.point(0.0, tb)
    te = prof.t_at_z(EYE_Z)
    eyes = {}
    for s, L in ((1, 'L'), (-1, 'R')):
        eyes[L] = (prof.point(s * EYE_A, te), prof.normal(s * EYE_A, te))
    return bill_surface, eyes


def displacement_amp(prof: Profile, P, z):
    """Down depth in metres: shaggy at the hem, full on the body, short on the head,
    almost bare around the bill base and eyes."""
    bill, eyes = anchors(prof)
    A = 0.024 + 0.010 * smoothstep((0.32 - z) / 0.18)
    head = smoothstep((z - 1.02) / 0.14)
    A = A * (1 - head) + 0.009 * head
    db = np.linalg.norm(P - bill, axis=-1)
    A *= 0.08 + 0.92 * smoothstep((db - 0.07) / 0.09)
    for E, _ in eyes.values():
        de = np.linalg.norm(P - E, axis=-1)
        A *= 0.25 + 0.75 * smoothstep((de - 0.035) / 0.05)
    return A


def ring_ts(prof: Profile, body_step=0.022, head_step=0.013):
    dz = smoothstep((prof.Z - 1.0) / 0.12)
    step = body_step * (1 - dz) + head_step * dz
    w = np.concatenate([[0], np.cumsum(np.diff(prof.t) / step[1:])])
    n = int(round(w[-1]))
    return np.interp(np.linspace(0, w[-1], n + 1), w, prof.t)


def body_mesh(prof: Profile, field: TuftField, seg=128):
    """Returns verts (m), faces, per-face UV lists, and the raw field values."""
    ts = ring_ts(prof)
    inner = ts[1:-1]
    a = -np.pi + np.arange(seg) * TAU / seg
    AA, TT = np.meshgrid(a, inner)                       # (rings, seg)
    P = prof.point(AA, TT)
    Nn = prof.normal(AA, TT)
    F = field(AA, TT)
    A = displacement_amp(prof, P, P[..., 2])
    Pd = P + Nn * (A * F)[..., None]
    verts = [tuple(v) for v in Pd.reshape(-1, 3)]
    bottom = len(verts); verts.append(tuple(prof.point(0.0, 0.0)))
    top = len(verts); verts.append(tuple(prof.point(0.0, prof.T)))
    R = len(inner)
    V = ts / prof.T
    faces, uvs = [], []
    for i in range(R - 1):
        for j in range(seg):
            nj = (j + 1) % seg
            faces.append((i * seg + j, i * seg + nj, (i + 1) * seg + nj, (i + 1) * seg + j))
            uvs.append([(j / seg, V[i + 1]), ((j + 1) / seg, V[i + 1]), ((j + 1) / seg, V[i + 2]), (j / seg, V[i + 2])])
    for j in range(seg):
        nj = (j + 1) % seg
        faces.append((bottom, nj, j)); uvs.append([((j + .5) / seg, 0.0), ((j + 1) / seg, V[1]), (j / seg, V[1])])
        b = (R - 1) * seg
        faces.append((b + j, b + nj, top)); uvs.append([(j / seg, V[-2]), ((j + 1) / seg, V[-2]), ((j + .5) / seg, 1.0)])
    return verts, faces, uvs, dict(rings=R + 2, seg=seg, tufts=field.count)


def body_texture(prof: Profile, field: TuftField, N=1024, seed=7):
    """Base colour (N, N, 3) in linear RGB; row 0 = v 0 (bottom). Matches body_mesh UVs."""
    rng = np.random.default_rng(seed)
    v = (np.arange(N) + 0.5) / N
    u = (np.arange(N) + 0.5) / N
    UU, VV = np.meshgrid(u, v)
    a = (UU - 0.5) * TAU
    t = VV * prof.T
    P = prof.point(a, t)
    z = P[..., 2]
    F = field(a, t)
    Fn = np.clip(F / np.percentile(F, 99), 0, 1)

    def octave(nx, ny, amp):
        g = rng.standard_normal((ny, nx))
        return amp * zoom(g, (N / ny, N / nx), order=3, mode='grid-wrap')
    strands = octave(512, 48, .5) + octave(1024, 128, .35) + octave(128, 24, .3)   # streaks along the down
    blotch = octave(8, 6, .5) + octave(24, 16, .3)
    front = (np.cos(a) + 1) / 2
    dark = np.array([.15, .078, .034]); light = np.array([.30, .165, .074])
    k = np.clip(front ** 1.3 * (1 - .35 * smoothstep((z - 1.15) / .3)) + .08 * blotch, 0, 1)
    rgb = dark * (1 - k[..., None]) + light * k[..., None]
    rgb = rgb * (0.58 + 0.55 * Fn ** 0.8)[..., None]                 # dark between tufts, lighter tips
    rgb = rgb * (1 + .20 * np.clip(strands, -1.5, 1.5))[..., None]
    rgb = rgb * (1 - .18 * smoothstep((.40 - z) / .25))[..., None]    # dusty hem
    bill, eyes = anchors(prof)
    db = np.linalg.norm(P - bill, axis=-1)
    fm = 0.8 * (1 - smoothstep((db - 0.05) / 0.07))                  # bare grey skin at the bill base
    skin = np.array([.11, .095, .085]) * (1 + .08 * np.clip(strands, -1.5, 1.5))[..., None]
    rgb = rgb * (1 - fm[..., None]) + skin * fm[..., None]
    for E, _ in eyes.values():
        de = np.linalg.norm(P - E, axis=-1)
        rgb *= (1 - .45 * (1 - smoothstep((de - .03) / .03)))[..., None]   # darker ring round the eye
    return np.clip(rgb, 0, 1)


# ---------------------------------------------------------------------------
# Lofting helpers
# ---------------------------------------------------------------------------
def _frames(C):
    T = np.gradient(C, axis=0); T /= np.linalg.norm(T, axis=1, keepdims=True)
    X = np.array([1.0, 0, 0])
    S = X - (T @ X)[:, None] * T
    bad = np.linalg.norm(S, axis=1) < 1e-6
    S[bad] = np.array([0, 1.0, 0])
    S /= np.linalg.norm(S, axis=1, keepdims=True)
    U = np.cross(T, S)
    flip = U[:, 2] < 0
    U[flip] *= -1; S[flip] *= -1
    return T, S, U


def loft(C, w, h, n=20, top_scale=1.0, bot_scale=1.0, lift=None, cap_start=True):
    """Tube along centreline C (k,3) with elliptical sections (half-width w, half-height h).
    top_scale/bot_scale squash the upper/lower half of each section. Last ring closes to a point."""
    C = np.asarray(C, float); k = len(C)
    T, S, U = _frames(C)
    th = np.arange(n) / n * TAU
    verts, faces = [], []
    for i in range(k):
        c = C[i] + (0 if lift is None else lift[i]) * U[i]
        for j in range(n):
            st = np.sin(th[j])
            hh = h[i] * (top_scale if st > 0 else bot_scale)
            verts.append(tuple(c + S[i] * w[i] * np.cos(th[j]) + U[i] * hh * st))
    for i in range(k - 1):
        for j in range(n):
            nj = (j + 1) % n
            faces.append((i * n + j, (i + 1) * n + j, (i + 1) * n + nj, i * n + nj))
    tip = len(verts); verts.append(tuple(C[-1] + T[-1] * 0.004))
    for j in range(n):
        faces.append(((k - 1) * n + j, tip, (k - 1) * n + (j + 1) % n))
    if cap_start:
        faces.append(tuple(reversed(range(n))))
    return verts, faces


def grid_solid(top, thickness):
    """Closed slab from a (nu, ns, 3) grid of top-surface points."""
    nu, ns, _ = top.shape
    bot = top - np.array([0, 0, thickness])
    verts = [tuple(p) for p in top.reshape(-1, 3)] + [tuple(p) for p in bot.reshape(-1, 3)]
    off = nu * ns
    idx = lambda i, j: i * ns + j
    faces = []
    for i in range(nu - 1):
        for j in range(ns - 1):
            q = (idx(i, j), idx(i, j + 1), idx(i + 1, j + 1), idx(i + 1, j))
            faces.append(q); faces.append(tuple(off + x for x in reversed(q)))
    ring = [(i, 0) for i in range(nu)] + [(nu - 1, j) for j in range(1, ns)] + \
           [(i, ns - 1) for i in range(nu - 2, -1, -1)] + [(0, j) for j in range(ns - 2, 0, -1)]
    for (i0, j0), (i1, j1) in zip(ring, ring[1:] + ring[:1]):
        a, b = idx(i0, j0), idx(i1, j1)
        faces.append((b, a, off + a, off + b))
    return verts, faces


def bill(prof: Profile, n=14, k=18, v2=False):
    """Long, slender, slightly decurved chick bill: upper and lower mandibles."""
    base_s = np.array(prof.point(0.0, prof.t_at_z(BILL_Z)))
    B = base_s + np.array([0, 0.035, 0])          # root sits inside the head
    if v2:
        return bill_v2(B, n=16, k=22)
    s = np.linspace(0, 1, k)
    Lb = 0.31
    up = B + np.stack([0 * s, -Lb * s, 0.018 * s - 0.040 * s ** 2.6], 1)
    w_up = 0.044 * (1 - s) ** 0.65 + 0.0015
    h_up = 0.041 * (1 - s) ** 0.70 + 0.0015
    upper = loft(up, w_up, h_up, n, top_scale=1.0, bot_scale=0.30, lift=0.004 * (1 - s))
    Ll = 0.93 * Lb
    lo = B + np.stack([0 * s, -Ll * s, -0.012 + 0.014 * s - 0.030 * s ** 2.6], 1)
    w_lo = 0.038 * (1 - s) ** 0.75 + 0.0015
    h_lo = 0.026 * (1 - s) ** 0.75 + 0.0012
    lower = loft(lo, w_lo, h_lo, n, top_scale=0.28, bot_scale=1.0, lift=-0.006 * (1 - s))
    return upper, lower


def foot_parts(side, n=10, k=12, v2=False):
    """Three splayed toes with knuckles and hooked claws, plus two webs between them."""
    if v2:
        return foot_parts_v2(side)
    cx = side * 0.226
    pad = np.array([cx, -0.045, 0.038])
    toes, claws, cls = [], [], []
    for base_ang, length in ((-0.48, 0.19), (0.0, 0.225), (0.48, 0.18)):
        phi = side * (base_ang + 0.14)                     # toes point slightly outward
        d = np.array([np.sin(phi), -np.cos(phi), 0.0])
        s = np.linspace(0, 1, k)
        C = pad + np.outer(s * length, d) + np.stack([0 * s, 0 * s, 0.010 * np.sin(np.pi * s) - 0.014 * s], 1)
        r = 0.038 * (1 - 0.45 * s) * (1 + 0.08 * np.sin(3 * np.pi * s) ** 2)
        cls.append(C)
        toes.append(loft(C, r, r * 0.80, n, bot_scale=0.75, cap_start=True))
        tip = C[-1] - d * 0.012; m = 6; c = np.linspace(0, 1, m)
        CC = tip + np.outer(c * 0.042, d) + np.stack([0 * c, 0 * c, -0.018 * c ** 1.6 + 0.003 * c], 1)
        rc = 0.0135 * (1 - c) ** 0.9 + 0.0008
        claws.append(loft(CC, rc, rc * 1.1, 8, cap_start=True))
    webs = []
    for a, b in ((0, 1), (1, 2)):
        nu, ns = 8, 6
        sv = np.linspace(0, 1, ns)
        top = np.zeros((nu, ns, 3))
        for jj, sw in enumerate(sv):
            umax = 0.93 - 0.16 * np.sin(np.pi * sw)          # webbing almost to the claws, gently scalloped
            uu = np.linspace(0.05, umax, nu)
            ia = np.interp(uu, np.linspace(0, 1, len(cls[a])), np.arange(len(cls[a])))
            pa = np.array([np.interp(ia, np.arange(len(cls[a])), cls[a][:, q]) for q in range(3)]).T
            pb = np.array([np.interp(ia, np.arange(len(cls[b])), cls[b][:, q]) for q in range(3)]).T
            top[:, jj] = pa * (1 - sw) + pb * sw
        top[..., 2] = top[..., 2] - 0.006
        webs.append(grid_solid(top, 0.013))
    return toes, claws, webs


def flipper_centres(prof: Profile, side, k=10):
    """Flipper hangs along the side of the body, flat against the down, slightly off at the tip."""
    zs = np.linspace(0.985, 0.40, k)
    ts = prof.t_at_z(zs)
    z, rx, ry, cy = prof.at(ts)
    off = 0.016 + 0.040 * ((0.985 - zs) / 0.585) ** 1.6
    x = side * (rx + off)
    y = cy + 0.025 + 0.035 * (0.985 - zs) / 0.585
    widths = np.array([.030, .058, .074, .080, .080, .076, .068, .054, .032, .004])
    return np.stack([x, y, zs], 1), widths


# ---------------------------------------------------------------------------
# Iteration 2 candidates: ridged bill with gape, almond eyelids, paddle feet
# ---------------------------------------------------------------------------
def loft_shaped(C, w, h, n, shape):
    """Like loft(), but the section is given by shape(theta) -> (sx, sy) multipliers per ring index."""
    C = np.asarray(C, float); k = len(C)
    T, S, U = _frames(C)
    verts, faces = [], []
    for i in range(k):
        for j in range(n):
            sx, sy = shape(j / n * TAU, i / (k - 1))
            verts.append(tuple(C[i] + S[i] * w[i] * sx + U[i] * h[i] * sy))
    for i in range(k - 1):
        for j in range(n):
            nj = (j + 1) % n
            faces.append((i * n + j, (i + 1) * n + j, (i + 1) * n + nj, i * n + nj))
    tip = len(verts); verts.append(tuple(C[-1] + T[-1] * 0.004))
    for j in range(n):
        faces.append(((k - 1) * n + j, tip, (k - 1) * n + (j + 1) % n))
    faces.append(tuple(reversed(range(n))))
    return verts, faces


def bill_v2(B, n=16, k=22):
    """Upper mandible with a culmen ridge and a tip that hooks just past the lower one;
    flat cutting edges meeting along a gape line that sweeps back and down at the base."""
    s = np.linspace(0, 1, k)
    Lb = 0.335
    up = B + np.stack([0 * s, -Lb * s, 0.020 * s - 0.050 * s ** 2.4], 1)
    w_up = 0.045 * (1 - s) ** 0.62 + 0.0012
    h_up = 0.042 * (1 - s) ** 0.66 + 0.0012

    def up_shape(th, u):
        c, sn = np.cos(th), np.sin(th)
        if sn > 0:      # upper half: narrow toward a rounded ridge
            return c * (1 - 0.32 * sn ** 2), sn * (1 + 0.10 * sn ** 6)
        return c, 0.26 * sn           # flat-ish tomium underneath
    upper = loft_shaped(up, w_up, h_up, n, up_shape)

    Ll = 0.90 * Lb
    lo = B + np.stack([0 * s, -Ll * s, -0.013 + 0.014 * s - 0.032 * s ** 2.4], 1)
    w_lo = 0.039 * (1 - s) ** 0.72 + 0.0012
    h_lo = 0.027 * (1 - s) ** 0.72 + 0.0010

    def lo_shape(th, u):
        c, sn = np.cos(th), np.sin(th)
        if sn > 0:
            return c, 0.24 * sn
        return c * (1 - 0.18 * sn ** 2), sn
    lower = loft_shaped(lo, w_lo, h_lo, n, lo_shape)
    return upper, lower


def eyelids(P, nrm, ax=0.037, ay=0.026, tilt=0.12, n=8, k=40):
    """One continuous almond-shaped lid rim of bare skin hugging the eye: pointed front and back
    corners, a fuller (slightly hooded) upper lid and a thinner lower lid, with no gaps."""
    P = np.asarray(P, float); nrm = np.asarray(nrm, float); nrm = nrm / np.linalg.norm(nrm)
    up = np.array([0, 0, 1.0]); fwd = np.cross(nrm, up); fwd /= np.linalg.norm(fwd)
    if fwd[1] > 0: fwd = -fwd                  # fwd points toward the bill (-Y)
    vv = up - nrm * (up @ nrm); vv /= np.linalg.norm(vv)
    ct, st = np.cos(tilt), np.sin(tilt)
    X = ct * fwd - st * vv; Y = st * fwd + ct * vv      # front corner sits a little lower
    O = P - nrm * 0.004
    th = np.arange(k) / k * TAU
    sn = np.sin(th)
    C = O[None] + np.outer(ax * np.cos(th), X) + np.outer(ay * sn * (0.72 + 0.28 * np.abs(sn)), Y)
    r = 0.0036 + 0.0032 * np.clip(sn, 0, 1) ** 1.5 + 0.0006 * np.clip(-sn, 0, 1)
    lift = 0.0012 * np.clip(sn, 0, 1)
    verts, faces = [], []
    for i in range(k):
        rd = C[i] - O; rd -= nrm * (rd @ nrm); rd /= np.linalg.norm(rd)
        for j in range(n):
            ph = j / n * TAU
            verts.append(tuple(C[i] + rd * r[i] * np.cos(ph) + nrm * (r[i] * 0.85 * np.sin(ph) + lift[i])))
    for i in range(k):
        i2 = (i + 1) % k
        for j in range(n):
            nj = (j + 1) % n
            faces.append((i * n + j, i * n + nj, i2 * n + nj, i2 * n + j))
    return [(verts, faces)]


def foot_parts_v2(side, n=10, k=12):
    """Baseline toes (smooth taper into the claw) with two targeted changes: the webbing is raised
    to the toe centre-line and thickened so the foot reads as a paddle, and the claws are shorter,
    more hooked and set into the toe tip."""
    cx = side * 0.226
    pad = np.array([cx, -0.045, 0.038])
    toes, claws, cls = [], [], []
    for base_ang, length in ((-0.48, 0.19), (0.0, 0.225), (0.48, 0.18)):
        phi = side * (base_ang + 0.14)
        d = np.array([np.sin(phi), -np.cos(phi), 0.0])
        s = np.linspace(0, 1, k)
        C = pad + np.outer(s * length, d) + np.stack([0 * s, 0 * s, 0.010 * np.sin(np.pi * s) - 0.014 * s], 1)
        r = 0.038 * (1 - 0.45 * s) * (1 + 0.08 * np.sin(3 * np.pi * s) ** 2)
        cls.append(C)
        toes.append(loft(C, r, r * 0.80, n, bot_scale=0.75, cap_start=True))
        tip = C[-1] - d * 0.020 + np.array([0, 0, 0.002]); m = 7; c = np.linspace(0, 1, m)
        CC = tip + np.outer(c * 0.044, d) + np.stack([0 * c, 0 * c, -0.024 * c ** 1.8 + 0.006 * c], 1)
        rc = 0.0122 * (1 - c) ** 0.85 + 0.0008      # narrower than the toe's underside, so no lump
        claws.append(loft(CC, rc, rc * 1.1, 8, cap_start=True))
    webs = []
    for a, b in ((0, 1), (1, 2)):
        nu, ns = 8, 6
        sv = np.linspace(0, 1, ns)
        top = np.zeros((nu, ns, 3))
        for jj, sw in enumerate(sv):
            umax = 0.93 - 0.16 * np.sin(np.pi * sw)
            uu = np.linspace(0.05, umax, nu)
            ia = np.interp(uu, np.linspace(0, 1, len(cls[a])), np.arange(len(cls[a])))
            pa = np.array([np.interp(ia, np.arange(len(cls[a])), cls[a][:, q]) for q in range(3)]).T
            pb = np.array([np.interp(ia, np.arange(len(cls[b])), cls[b][:, q]) for q in range(3)]).T
            top[:, jj] = pa * (1 - sw) + pb * sw
        top[..., 2] = top[..., 2] + 0.006
        webs.append(grid_solid(top, 0.018))
    return toes, claws, webs
