"""Crab geometry for the penguin game: proportions, rest skeleton and mesh parts (pure NumPy, no Blender).

Units are centimetres with Z up. The crab faces -Y in Blender and its left is +X, the same convention as
Pebble Chick, so both export to Unreal with the same settings. Every part is a rigid piece of shell that
belongs to exactly one bone, as on a real crab: the carapace, the leg and claw segments, the eye stalks.
Ball joints at every hinge hide the gaps when segments rotate.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.interpolate import CubicSpline

C = np.array([0.0, 1.0, 13.5])                 # carapace centre; the body bone pivots here (low, crab-like stance)
UP = np.array([0.0, 0.0, 1.0])
FWD = np.array([0.0, -1.0, 0.0])
SIDES = (("L", 1.0), ("R", -1.0))
CLAW_SCALE = {"L": 1.0, "R": 1.32}             # right: heavy "crusher"; left: slimmer "cutter", like many real crabs


def nrm(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mirror(p, s):
    p = np.array(p, float); p[..., 0] *= s
    return p


def bn(name, side):
    """Unreal-style bone name: ("leg1_upper", "L") -> "leg1_upper_l"."""
    return f"{name}_{side.lower()}"


# Levels of detail: the same parts at lower resolution. All levels share one UV layout and texture atlas.
LOD_TABLE = {0: dict(around=1.0, rings=1.0, carapace=(144, 22, 10), sphere=(12, 3)),
             1: dict(around=0.7, rings=0.6, carapace=(80, 13, 6), sphere=(8, 1)),
             2: dict(around=0.5, rings=0.4, carapace=(56, 9, 4), sphere=(6, 1)),
             3: dict(around=0.36, rings=0.25, carapace=(40, 6, 3), sphere=(5, 1))}
LOD = dict(LOD_TABLE[0])


def set_lod(level):
    LOD.clear(); LOD.update(LOD_TABLE[level])


def na(n):
    """Points around a section at the current level of detail (even, at least 4)."""
    return max(4, int(round(n * LOD["around"] / 2)) * 2)


def nr(n, lo=2):
    """Rings along a part at the current level of detail."""
    return max(lo, int(round(n * LOD["rings"])))


# ---------------------------------------------------------------------------
# Carapace: outline, dome, underside and surface relief
# ---------------------------------------------------------------------------
# Half outline (x >= 0) as rim radius from the centre by angle from +X: -90 is the front centre.
_OUT = CubicSpline([-90, -75, -60, -45, -30, -15, 0, 20, 40, 60, 75, 90],
                   [19.0, 19.6, 21.8, 25.2, 28.0, 29.4, 28.6, 25.2, 21.6, 19.4, 18.4, 18.0], bc_type="clamped")
TEETH = (-53.0, -9.0, 4, 2.4)                  # anterolateral teeth: from, to (degrees), count, height (cm)


def sym_deg(th_deg):
    t = np.radians(th_deg)
    return np.degrees(np.arctan2(np.sin(t), np.abs(np.cos(t))))


def rim_radius(th_deg, s=1.0):
    th = sym_deg(th_deg)
    R = _OUT(th)
    a0, a1, n, h = TEETH
    p = (th - a0) / ((a1 - a0) / n)
    f = np.mod(p, 1.0)
    tooth = np.where((p >= 0) & (p < n), h * np.sin(np.pi * f ** 0.6) ** 1.8, 0.0)
    rostrum = 0.9 * np.exp(-((th + 86.5) / 2.2) ** 2)          # two small teeth between the eyes
    notch = -2.0 * np.exp(-((th + 71.0) / 3.6) ** 2)            # orbit: the eye stalk sits in this notch
    return R + smoothstep(0.72, 1.0, s) * (tooth + rostrum) + smoothstep(0.80, 1.0, s) * notch


def _seg_dist(px, py, a, b):
    ax, ay = a; bx, by = b
    vx, vy = bx - ax, by - ay
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy), 0, 1)
    return np.hypot(px - ax - t * vx, py - ay - t * vy)


H_GROOVE = [((-5.5, -4.0), (-4.8, 2.0)), ((-4.8, 2.0), (-5.6, 8.0)), ((5.5, -4.0), (4.8, 2.0)),
            ((4.8, 2.0), (5.6, 8.0)), ((-4.8, 1.6), (4.8, 1.6))]


def relief(x, y):
    """Large-scale relief on top of the carapace (cm): gastric and branchial lobes and the H-shaped groove."""
    g = lambda dx, dy, r: np.exp(-(dx * dx + dy * dy) / (r * r))
    h = 0.9 * (g(x - 6, y + 6, 5) + g(x + 6, y + 6, 5)) + 0.7 * g(x, y - 6, 4.5)
    h += 0.6 * (g(x - 15, y - 4, 7) + g(x + 15, y - 4, 7))
    d = np.min([_seg_dist(x, y, a, b) for a, b in H_GROOVE], axis=0)
    brow = 1.8 * np.exp(-((np.abs(x) - 6.5) / 4.2) ** 2) * np.exp(-((y + 15.6) / 1.6) ** 2)   # ridge behind each eye
    return h - 0.25 * np.exp(-(d / 1.0) ** 2) + brow


def dome(th_deg, s=1.0):
    """Top height and underside depth. The front of the dome is lower, fading in from the centre so the
    surface stays smooth at the top pole."""
    front = np.maximum(0.0, -np.sin(np.radians(th_deg)))
    return 10.5 - 2.4 * front ** 2 * smoothstep(0.0, 1.0, s), 6.0


def carapace_point(th_deg, s, top=True):
    R = rim_radius(th_deg, s)
    t = np.radians(th_deg)
    x, y = s * R * np.cos(t), s * R * np.sin(t)
    ht, hb = dome(th_deg, s)
    q = np.clip(1 - s * s, 0, 1)
    if top:
        z = ht * q ** 0.55 + relief(x, y) * smoothstep(1.0, 0.72, s)
    else:
        grooves = sum(np.exp(-((y - yk) / 0.5) ** 2) for yk in (-9.0, -4.5, 0.0, 4.5))
        z = -hb * q ** 0.42 + 0.35 * grooves * smoothstep(0.8, 0.45, s) + 0.0 * x
    return C + np.stack([x, y, z], -1)


# ---------------------------------------------------------------------------
# Generic lofted part: a tube along a centre line with an elliptical section and rounded or pointed ends
# ---------------------------------------------------------------------------
class Part:
    """verts (N,3); faces: lists of vertex indices; fuv: per face, the (u, v) of each corner in the part's own
    0..1 texture space; vt: per-vertex 'along' parameter; bone; tile: texture island key; owner: whether this
    part paints its island (mirrored and duplicate parts share the island of their twin)."""
    def __init__(self, name, bone, verts, faces, fuv, vt, tile, kind, mat="shell", owner=True, size=(1.0, 1.0)):
        self.name, self.bone, self.verts, self.faces, self.fuv = name, bone, np.asarray(verts, float), faces, fuv
        self.vt, self.tile, self.kind, self.mat, self.owner, self.size = np.asarray(vt, float), tile, kind, mat, owner, size


def envelope(t, a0=0.12, a1=0.12, point=0.0):
    """1 in the middle; rounded (quarter-ellipse) ends over a0 and a1. point > 0 makes the far end a cone
    that keeps that fraction of the radius at the very tip."""
    t = np.asarray(t, float)
    e = np.ones_like(t)
    m0 = t < a0
    e[m0] = np.sqrt(np.clip(1 - ((a0 - t[m0]) / a0) ** 2, 0, 1))
    m1 = t > 1 - a1
    if point > 0:
        e[m1] = point + (1 - point) * (1 - (t[m1] - (1 - a1)) / a1) ** 0.9
    else:
        e[m1] = np.sqrt(np.clip(1 - ((t[m1] - (1 - a1)) / a1) ** 2, 0, 1))
    return e


def end_samples(n_mid=10, a0=0.12, a1=0.12, k=4):
    """t samples with extra rings inside the rounded ends; first and last are the poles."""
    s0 = a0 * (1 - np.cos(np.linspace(0, np.pi / 2, k + 1)))[:-1]
    s1 = 1 - a1 * (1 - np.cos(np.linspace(0, np.pi / 2, k + 1)))[:-1][::-1]
    return np.concatenate([s0, np.linspace(a0, 1 - a1, n_mid), s1])


def loft(name, bone, center, ref, rv, rs, ts, n=16, radial=None, tile=None, kind="tube", mat="shell",
         owner=True, power=2.0):
    """center(t) -> point; ref(t) or vector: the 'bottom' direction of the section (seam side); rv/rs(t):
    radii toward bottom and to the side; radial(t, a) extra outward offset (a = 0 at the bottom); power(t) or
    number: superellipse exponent of the section (2 = ellipse, higher = flatter sides)."""
    ts = np.asarray(ts, float)
    P = np.array([center(t) for t in ts])
    T = np.gradient(P, ts, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    verts, vt = [P[0]], [ts[0]]
    rings = []
    for i in range(1, len(ts) - 1):
        y = T[i]
        r = ref(ts[i]) if callable(ref) else np.asarray(ref, float)
        b = nrm(r - y * np.dot(y, r)); sd = np.cross(y, b)
        ring = []
        for j in range(n):
            a = 2 * np.pi * j / n
            pw = 2.0 / (power(ts[i]) if callable(power) else power)
            ca, sa = math.cos(a), math.sin(a)
            d = math.copysign(abs(ca) ** pw, ca) * b * rv(ts[i]) + math.copysign(abs(sa) ** pw, sa) * sd * rs(ts[i])
            if radial is not None:
                d = d + radial(ts[i], a) * nrm(math.cos(a) * b + math.sin(a) * sd)
            ring.append(len(verts)); verts.append(P[i] + d); vt.append(ts[i])
        rings.append(ring)
    verts.append(P[-1]); vt.append(ts[-1])
    last = len(verts) - 1
    faces, fuv = [], []
    for j in range(n):
        j2 = (j + 1) % n
        faces.append([0, rings[0][j2], rings[0][j]])
        fuv.append([((j + 0.5) / n, ts[0]), ((j + 1) / n, ts[1]), (j / n, ts[1])])
        for i in range(len(rings) - 1):
            faces.append([rings[i][j], rings[i][j2], rings[i + 1][j2], rings[i + 1][j]])
            fuv.append([(j / n, ts[i + 1]), ((j + 1) / n, ts[i + 1]), ((j + 1) / n, ts[i + 2]), (j / n, ts[i + 2])])
        faces.append([last, rings[-1][j], rings[-1][j2]])
        fuv.append([((j + 0.5) / n, ts[-1]), (j / n, ts[-2]), ((j + 1) / n, ts[-2])])
    # island size in cm: mean section perimeter by centre-line length
    per = np.mean([np.sum(np.linalg.norm(np.diff(np.array([verts[k] for k in ring + ring[:1]]), axis=0), axis=1))
                   for ring in rings])
    length = float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1)))
    return Part(name, bone, verts, faces, fuv, vt, tile or name, kind, mat, owner, size=(per, length))


def segment_center(a, b, ext0=0.0, ext1=0.0):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = nrm(b - a); a2, b2 = a - d * ext0, b + d * ext1
    return lambda t: a2 + (b2 - a2) * t


def spline_center(pts):
    pts = np.asarray(pts, float)
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    cs = CubicSpline(d / d[-1], pts, bc_type="natural")
    return lambda t: cs(t)


def sphere(name, bone, c, r, tile, kind="joint", mat="shell", owner=True, n=None, k=None, axis=(0, 0, 1), stretch=1.0):
    n = n or LOD["sphere"][0]; k = k or LOD["sphere"][1]
    ax = nrm(axis)
    L = r * stretch
    center = segment_center(np.asarray(c) - ax * L, np.asarray(c) + ax * L)
    ref = nrm(np.cross(ax, [1, 0, 0]) if abs(ax[0]) < 0.9 else np.cross(ax, [0, 1, 0]))
    env = lambda t: np.sqrt(np.clip(1 - (2 * t - 1) ** 2, 0, 1))
    ts = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, 2 * k + 3))
    return loft(name, bone, center, ref, lambda t: r * env(t), lambda t: r * env(t), ts, n=n, tile=tile,
                kind=kind, mat=mat, owner=owner)


# ---------------------------------------------------------------------------
# Rest skeleton: legs come from a 2-bone IK solve so the rest pose stands on the ground
# ---------------------------------------------------------------------------
LEGS = [  # angle on the rim (deg), foot direction (deg from +X), reach from hip to foot (cm), knee tilt toward
    # the front (deg; negative tilts it back), upper, lower, tip lengths. Tilted knees kink each leg seen from above,
    # so the legs sweep forward and back like a crab's instead of radiating like spokes.
    dict(rim=-14, psi=-38, reach=22.5, knee=30.0, L=(13.0, 12.0, 7.0)),
    dict(rim=10, psi=-11, reach=25.0, knee=16.0, L=(15.0, 13.5, 7.5)),
    dict(rim=33, psi=17, reach=24.0, knee=-24.0, L=(15.0, 13.5, 7.5)),
    dict(rim=56, psi=44, reach=21.5, knee=-32.0, L=(13.0, 12.0, 7.0)),
]
TIP_TILT = math.radians(25)                     # the tip leans outward from vertical by this much


def knee_pole(up, out_h, knee_deg):
    """Direction the knee bends toward: up, tilted toward the crab's front by knee_deg."""
    f = FWD - out_h * np.dot(FWD, out_h) - up * np.dot(FWD, up)
    f = nrm(f) if np.linalg.norm(f) > 1e-6 else np.zeros(3)
    g = math.radians(knee_deg)
    return up * math.cos(g) + f * math.sin(g)


def leg_ik(H, T, L, up, out_h, tilt=TIP_TILT, pole=None):
    """Hip H, ground tip T -> knee K and tip base D. The tip leans outward by tilt; the knee bends toward pole."""
    L1, L2, L3 = L
    dd = nrm(-up * math.cos(tilt) + out_h * math.sin(tilt))
    D = T - dd * L3
    v = D - H; d = np.linalg.norm(v)
    d = np.clip(d, abs(L1 - L2) + 1e-3, L1 + L2 - 1e-3)
    u = v / np.linalg.norm(v)
    a = math.acos(np.clip((L1 * L1 + d * d - L2 * L2) / (2 * L1 * d), -1, 1))
    pole = up if pole is None else pole
    w = nrm(pole - u * np.dot(u, pole))
    K = H + L1 * (math.cos(a) * u + math.sin(a) * w)
    return K, D


def leg_rest(i, s):
    g = LEGS[i]
    th = g["rim"] if s > 0 else 180 - g["rim"]
    H = carapace_point(th, 0.88, top=False) + np.array([0, 0, 1.0])
    psi = math.radians(g["psi"]); out_h = np.array([s * math.cos(psi), math.sin(psi), 0.0])
    T = H + out_h * g["reach"]; T[2] = 0.0
    K, D = leg_ik(H, T, g["L"], UP, out_h, pole=knee_pole(UP, out_h, g["knee"]))
    return H, K, D, T, out_h


CLAW = {  # cutter: slim palm, long fingers with fine sharp teeth; crusher: deep palm, short thick fingers, molars
    "L": dict(palm=(6.0, 3.6), finger=(2.2, 1.9), dactyl=(2.1, 1.8), f_len=10.5, arch=2.2, hdir=(-0.62, -0.76, -0.05),
              teeth=dict(period=0.05, height=0.75, sharp=True)),
    "R": dict(palm=(6.9, 5.0), finger=(3.0, 2.6), dactyl=(2.9, 2.5), f_len=8.6, arch=1.5, hdir=(-0.50, -0.85, -0.12),
              teeth=dict(period=0.10, height=1.05, sharp=False)),
}


def claw_rest(s, side):
    k = CLAW_SCALE[side]; cs = CLAW[side]
    th = -57 if s > 0 else -123
    P0 = carapace_point(th, 0.80, top=False) + np.array([0, 0, 1.5])
    def at(p): return P0 + (np.asarray(p) - P0) * k
    E = P0 + nrm([0.55 * s, -0.62, 0.42]) * 11.0
    W = E + nrm([0.08 * s, -0.96, 0.12]) * 6.0
    hdir = nrm([cs["hdir"][0] * s, cs["hdir"][1], cs["hdir"][2]])
    Hh = W + hdir * 11.0                         # dactyl hinge, on top of the palm's far end
    side_x = nrm(np.cross(UP, hdir)); zh = nrm(np.cross(hdir, side_x))   # z of the hand frame, about up
    F_dir = nrm(hdir - zh * 0.16 - mirror([1, 0, 0], s) * 0.10)
    F_tip = Hh - zh * 5.0 + F_dir * cs["f_len"]   # fixed finger tip
    D_tip = F_tip + zh * 1.0                      # closed dactyl tip rests on it
    return dict(P0=P0, E=at(E), W=at(W), Hh=at(Hh), F_tip=at(F_tip), D_tip=at(D_tip), zh=zh, hdir=hdir, k=k)


def antenna_rest(s):
    a = carapace_point(-84.5 if s > 0 else -95.5, 0.98, top=True) - np.array([0, 0, 0.6])
    return a, a + np.array([3.0 * s, -5.6, 2.4])


def mouth_rest(s):
    top = C + np.array([1.85 * s, -15.0, -1.6])
    return top, top + np.array([0.0, -1.1, -4.6])


def eye_rest(s):
    th = -71 if s > 0 else -109
    base = carapace_point(th, 0.93, top=True) - np.array([0, 0, 1.0])
    d = nrm([0.24 * s, -0.40, 0.88])
    return base, base + d * 8.5, d


HELPER_PREFIXES = ("ik_", "pole_")
HELPER_KEYS = ("_end_", "claw_tip_", "claw_pinch_")


def is_helper(name):
    """Bones with no skin: IK goals, pole targets, contact and attachment points."""
    return name.startswith(HELPER_PREFIXES) or any(k in name for k in HELPER_KEYS)


def skeleton():
    """[(name, head, tail, z_axis, parent)] for the rest pose; z_axis sets the bone roll.

    Skinned bones: root, body, eye_l/r, antenna_l/r, mouthpart_l/r, claw_arm/wrist/hand/pincer_l/r and
    leg1-4_upper/lower/tip_l/r. Helper bones (no skin) for procedural animation and gameplay:
      legN_end_l/r     the foot contact point at the tip of each leg (child of legN_tip)
      pole_legN_l/r    knee pole target for two-bone IK (child of body)
      ik_foot_root, ik_legN_l/r     foot IK goals, animated in every clip to follow legN_end (child of root)
      ik_legN_ankle_l/r   child of ik_legN placed and oriented like legN_tip: the Two Bone IK effector, so
                          the tip segment lands with its end exactly on ik_legN
      claw_tip_l/r     tip of the moving finger; claw_pinch_l/r where the fingers close (hit point)
      ik_claw_root, ik_claw_l/r     claw IK goals, animated to follow claw_tip
    """
    B = [("root", (0, 0, 0), (0, 0, 12), FWD, None), ("body", C, C + [0, 0, 10], FWD, "root")]
    helpers = []
    for side, s in SIDES:
        base, tip, d = eye_rest(s)
        B.append((bn("eye", side), base, tip, nrm(FWD - d * np.dot(d, FWD)), "body"))
        a0, a1 = antenna_rest(s); da = nrm(a1 - a0)
        B.append((bn("antenna", side), a0, a1, nrm(UP - da * np.dot(da, UP)), "body"))
        m0, m1 = mouth_rest(s); dm = nrm(m1 - m0)
        B.append((bn("mouthpart", side), m0, m1, nrm(FWD - dm * np.dot(dm, FWD)), "body"))
        c = claw_rest(s, side)
        chain = [("claw_arm", c["P0"], c["E"]), ("claw_wrist", c["E"], c["W"]), ("claw_hand", c["W"], c["Hh"]),
                 ("claw_pincer", c["Hh"], c["D_tip"])]
        parent = "body"; zs = {}
        for nm, h, t in chain:
            y = nrm(t - h); x = nrm(np.cross(UP, y)); z = np.cross(x, y); zs[nm] = z
            B.append((bn(nm, side), h, t, z, parent)); parent = bn(nm, side)
        dt = nrm(c["D_tip"] - c["Hh"])
        grip = (c["F_tip"] + c["D_tip"]) / 2 - c["hdir"] * 2.0 * c["k"]
        helpers += [(bn("claw_tip", side), c["D_tip"], c["D_tip"] + dt * 2.0, zs["claw_pincer"], bn("claw_pincer", side)),
                    (bn("claw_pinch", side), grip, grip + c["hdir"] * 2.0, zs["claw_hand"], bn("claw_hand", side)),
                    (bn("ik_claw", side), c["D_tip"], c["D_tip"] + dt * 2.0, zs["claw_pincer"], "ik_claw_root")]
        for i in range(4):
            H, K, D, T, out_h = leg_rest(i, s)
            u = nrm(D - H); w = nrm((K - H) - u * np.dot(K - H, u))
            n = nrm(np.cross(u, w))                            # hinge axis: across the (tilted) plane of the leg
            if np.dot(n, np.cross(UP, out_h)) < 0: n = -n
            parent = "body"
            for nm, h, t in ((f"leg{i + 1}_upper", H, K), (f"leg{i + 1}_lower", K, D), (f"leg{i + 1}_tip", D, T)):
                y = nrm(t - h); x = nrm(n - y * np.dot(n, y))
                B.append((bn(nm, side), h, t, np.cross(x, y), parent)); parent = bn(nm, side)
            y = nrm(T - D); x = nrm(n - y * np.dot(n, y)); z = np.cross(x, y)
            Pp = K + w * 14.0
            helpers += [(bn(f"leg{i + 1}_end", side), T, T + y * 2.5, z, bn(f"leg{i + 1}_tip", side)),
                        (bn(f"ik_leg{i + 1}", side), T, T + y * 2.5, z, "ik_foot_root"),
                        (bn(f"ik_leg{i + 1}_ankle", side), D, T, z, bn(f"ik_leg{i + 1}", side)),
                        (bn(f"pole_leg{i + 1}", side), Pp, Pp + w * 4.0, nrm(FWD - w * np.dot(w, FWD)), "body")]
    B += [("ik_foot_root", (0, 0, 0), (0, 0, 6), FWD, "root"), ("ik_claw_root", (0, 0, 0), (0, 0, 6), FWD, "root")]
    B += helpers
    return [(n, np.asarray(h, float), np.asarray(t, float), np.asarray(z, float), p) for n, h, t, z, p in B]


# ---------------------------------------------------------------------------
# Mesh parts
# ---------------------------------------------------------------------------
_ARC = {}


def _arc(th, top):
    """Arc length from the pole along the top (or underside) at angles th, as a function of s: (s grid, table)."""
    fine = np.linspace(0.0, 1.0, 321)
    pts = np.array([carapace_point(th, sv, top) for sv in fine])            # (321, n, 3)
    acc = np.concatenate([np.zeros((1, len(th))), np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=2), 0)])
    return fine, acc


def _arc_max():
    if "max" not in _ARC:
        th = np.linspace(-180, 180, 720, endpoint=False)
        _ARC["max"] = max(_arc(th, True)[1][-1].max(), _arc(th, False)[1][-1].max())
    return _ARC["max"]


def carapace_part():
    n, kt, kb = LOD["carapace"]
    th = np.linspace(-180, 180, n, endpoint=False)
    s_top = 0.5 - 0.5 * np.cos(np.pi * (np.arange(1, kt + 1) / kt) ** 0.85)   # ring 1 .. rim (s = 1), dense at both ends
    s_bot = (1 - (1 - np.arange(1, kb) / kb) ** 1.5)[::-1]        # just inside the rim .. near the centre
    verts = [carapace_point(0, 0.0, True)]
    vt = [0.0]
    rings = []
    for sv in s_top:
        rings.append(list(range(len(verts), len(verts) + n)))
        verts.extend(carapace_point(th, sv, True)); vt.extend([sv] * n)
    for sv in s_bot:
        rings.append(list(range(len(verts), len(verts) + n)))
        verts.extend(carapace_point(th, sv, False)); vt.extend([-sv] * n)
    verts.append(carapace_point(0, 0.0, False)); vt.append(-0.0)
    verts = np.array(verts); last = len(verts) - 1
    # UVs: polar, by arc length from each pole (from a fine table, so every level of detail maps identically);
    # the top and the underside are separate islands
    Lmax = _arc_max()
    fine, acc_t = _arc(th, True); _, acc_b = _arc(th, False)
    ang = np.radians(th)
    uv = {}
    s_rings_bot = [1.0] + list(s_bot)                                        # underside rings from the rim inward
    for i, ring in enumerate(rings[:kt]):
        for j, vi in enumerate(ring):
            r = np.interp(s_top[i], fine, acc_t[:, j]) / Lmax
            uv[("t", vi)] = (0.5 + 0.5 * r * math.cos(ang[j]), 0.5 + 0.5 * r * math.sin(ang[j]))
    for i, ring in enumerate(rings[kt - 1:]):
        for j, vi in enumerate(ring):
            r = np.interp(s_rings_bot[i], fine, acc_b[:, j]) / Lmax
            uv[("b", vi)] = (0.5 - 0.5 * r * math.cos(ang[j]), 0.5 + 0.5 * r * math.sin(ang[j]))
    uv[("t", 0)] = (0.5, 0.5); uv[("b", last)] = (0.5, 0.5)
    faces, fuv, ftile = [], [], []
    def add(face, island):
        faces.append(face); fuv.append([uv[(island, v)] for v in face]); ftile.append(island)
    for j in range(n):
        j2 = (j + 1) % n
        add([0, rings[0][j], rings[0][j2]], "t")
        for i in range(len(rings) - 1):
            island = "t" if i < kt - 1 else "b"
            add([rings[i][j], rings[i + 1][j], rings[i + 1][j2], rings[i][j2]], island)
        add([last, rings[-1][j2], rings[-1][j]], "b")
    p = Part("Carapace", "body", verts, faces, fuv, vt, None, "carapace", size=(2 * Lmax, 2 * Lmax))
    p.ftile = ["carapace_top" if t == "t" else "carapace_bottom" for t in ftile]
    return p


def cuff(t, start=0.14):
    """Segment profile: tucked-in start (it slides inside the previous segment) and a flared cuff at the far end."""
    t = np.asarray(t, float)
    return (0.78 + 0.22 * smoothstep(0.0, start, t)) * (1.0 + 0.13 * np.exp(-((t - 0.88) / 0.05) ** 2))


def leg_parts(i, side, s):
    H, K, D, T, out_h = leg_rest(i, s)
    owner = side == "L"
    tile = lambda seg: f"leg{i + 1}_{seg}"
    bone = lambda seg: bn(f"leg{i + 1}_{seg}", side)
    q = (LEGS[i]["L"][0] / 15.0) ** 0.5
    rin = lambda t: nrm(-out_h * 0.8 - UP * 0.6)               # bottom of the section faces in and down
    # Crab legs are flat paddles: wide seen from above, thin seen from the side
    parts = [loft(f"Leg{i + 1} upper.{side}", bone("upper"), segment_center(H, K, 1.8, 0.9), -UP,
                  lambda t: 2.0 * q * (1.0 - 0.12 * t) * cuff(t) * envelope(t, 0.08, 0.07),
                  lambda t: 3.4 * q * (1.0 - 0.15 * t) * cuff(t) * envelope(t, 0.08, 0.07),
                  end_samples(nr(11), 0.08, 0.07, nr(3, 1)), n=na(16), tile=tile("upper"), owner=owner, power=2.4,
                  radial=lambda t, a: 0.3 * q * max(0.0, math.cos(a - math.pi)) ** 10 * (0.15 < t < 0.82)),
             loft(f"Leg{i + 1} lower.{side}", bone("lower"), segment_center(K, D, 0.9, 0.7), rin,
                  lambda t: 1.75 * q * (1.0 - 0.2 * t) * cuff(t) * envelope(t, 0.07, 0.07),
                  lambda t: 2.7 * q * (1.0 - 0.22 * t) * cuff(t) * envelope(t, 0.07, 0.07),
                  end_samples(nr(11), 0.07, 0.07, nr(3, 1)), n=na(16), tile=tile("lower"), owner=owner, power=2.3)]
    sweep = nrm(FWD - out_h * np.dot(FWD, out_h)) * math.copysign(0.9, LEGS[i]["knee"])   # tips curve with the knee
    tip_c = spline_center([D - nrm(T - D) * 0.7, (D + T) / 2 - out_h * 0.45 + sweep, T])
    parts.append(loft(f"Leg{i + 1} tip.{side}", bone("tip"), tip_c, rin,
                      lambda t: 1.35 * q * (0.85 + 0.15 * smoothstep(0, 0.12, t)) * envelope(t, 0.08, 0.78, point=0.05),
                      lambda t: 1.75 * q * (0.85 + 0.15 * smoothstep(0, 0.12, t)) * envelope(t, 0.08, 0.78, point=0.05),
                      end_samples(nr(9), 0.08, 0.05, nr(3, 1)), n=na(12), tile=tile("tip"), owner=owner))
    inward = nrm(C - H) * np.array([1, 1, 0])
    parts.append(sphere(f"Leg{i + 1} hip joint.{side}", bone("upper"), H + UP * 0.6 + inward * 1.2, 2.2 * q, "joint_hip",
                        kind="joint_hip", owner=owner and i == 0))
    parts.append(sphere(f"Leg{i + 1} knee joint.{side}", bone("lower"), K, 1.7 * q, "joint", owner=owner and i == 0))
    parts.append(sphere(f"Leg{i + 1} tip joint.{side}", bone("tip"), D, 1.25 * q, "joint", owner=False))
    return parts


def claw_parts(side, s):
    c = claw_rest(s, side); cs = CLAW[side]
    k, zh = c["k"], c["zh"]
    P0, E, W, Hh, F_tip, D_tip = c["P0"], c["E"], c["W"], c["Hh"], c["F_tip"], c["D_tip"]
    tl = lambda nm: f"{nm}_{side}"                       # each claw has its own texture islands
    parts = []
    spines = lambda t, a: k * (0.9 * sum(math.exp(-((t - tc) / 0.035) ** 2) for tc in (0.35, 0.55, 0.75))
                               * max(0.0, math.cos(a - math.pi)) ** 12)
    parts.append(loft(f"Claw arm.{side}", bn("claw_arm", side), segment_center(P0, E, 2.0, 1.2), -UP,
                      lambda t: k * (3.0 + 0.9 * t) * cuff(t) * envelope(t, 0.10, 0.10),
                      lambda t: k * (2.6 + 0.6 * t) * cuff(t) * envelope(t, 0.10, 0.10),
                      end_samples(nr(12), 0.10, 0.10, nr(3, 1)), n=na(16), radial=spines, tile=tl("claw_arm"), power=2.5))
    knob = lambda t, a: k * 1.1 * math.exp(-((t - 0.55) / 0.12) ** 2) * max(0.0, math.cos(a - 0.8 * math.pi)) ** 6
    parts.append(loft(f"Claw wrist.{side}", bn("claw_wrist", side), segment_center(E, W, 1.2, 1.4), -UP,
                      lambda t: k * 4.0 * envelope(t, 0.2, 0.2), lambda t: k * 3.5 * envelope(t, 0.2, 0.2),
                      end_samples(nr(8), 0.2, 0.2, nr(3, 1)), n=na(16), radial=knob, tile=tl("claw_wrist")))
    # Palm and fixed finger in one piece: a deep, flat-sided palm; the finger runs off its lower edge
    hd = nrm(Hh - W)
    Pe = Hh - zh * 2.8 * k
    hand_c = spline_center([W - hd * 1.6 * k, W + (Pe - W) * 0.45 - zh * 0.2 * k, Pe - zh * 0.9 * k,
                            Pe + (F_tip - Pe) * 0.5 - zh * 0.4 * k, F_tip])
    (pv, ps), (fv, fs), th = cs["palm"], cs["finger"], cs["teeth"]
    def palm_r(t, big, fin):
        return np.interp(t, [0.0, 0.07, 0.28, 0.50, 0.60, 0.80, 1.0], [0, big * 0.78, big, big * 0.9, fin, fin * 0.72, fin * 0.32])
    def tooth(t, t0, t1):
        if not (t0 < t < t1): return 0.0
        ph = ((t - t0) / th["period"]) % 1.0
        return (1 - ph) ** 1.5 if th["sharp"] else math.sin(math.pi * ph) ** 0.8
    teeth_f = lambda t, a: k * th["height"] * tooth(t, 0.62, 0.95) * max(0.0, math.cos(a - math.pi)) ** 4
    ts = np.concatenate([[0.0, 0.02, 0.05], np.linspace(0.08, 0.96, nr(40, 8)), [0.985, 1.0]])
    parts.append(loft(f"Claw hand.{side}", bn("claw_hand", side), hand_c, -zh,
                      lambda t: k * palm_r(t, pv, fv), lambda t: k * palm_r(t, ps, fs),
                      ts, n=na(22), radial=teeth_f, tile=tl("claw_hand"),
                      power=lambda t: 2.0 + 1.1 * smoothstep(0.62, 0.45, t)))
    dact_c = spline_center([Hh - hd * 1.2 * k, Hh + (D_tip - Hh) * 0.45 + zh * cs["arch"] * k, D_tip])
    teeth_d = lambda t, a: k * 0.85 * th["height"] * tooth(t, 0.35, 0.9) * max(0.0, math.cos(a)) ** 4
    dv, ds = cs["dactyl"]
    parts.append(loft(f"Claw pincer.{side}", bn("claw_pincer", side), dact_c, -zh,
                      lambda t: k * np.interp(t, [0, 0.08, 0.3, 0.8, 1.0], [0, dv, dv * 0.95, dv * 0.5, dv * 0.16]),
                      lambda t: k * np.interp(t, [0, 0.08, 0.3, 0.8, 1.0], [0, ds, ds * 0.95, ds * 0.55, ds * 0.18]),
                      np.concatenate([[0.0, 0.03], np.linspace(0.07, 0.96, nr(28, 6)), [0.985, 1.0]]), n=na(16),
                      radial=teeth_d, tile=tl("claw_pincer"), power=2.3))
    parts.append(sphere(f"Claw shoulder joint.{side}", bn("claw_arm", side), P0 + UP * 0.8, 2.9 * k, "joint_hip",
                        kind="joint_hip", owner=False))
    for nm, b, c, r in (("elbow", "claw_wrist", E, 3.3), ("wrist", "claw_hand", W, 3.4), ("hinge", "claw_pincer", Hh, 1.8)):
        parts.append(sphere(f"Claw {nm} joint.{side}", bn(b, side), c, r * k, "joint_hip", kind="joint_hip", owner=False))
    return parts


def eye_parts(side, s):
    base, tip, d = eye_rest(s)
    owner = side == "L"
    return [loft(f"Eye stalk.{side}", bn("eye", side), segment_center(base, tip, 1.5, 0.0), [0, 1, 0],
                 lambda t: (1.75 - 0.3 * t) * envelope(t, 0.1, 0.05), lambda t: (1.6 - 0.25 * t) * envelope(t, 0.1, 0.05),
                 end_samples(nr(7), 0.1, 0.05, nr(2, 1)), n=na(12), tile="eye_stalk", owner=owner),
            sphere(f"Eye socket.{side}", bn("eye", side), base + d * 0.4, 2.3, "joint_hip", kind="joint_hip", owner=False),
            sphere(f"Eye.{side}", bn("eye", side), tip + d * 1.7, 3.2, "eyeball", kind="eyeball", mat="eye",
                   owner=owner, n=na(20), k=nr(5), axis=d, stretch=1.12)]


def head_parts():
    parts = []
    for side, s in SIDES:
        a, tip = antenna_rest(s)
        parts.append(loft(f"Antenna.{side}", bn("antenna", side), spline_center([a, a + np.array([0.8 * s, -3.0, 1.8]), tip]), -UP,
                          lambda t: 0.62 * envelope(t, 0.1, 0.35, point=0.4), lambda t: 0.62 * envelope(t, 0.1, 0.35, point=0.4),
                          end_samples(nr(8), 0.1, 0.1, nr(2, 1)), n=na(8), tile="antenna", owner=side == "L"))
        # third maxillipeds: two flat plates side by side that close over the mouth
        top, bot = mouth_rest(s)
        parts.append(loft(f"Mouthpart.{side}", bn("mouthpart", side), segment_center(top, bot), [0, -1, 0],
                          lambda t: 0.5 * envelope(t, 0.12, 0.18), lambda t: 1.75 * envelope(t, 0.12, 0.18),
                          end_samples(nr(6), 0.12, 0.18, nr(3, 1)), n=na(12), tile="mouth", owner=side == "L", power=4.0))
    return parts


def abdomen_part():
    """The tail flap folded under the body (what you see when the crab lies on its back)."""
    ys = np.linspace(-3.5, 14.0, 7)
    pts = []
    for y in ys:
        th = 90.0 if y >= 0 else -90.0
        s = abs(y) / float(rim_radius(th, 1.0))
        z = carapace_point(th, s, top=False)[2] - 0.55
        pts.append([C[0], C[1] + y, z])
    width = lambda t: np.interp(t, [0, 0.1, 0.45, 0.8, 1.0], [0.0, 2.6, 4.4, 5.8, 5.2])
    return loft("Abdomen", "body", spline_center(pts), UP, lambda t: 0.75 * envelope(t, 0.08, 0.1),
                lambda t: width(t) * envelope(t, 0.08, 0.1), end_samples(nr(16), 0.08, 0.1, nr(3, 1)), n=na(16), tile="abdomen",
                kind="abdomen", power=3.0)


def build_parts(lod=0):
    set_lod(lod)
    parts = [carapace_part()]
    for side, s in SIDES:
        for i in range(4):
            parts += leg_parts(i, side, s)
        parts += claw_parts(side, s)
        parts += eye_parts(side, s)
    parts += head_parts()
    parts.append(abdomen_part())
    for p in parts:
        if not hasattr(p, "ftile"):
            p.ftile = [p.tile] * len(p.faces)
    return parts
