"""Geometry for Kai's boat: a small toon skiff with an outboard motor.

Units are centimetres. The boat's frame: +X toward the bow, +Y to port (left), +Z up. The origin is on the
centreline, at the bottom of the keel amidships. The hull is built from parametric surfaces (clean quads with
parametric UVs, so planks follow the hull); the outboard motor and propeller are signed distance functions meshed
like Kai's parts (see kai_geometry.polygonize).
"""
import math
import numpy as np

import kai_geometry as KG

XS, XB = -105.0, 80.0           # stern (transom) and bow tip: a short, chubby toon skiff
T = 3.2                         # hull planking thickness
U_BULK = 0.80                   # the foredeck covers the hull forward of here
FLOOR_Z = 7.0                   # top of the floorboards
WATERLINE = 5.0                 # design waterline (keel bottom = 0), below the floorboards so no water shows inside
SEAT = dict(driver=(XS + T + 0.2, -81.0, 22.0), middle=(2.0, 18.0, 22.0))   # (x from, x to, top z), sized for Kai
SEAT_T = 3.0                    # seat plank thickness
MOTOR_PIVOT = np.array([XS - 7.0, 0.0, 42.0])   # steering axis of the outboard (vertical through here)
STEER_MAX = 25.0                # degrees each way (outboard)
RAKE = 16.0                     # the stem leans forward this much at the gunwale


def _u(x):
    return (np.asarray(x, float) - XS) / (XB - XS)


def gunwale_w(x):
    """Half-width of the hull at the gunwale."""
    u = _u(x)
    aft = 44.0 + 12.0 * np.sin(0.5 * np.pi * np.clip(u / 0.38, 0, 1))
    fwd = 56.0 * np.sqrt(np.clip(1 - (np.clip(u - 0.38, 0, None) / 0.62) ** 2.4, 0, 1))
    return np.maximum(np.where(u <= 0.38, aft, fwd), 2.6)


def bottom_w(x):
    """Half-width of the flat of the bottom."""
    u = _u(x)
    aft = 34.0 + 3.0 * np.sin(0.5 * np.pi * np.clip(u / 0.35, 0, 1))
    fwd = 37.0 * np.sqrt(np.clip(1 - (np.clip(u - 0.35, 0, None) / 0.51) ** 2.2, 0, 1))
    return np.where(u <= 0.35, aft, fwd)


def keel_z(x):
    u = _u(x)
    return 24.0 * np.clip((u - 0.5) / 0.5, 0, None) ** 2.3


def sheer_z(x):
    u = _u(x)
    return np.where(u < 0.45, 35.0 + 2.0 * ((0.45 - u) / 0.45) ** 2, 35.0 + 28.0 * (np.clip(u - 0.45, 0, None) / 0.55) ** 2.2)


def _rake_amount(x):
    u = np.clip((np.asarray(x, float) - XS) / (XB - XS), 0, 1)
    t = np.clip((u - 0.6) / 0.4, 0, 1)
    return RAKE * t * t


def _height(x, z):
    zk = keel_z(x)
    return np.clip((z - zk) / np.maximum(sheer_z(x) - zk, 1e-6), 0, 1)


def rake(P):
    """Lean the bow forward: points move toward the bow in proportion to their height up the hull, so the stem
    rakes and the keel stays put. Applied to every finished hull piece (the parametric surfaces stay simple)."""
    Q = np.array(P, float)
    Q[..., 0] += _rake_amount(Q[..., 0]) * _height(Q[..., 0], Q[..., 2])
    return Q


def unrake(Q):
    """Inverse of rake (fixed-point iteration)."""
    P = np.array(Q, float); x = P[..., 0].copy()
    for _ in range(8):
        x = Q[..., 0] - _rake_amount(x) * _height(x, Q[..., 2])
    P[..., 0] = x
    return P


N_EXP = 3.0


def section(x, phi, inner=False):
    """Point on the hull at station x and section angle phi (0 = keel, pi/2 = gunwale), port side (y >= 0)."""
    x = np.asarray(x, float); phi = np.asarray(phi, float)
    zk, zs, wg, wb = keel_z(x), sheer_z(x), gunwale_w(x), bottom_w(x)
    if inner:
        zk = zk + T; wg = np.maximum(wg - T * 1.05, 0.4); wb = np.maximum(wb - T, 0.0)
    H = zs - zk
    s = np.sin(phi) ** (2 / N_EXP); c = np.cos(phi) ** (2 / N_EXP)
    z = zk + H * (1 - c)
    t = np.clip((z - zk) / H, 0, 1)
    W = wb + (wg - wb) * t ** 0.8
    return np.stack([x * np.ones_like(phi), W * s, z], -1)


def stations(x0, x1, n, bow_bias=1.0):
    t = np.linspace(0, 1, n)
    return x0 + (x1 - x0) * (1 - (1 - t) ** bow_bias)


# ---------------------------------------------------------------------------
# Mesh pieces (numpy). build_boat.py turns them into Blender meshes, unwraps and paints them by 3D position.
# ---------------------------------------------------------------------------
class Mesh:
    """Vertices and faces (quads and triangles) of one named piece of the boat."""

    def __init__(self, name):
        self.name, self.V, self.F = name, [], []

    def add(self, V, F):
        o = sum(len(v) for v in self.V)
        self.V.append(np.asarray(V, float))
        self.F += [[int(i) + o for i in f] for f in F]
        return self

    def arrays(self):
        return np.vstack(self.V), self.F


def grid(P, flip=False):
    """Quads over a (n, m, 3) grid of points."""
    n, m = P.shape[:2]
    idx = np.arange(n * m).reshape(n, m)
    F = []
    for i in range(n - 1):
        for j in range(m - 1):
            q = [idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]]
            F.append(q[::-1] if flip else q)
    return P.reshape(-1, 3), F


def mirror(P):
    Q = np.array(P, float); Q[..., 1] *= -1
    return Q


def fan(ring, center, flip=False):
    """Triangle fan closing a ring of points around a centre point."""
    V = np.vstack([ring, center[None]])
    c = len(ring)
    F = [[i, i + 1, c] for i in range(len(ring) - 1)]
    return V, [f[::-1] for f in F] if flip else F


def box(C):
    """Faces of a convex 8-corner block (corners: 4 at the first end, then 4 at the other, same winding), each
    wound to face outward."""
    C = np.asarray(C, float)
    F = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    c = C.mean(0); out = []
    for f in F:
        n = np.cross(C[f[1]] - C[f[0]], C[f[2]] - C[f[0]])
        out.append(f if n @ (C[f].mean(0) - c) > 0 else f[::-1])
    return C, out


# ---------------------------------------------------------------------------
# Hull pieces
# ---------------------------------------------------------------------------
NU, NPHI = 44, 15


def hull_outer():
    xs = stations(XS, XB, NU, 1.35)
    phis = np.linspace(0, np.pi / 2, NPHI)
    P = section(xs[:, None], phis[None, :])
    m = Mesh("outer")
    m.add(*grid(P, flip=True)); m.add(*grid(mirror(P)))
    ring = _ring(XB, False)                                     # the narrow stem face that closes the bow
    m.add(*fan(ring, np.array([XB, 0.0, 0.5 * (ring[0][2] + ring[NPHI - 1][2])])))
    return m


def hull_inner():
    x0, x1 = XS + T, XS + U_BULK * (XB - XS)
    xs = stations(x0, x1, 34)
    phis = np.linspace(0, np.pi / 2, NPHI)
    P = section(xs[:, None], phis[None, :], inner=True)
    m = Mesh("inner")
    m.add(*grid(P)); m.add(*grid(mirror(P), flip=True))
    return m


def rim():
    """Flat top of the planking between the outer and inner hull, from the transom to the foredeck."""
    xs = stations(XS, XS + U_BULK * (XB - XS), 34)
    zs = sheer_z(xs)
    out = np.stack([xs, gunwale_w(xs), zs], -1)
    inn = np.stack([xs, np.maximum(gunwale_w(xs) - T * 1.05, 0.4), zs], -1)
    P = np.stack([out, inn], 1)
    m = Mesh("rim")
    m.add(*grid(P, flip=True)); m.add(*grid(mirror(P)))
    return m


def _ring(x, inner):
    """Closed section ring at station x: starboard gunwale -> keel -> port gunwale -> back across the top."""
    phis = np.linspace(0, np.pi / 2, NPHI)
    half = section(np.full_like(phis, x), phis, inner=inner)
    ring = np.vstack([mirror(half)[::-1], half[1:]])
    return np.vstack([ring, ring[:1]])


def transom():
    """The flat stern: an outer face at XS and an inner face at XS + T, with a strip along the top between them."""
    m = Mesh("transom")
    for xx, inner, flip in ((XS, False, True), (XS + T, True, False)):
        ring = _ring(xx, inner)
        center = np.array([xx, 0.0, 0.5 * (ring[0][2] + ring[NPHI - 1][2])])
        m.add(*fan(ring, center, flip))
    ys = np.linspace(-1, 1, 12)
    zt = sheer_z(XS)
    wo, wi = gunwale_w(XS), max(gunwale_w(XS) - T * 1.05, 0.4)
    P = np.stack([np.stack([np.full_like(ys, XS), ys * wo, np.full_like(ys, zt)], -1),
                  np.stack([np.full_like(ys, XS + T), ys * wi, np.full_like(ys, zt)], -1)], 1)
    m.add(*grid(P, flip=True))
    return m


def foredeck():
    """Deck over the bow, from the bulkhead to the stem, slightly crowned."""
    x0 = XS + U_BULK * (XB - XS)
    xs = stations(x0, XB, 16)
    ys = np.linspace(-1, 1, 11)
    wg, zs = gunwale_w(xs), sheer_z(xs)
    P = np.stack([xs[:, None] + 0 * ys[None], wg[:, None] * ys[None], zs[:, None] + deck_crown(xs[:, None], ys[None])], -1)
    return Mesh("deck").add(*grid(P))


def deck_crown(x, yn):
    """Height of the foredeck's crown above the sheer at station x and fraction yn of the half-width."""
    return 1.2 * (1 - yn ** 2) * (gunwale_w(x) / 40)


def bulkhead():
    """Wall under the front edge of the foredeck, facing aft into the boat; its top follows the deck's crown."""
    xb = XS + U_BULK * (XB - XS)
    phis = np.linspace(0, np.pi / 2, NPHI)
    half = section(np.full_like(phis, xb), phis, inner=True)
    wg = float(gunwale_w(xb)); wi = half[-1][1]
    ys = np.linspace(wi, -wi, 13)[1:-1]
    top = np.stack([np.full_like(ys, xb), ys, float(sheer_z(xb)) + deck_crown(xb, ys / wg)], -1)
    ring = np.vstack([mirror(half)[::-1], half[1:], top, mirror(half)[-1:]])
    center = np.array([xb, 0.0, 0.5 * (FLOOR_Z + ring[0][2])])
    return Mesh("bulkhead").add(*fan(ring, center, True))


def inner_halfwidth_at(x, z, inner=True):
    """Inner (or outer) half-width of the hull at station x and height z."""
    phis = np.linspace(0, np.pi / 2, 400)
    S = section(np.full_like(phis, x), phis, inner=inner)
    i = int(np.clip(np.searchsorted(S[:, 2], z), 1, len(S) - 1))
    a, b = S[i - 1], S[i]
    t = (z - a[2]) / max(b[2] - a[2], 1e-9)
    return a[1] + t * (b[1] - a[1])


def fitted_plank(x0, x1, z0, z1, inset=0.3):
    """A plank from x0 to x1 and z0 to z1 whose ends follow the inside of the hull."""
    C = []
    for x in (x0, x1):
        w0, w1 = inner_halfwidth_at(x, z0) - inset, inner_halfwidth_at(x, z1) - inset
        C += [(x, -w0, z0), (x, w0, z0), (x, w1, z1), (x, -w1, z1)]
    return box(C)


def floor_end():
    """Station where the inside of the bottom rises up to the underside of the floorboards (the bow rocker)."""
    xs = np.linspace(0.0, XB, 2000)
    return float(xs[np.argmax(keel_z(xs) + T >= FLOOR_Z - 1.6)])


def floorboards():
    return Mesh("floor").add(*fitted_plank(XS + T + 0.2, floor_end() - 0.5, FLOOR_Z - 1.6, FLOOR_Z))


def seats():
    m = Mesh("seats")
    for x0, x1, top in SEAT.values():
        m.add(*fitted_plank(x0, x1, top - SEAT_T, top, inset=0.1))
    return m


def tube(path, radius, sides=12):
    """A tube swept along a polyline, with domed caps."""
    path = np.asarray(path, float)
    n = len(path)
    Tg = np.gradient(path, axis=0); Tg /= np.linalg.norm(Tg, axis=1, keepdims=True)
    rings = []
    a = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    for i in range(n):
        nr = np.cross(Tg[i], [0, 0, 1.0]); nr /= max(np.linalg.norm(nr), 1e-9)
        bn = np.cross(nr, Tg[i])
        rings.append(path[i] + radius * (np.cos(a)[:, None] * nr + np.sin(a)[:, None] * bn))
    V = np.vstack(rings)
    F = []
    for i in range(n - 1):
        for j in range(sides):
            j2 = (j + 1) % sides
            F.append([i * sides + j, i * sides + j2, (i + 1) * sides + j2, (i + 1) * sides + j])
    for end, sign in ((0, -1), (n - 1, 1)):
        c = path[end] + Tg[end] * radius * 0.7 * sign
        o = len(V); V = np.vstack([V, c[None]])
        for j in range(sides):
            j2 = (j + 1) % sides
            f = [end * sides + j, end * sides + j2, o]
            F.append(f if sign > 0 else f[::-1])
    return V, F


def rub_rail():
    """Chunky rounded rail along the outside of the gunwale, all the way round the bow."""
    xs = stations(XS + 2.0, XB - 1.0, 60, 1.4)                  # the domed ends finish flush with the transom
    side = np.stack([xs, gunwale_w(xs) + 0.9, sheer_z(xs) - 1.6], -1)
    tip = np.array([[XB + 1.6, 0.0, float(sheer_z(XB)) - 1.6]])
    path = np.vstack([mirror(side), tip, side[::-1]])
    V, F = tube(path, 2.6, 12)
    return Mesh("rail").add(V, [f[::-1] for f in F])


def motor_pad():
    """Wooden pad on top of the transom that the outboard clamps onto."""
    zt = sheer_z(XS)
    C = [(XS - 1.0, -9, zt), (XS + T + 1.5, -9, zt), (XS + T + 1.5, 9, zt), (XS - 1.0, 9, zt),
         (XS - 1.0, -9, zt + 3.0), (XS + T + 1.5, -9, zt + 3.0), (XS + T + 1.5, 9, zt + 3.0), (XS - 1.0, 9, zt + 3.0)]
    return Mesh("pad").add(*box(C))


def hull_pieces():
    """Every parametric piece of the hull, raked. The SDF fittings (clamp, cleat, bow light) are meshed by the build."""
    out = []
    for m in (hull_outer(), hull_inner(), rim(), transom(), foredeck(), bulkhead(), floorboards(), seats(), rub_rail(),
              motor_pad()):
        m.V = [rake(v) for v in m.V]
        out.append(m)
    return out


# ---------------------------------------------------------------------------
# Outboard motor and propeller (signed distance functions, in the boat frame at rest, steering straight)
# ---------------------------------------------------------------------------
sd_e, sd_rc, sd_cap, smin, smax = KG.sd_ellipsoid, KG.sd_round_cone, KG.sd_capsule, KG.smin, KG.smax
SWIVEL_R = 2.0                                # swivel tube radius (turns inside the clamp's collars)
LEG_X = MOTOR_PIVOT[0] - 10.5                # the outboard's leg, behind the steering axis (clear of the clamp's collars)
PROP_C = np.array([LEG_X - 6.8, 0.0, -5.0])   # propeller hub centre, at the tail of the gearcase


def sd_box(P, c, h, r=0.0):
    q = np.abs(P - c) - (np.asarray(h) - r)
    return np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(q.max(1), 0) - r


def _motor_parts(P):
    """Distances to the outboard's parts, steering straight: a big rounded cowl over a cream band, a swivel tube on
    the steering axis, the leg down to the gearcase and skeg, and a short steering arm where the wheel's cable
    connects (the boat is steered from the console)."""
    pv = MOTOR_PIVOT
    cx = pv[0] - 6.5
    cowl = sd_e(P, np.array([cx, 0, pv[2] + 15.5]), np.array([15.0, 11.5, 12.5]))
    cowl = smax(cowl, -(P[:, 2] - (pv[2] + 7.0)), 1.8)
    band = sd_box(P, np.array([cx + 0.5, 0, pv[2] + 5.5]), (13.0, 9.6, 4.0), 3.4)
    leg = sd_cap(P, np.array([pv[0], 0, pv[2] + 1.0]), np.array([pv[0], 0, sheer_z(XS) - 9.0]), SWIVEL_R)  # swivel tube
    leg = smin(leg, sd_rc(P, np.array([LEG_X + 1.0, 0, pv[2] + 3.0]), np.array([LEG_X, 0, PROP_C[2] + 3.0]), 4.4, 3.4), 2.0)
    leg = smin(leg, sd_box(P, np.array([0.5 * (pv[0] + LEG_X), 0, pv[2] + 3.0]), (0.5 * (pv[0] - LEG_X) + 1.0, 2.0, 1.6), 1.2), 1.2)
    leg = smin(leg, sd_e(P, np.array([LEG_X - 2.5, 0, PROP_C[2] + 10.3]), np.array([11.0, 7.0, 0.9])), 1.0)  # plate
    leg = smin(leg, sd_rc(P, np.array([LEG_X + 5.5, 0, PROP_C[2]]), np.array([PROP_C[0] + 7.2, 0, PROP_C[2]]), 3.6, 2.2), 1.6)
    leg = smin(leg, sd_box(P, np.array([LEG_X + 1.5, 0, PROP_C[2] - 6.0]), (3.5, 0.8, 3.6), 0.7), 1.0)     # skeg
    link = sd_rc(P, pv + np.array([2.0, 0, 6.2]), pv + np.array([9.5, 0, 5.6]), 1.7, 1.2)          # steering arm
    link = smin(link, sd_e(P, pv + np.array([10.2, 0, 5.6]), np.array([1.7, 1.7, 1.7])), 0.5)
    return dict(cowl=cowl, band=band, leg=leg, link=link)


def motor_sdf(P):
    c = _motor_parts(P)
    d = smin(c["cowl"], c["band"], 1.4)
    d = smin(d, c["leg"], 2.0)
    return smin(d, c["link"], 1.2)


MOTOR_PAINT = dict(cowl=0, band=1, leg=2, link=2)


def motor_part(P):
    """Which part of the motor a point belongs to (for painting): 0 cowl, 1 band, 2 metal."""
    c = _motor_parts(P)
    names = list(c)
    near = np.argmin(np.stack([c[n] for n in names]), axis=0)
    return np.array([MOTOR_PAINT[n] for n in names])[near]


MOTOR_BOX = ((XS - 38.0, MOTOR_PIVOT[0] + 14.0), (-14.0, 14.0), (PROP_C[2] - 13.0, MOTOR_PIVOT[2] + 30.0))


# ---------------------------------------------------------------------------
# Fittings on the hull (signed distance functions, meshed into the hull): the outboard's transom clamp with collars
# round the swivel tube (the clamp stays put while the motor steers), a mooring cleat and a bow light.
# ---------------------------------------------------------------------------
BOW_LIGHT = np.array([XB - 13.0, 0.0, 0.0])        # z filled in below (on the deck)


def clamp_sdf(P):
    zt = float(sheer_z(XS)); pv = MOTOR_PIVOT
    d = sd_box(P, np.array([XS + 1.1, 0, zt + 4.6]), (4.6, 7.2, 1.6), 0.9)                          # over the pad
    d = smin(d, sd_box(P, np.array([XS - 2.1, 0, zt - 1.5]), (1.1, 7.2, 7.5), 0.8), 0.8)            # outside plate
    d = smin(d, sd_box(P, np.array([XS + T + 1.1, 0, zt - 1.0]), (1.0, 7.2, 4.4), 0.7), 0.8)      # inside plate
    for z in (zt + 3.6, zt - 7.0):                                                                  # collars and arms
        ring = np.maximum(np.abs(np.hypot(P[:, 0] - pv[0], P[:, 1]) - (SWIVEL_R + 1.4)) - 0.8, np.abs(P[:, 2] - z) - 1.4)
        d = np.minimum(d, ring - 0.15)
        for s in (1, -1):
            d = smin(d, sd_cap(P, np.array([XS - 2.2, 4.0 * s, z]), np.array([pv[0] + 2.6, 3.2 * s, z]), 1.2), 0.6)
    for s in (1, -1):                                                                               # T-handle screws
        y = 4.2 * s; z = zt - 3.0
        d = np.minimum(d, sd_cap(P, np.array([XS + T + 1.5, y, z]), np.array([XS + T + 3.4, y, z]), 0.75))
        d = np.minimum(d, sd_cap(P, np.array([XS + T + 3.4, y, z - 2.2]), np.array([XS + T + 3.4, y, z + 2.2]), 0.75))
    return d


CLAMP_BOX = ((XS - 11.0, XS + T + 9.0), (-10.0, 10.0), (float(sheer_z(XS)) - 11.0, float(sheer_z(XS)) + 8.0))


def deck_z(x, y=0.0):
    return float(sheer_z(x) + deck_crown(x, y / gunwale_w(x)))


def bow_sdf(P):
    """A mooring cleat on the foredeck and a little red-and-green bow light at the tip (built un-raked; the build
    rakes the mesh like the rest of the hull)."""
    xc = XB - 34.0; zc = deck_z(xc)
    d = sd_cap(P, np.array([xc - 3.0, 0, zc - 1.0]), np.array([xc - 3.0, 0, zc + 2.4]), 1.1)
    d = smin(d, sd_cap(P, np.array([xc + 3.0, 0, zc - 1.0]), np.array([xc + 3.0, 0, zc + 2.4]), 1.1), 0.4)
    d = smin(d, sd_cap(P, np.array([xc - 6.5, 0, zc + 2.6]), np.array([xc + 6.5, 0, zc + 2.6]), 1.05), 0.8)
    xl = BOW_LIGHT[0]; zl = deck_z(xl)
    d = np.minimum(d, sd_cap(P, np.array([xl, 0, zl - 1.0]), np.array([xl, 0, zl + 3.0]), 0.9))
    d = smin(d, sd_e(P, np.array([xl, 0, zl + 4.6]), np.array([2.4, 2.4, 2.2])), 0.6)
    return d


BOW_BOX = ((XB - 45.0, XB - 6.0), (-4.0, 4.0), (deck_z(XB - 45.0) - 3.0, deck_z(XB - 13.0) + 8.0))
BOW_LIGHT[2] = deck_z(BOW_LIGHT[0]) + 4.6


# ---------------------------------------------------------------------------
# Helm: a small wooden console in front of the stern seat, with a steering wheel on a short column (the wheel is its
# own mesh so it can turn) and a throttle lever. The wheel steers the outboard by cable.
# ---------------------------------------------------------------------------
WHEEL_C = np.array([-65.0, 0.0, 42.5])                  # hub centre
WHEEL_FWD = np.array([0.91, 0.0, -0.41]) / np.linalg.norm([0.91, 0.0, -0.41])   # wheel axis, away from the driver
WHEEL_UP = np.cross(WHEEL_FWD, [0.0, 1.0, 0.0])          # 12 o'clock on the wheel
WHEEL_R, WHEEL_RIM = 9.5, 0.9                            # rim radius and thickness
WHEEL_MAX = 60.0                                         # degrees each way at full lock
WHEEL_FRAME = np.column_stack([WHEEL_FWD, [0.0, 1.0, 0.0], WHEEL_UP])   # wheel's local axes in the boat frame
CONSOLE = dict(x0=-55.0, x1=-45.0, half_w=13.0, top_back=37.0, top_front=40.0, round=3.0)   # low, wide and rounded


def console_sdf(P):
    c = CONSOLE
    xm = 0.5 * (c["x0"] + c["x1"]); hx = 0.5 * (c["x1"] - c["x0"])
    zt = 0.5 * (c["top_back"] + c["top_front"])
    d = sd_box(P, np.array([xm, 0, 0.5 * (FLOOR_Z - 1.0 + c["top_front"])]),
               (hx, c["half_w"], 0.5 * (c["top_front"] - FLOOR_Z + 1.0)), c["round"])
    slope = (c["top_front"] - c["top_back"]) / (c["x1"] - c["x0"])
    n = np.array([-slope, 0, 1.0]) / math.hypot(slope, 1.0)                    # the sloping dash top
    d = smax(d, (P - np.array([xm, 0, zt])) @ n, 1.2)
    col_end = WHEEL_C + WHEEL_FWD * 1.0
    col_start = WHEEL_C + WHEEL_FWD * ((c["x0"] + 1.0 - WHEEL_C[0]) / WHEEL_FWD[0])
    d = smin(d, sd_rc(P, col_start, col_end, 2.1, 1.4), 1.0)                   # steering column
    for k, yy in enumerate((5.4,)):                                            # a round gauge on the back face
        d = smin(d, sd_cap(P, np.array([c["x0"] - 0.2, yy, GAUGE_Z]), np.array([c["x0"] - 1.2, yy, GAUGE_Z]), 2.3), 0.4)
    lever0 = np.array([c["x0"] + 4.0, -c["half_w"] - 0.4, c["top_back"] + 1.5])        # throttle lever, right side
    lever1 = lever0 + np.array([-4.5, -1.4, 7.0])
    d = np.minimum(d, sd_box(P, lever0 + np.array([0, 0.6, -1.5]), (2.6, 1.0, 2.6), 0.6))
    d = np.minimum(d, sd_cap(P, lever0, lever1, 0.7))
    d = np.minimum(d, sd_e(P, lever1, np.array([1.6, 1.6, 1.6])))
    return d


GAUGE_Z = CONSOLE["top_back"] - 5.5
THROTTLE_KNOB = np.array([CONSOLE["x0"] - 0.5, -CONSOLE["half_w"] - 1.8, CONSOLE["top_back"] + 8.5])
CONSOLE_BOX = ((CONSOLE["x0"] - 8.0, CONSOLE["x1"] + 2.0), (-CONSOLE["half_w"] - 5.0, CONSOLE["half_w"] + 2.0),
               (FLOOR_Z - 1.5, CONSOLE["top_front"] + 12.0))


def wheel_sdf(Q):
    """The steering wheel in its own frame (X along the axis, away from the driver; Z up at 12 o'clock): a fat rim,
    three spokes (3, 6 and 9 o'clock) and a domed hub."""
    r = np.hypot(Q[:, 1], Q[:, 2])
    d = np.hypot(r - WHEEL_R, Q[:, 0]) - WHEEL_RIM
    hub = sd_cap(Q, np.array([-0.9, 0, 0]), np.array([1.0, 0, 0]), 2.2)
    d = smin(d, hub, 0.6)
    for v in (np.array([0, -1.0, 0]), np.array([0, 0, -1.0]), np.array([0, 1.0, 0])):     # 3, 6 and 9 o'clock
        d = smin(d, sd_cap(Q, np.array([0.2, 0, 0]) + v * 1.5, np.array([0.3, 0, 0]) + v * (WHEEL_R - 0.4), 0.75), 0.5)
    return d


def wheel_part(Q):
    """0 rim, 1 spokes, 2 hub, 3 hub cap (the face toward the driver)."""
    r = np.hypot(Q[:, 1], Q[:, 2])
    out = np.ones(len(Q), int)
    out[r > WHEEL_R - 1.6] = 0
    out[r < 2.6] = 2
    out[(r < 1.7) & (Q[:, 0] < -1.6)] = 3
    return out


WHEEL_BOX = ((-3.5, 3.5), (-WHEEL_R - 2, WHEEL_R + 2), (-WHEEL_R - 2, WHEEL_R + 2))


def wheel_grip(side, turn=0.0):
    """Where Kai's hand closes on the rim (boat frame): 10 o'clock (left) or 2 o'clock (right), with the wheel turned
    `turn` degrees (+ = anticlockwise as the driver sees it, turning the boat left)."""
    s = 1.0 if side == "L" else -1.0
    a = math.radians(60.0 * s + turn)
    q = np.array([0.0, WHEEL_R * math.sin(a), WHEEL_R * math.cos(a)])
    return WHEEL_C + WHEEL_FRAME @ q, WHEEL_FRAME @ np.array([0.0, math.sin(a), math.cos(a)])


def prop_sdf(P):
    """Three rounded, slightly twisted blades round a hub, on an axis along X through PROP_C."""
    q = P - PROP_C
    hub = sd_cap(P, PROP_C + np.array([2.2, 0, 0]), PROP_C - np.array([2.6, 0, 0]), 2.0)
    d = hub
    for k in range(3):
        a = 2 * np.pi * k / 3
        r_dir = np.array([0, np.cos(a), np.sin(a)])
        t_dir = np.array([0, -np.sin(a), np.cos(a)])
        pitch = math.radians(28)
        n = np.cos(pitch) * np.array([1.0, 0, 0]) + np.sin(pitch) * t_dir        # blade face normal
        u = np.cross(n, r_dir)
        c = PROP_C + r_dir * 4.6
        R = np.column_stack([u, r_dir, n])
        blade = sd_e(P, c, np.array([3.0, 4.0, 0.55]), R)
        d = smin(d, blade, 0.8)
    return d


PROP_BOX = ((PROP_C[0] - 5, PROP_C[0] + 5), (-11, 11), (PROP_C[2] - 11, PROP_C[2] + 11))


# ---------------------------------------------------------------------------
# Sockets (name -> (location, forward x-axis, up z-axis)), in the hull's frame
# ---------------------------------------------------------------------------
KAI_ROOT = np.array([-86.6, 0.0, FLOOR_Z])
# Buoyancy sample points for the Blueprint, on the keel's plane (z = 0) and spread evenly round the design centre of
# mass (x = -14: the outboard and the driver sit aft; the guide offsets Unreal's centre of mass to match), so with equal
# springs the boat floats level with every pontoon WATERLINE deep.
DESIGN_COM = np.array([-14.0, 0.0, 13.4])
PONTOONS = (("Pontoon_Bow", 64.0, 0.0), ("Pontoon_FL", 40.0, 30.0), ("Pontoon_FR", 40.0, -30.0),
            ("Pontoon_ML", -30.0, 36.0), ("Pontoon_MR", -30.0, -36.0), ("Pontoon_SL", -92.0, 30.0),
            ("Pontoon_SR", -92.0, -30.0))       # where Kai's root bone goes while driving (feet on the floorboards)
CAPSULE_HALF = 52.0                               # Kai's capsule half height (his guide: mesh Z -52)


_xs = XS + 0.72 * (XB - XS)
SPRAY = rake(np.array([_xs, inner_halfwidth_at(_xs, WATERLINE + 2.0, inner=False) + 0.5, WATERLINE + 2.0]))  # bow spray, port


def sockets():
    f, up = np.array([1.0, 0, 0]), np.array([0, 0, 1.0])
    zw = WATERLINE
    S = {
        "Seat_Driver": (KAI_ROOT + np.array([0, 0, CAPSULE_HALF]), f, up),
        "Driver_Root": (KAI_ROOT, f, up),
        "Seat_Passenger": (np.array([12.4, 0, FLOOR_Z + CAPSULE_HALF]), f, up),
        "Exit_Port": (np.array([-30.0, 95.0, 40.0 + CAPSULE_HALF]), f, up),         # beside the boat at gunwale height;
        "Exit_Starboard": (np.array([-30.0, -95.0, 40.0 + CAPSULE_HALF]), f, up),   # the Blueprint traces down for ground
        "Board_Stand": (np.array([-30.0, 0, FLOOR_Z + CAPSULE_HALF]), f, up),
        "Motor_Mount": (MOTOR_PIVOT, f, up),
        "Wheel": (WHEEL_C, WHEEL_FWD, WHEEL_UP),
        "Throttle": (THROTTLE_KNOB, f, up),
        "Camera_Boom": (np.array([-40.0, 0, 70.0]), f, up),
        "Bow_Spray_L": (SPRAY, f, up),
        "Bow_Spray_R": (mirror(SPRAY), f, up),
        "Wake": (np.array([PROP_C[0] - 4.0, 0, zw]), -f, up),
        "Bow_Light": (rake(BOW_LIGHT), f, up),
    }
    for name, x, y in PONTOONS:
        S[name] = (np.array([x, y, 0.0]), f, up)
    return S


def motor_sockets():
    f, up = np.array([1.0, 0, 0]), np.array([0, 0, 1.0])
    return {"Propeller": (PROP_C, f, up),
            "Exhaust": (MOTOR_PIVOT + np.array([-20.0, 0, 9.0]), -f, up)}
