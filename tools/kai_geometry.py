"""Kai, a toon island kid for platforming: proportions, skeleton and the shape of every modular part.

Pure NumPy (plus scikit-image for marching cubes), so it runs inside or outside Blender. Units are centimetres,
Z is up, Kai faces -Y and Kai's left is +X. Organic parts are signed distance fields (SDFs) blended with smooth
unions and turned into meshes with marching cubes; build_kai.py remeshes, UV-maps, paints and skins them in Blender.
Face features (eye whites, irises, lids, brows, mouth) are explicit meshes laid onto the head surface.

Modular slots. Skin that shows is one continuous piece (no seams to hide); clothes sit over it and hide where
each skin piece starts:
    head      head, ears, neck, a patch of chest for the V-neck, eyes, lids, brows, mouth
    hair      any hairstyle; the head is complete (bald) underneath
    arms      both arms and hands, starting inside the sleeves
    tunic     tunic and sailor collar
    pants     pants (rolled to mid calf)
    legs      lower legs and bare feet, starting inside the pants
    sandals   soles and straps over the feet
    sash, neckerchief   accessories
"""
import math
import numpy as np

FWD = np.array([0.0, -1.0, 0.0])
UP = np.array([0.0, 0.0, 1.0])
SIDES = (("L", 1.0), ("R", -1.0))


def bn(name, side):
    """Unreal-style bone name: ("thigh", "L") -> "thigh_l"."""
    return f"{name}_{side.lower()}"


def nrm(v):
    v = np.asarray(v, float)
    return v / max(np.linalg.norm(v), 1e-12)


def mirror(p, s):
    p = np.array(p, float); p[..., 0] *= s
    return p


# ---------------------------------------------------------------------------
# Signed distance primitives (P: (n, 3) array). Negative inside.
# ---------------------------------------------------------------------------
def sd_sphere(P, c, r):
    return np.linalg.norm(P - c, axis=1) - r


def sd_ellipsoid(P, c, r, R=None):
    """Ellipsoid with radii r, optionally rotated by the 3x3 matrix R (columns are its local axes)."""
    q = P - c
    if R is not None: q = q @ R
    q = q / r
    k0 = np.linalg.norm(q, axis=1)
    k1 = np.linalg.norm(q / r, axis=1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def sd_round_cone(P, a, b, r1, r2):
    """Cone between spheres (a, r1) and (b, r2), exact (after Inigo Quilez)."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    ba = b - a; l2 = ba @ ba; rr = r1 - r2; a2 = l2 - rr * rr; il2 = 1.0 / l2
    pa = P - a
    y = pa @ ba; z = y - l2
    x = pa * l2 - np.outer(y, ba)
    x2 = np.einsum("ij,ij->i", x, x)
    y2 = y * y * l2; z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    out = np.empty(len(P))
    c1 = np.sign(z) * a2 * z2 > k
    c2 = np.sign(y) * a2 * y2 < k
    out[c1] = np.sqrt(x2[c1] + z2[c1]) * il2 - r2
    m = c2 & ~c1
    out[m] = np.sqrt(x2[m] + y2[m]) * il2 - r1
    m = ~c1 & ~c2
    out[m] = (np.sqrt(x2[m] * a2 * il2) + y[m] * rr) * il2 - r1
    return out


def sd_capsule(P, a, b, r):
    return sd_round_cone(P, a, b, r, r)


def smin(a, b, k):
    if k <= 0: return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


def sd_chain(P, pts, radii, k=0.3):
    """Smoothly joined round cones through pts with radius radii at each point."""
    d = None
    for i in range(len(pts) - 1):
        e = sd_round_cone(P, pts[i], pts[i + 1], radii[i], radii[i + 1])
        d = e if d is None else smin(d, e, k)
    return d


def sd_torus(P, c, axis, R, r):
    axis = nrm(axis); q = P - c
    h = q @ axis
    rad = np.linalg.norm(q - np.outer(h, axis), axis=1)
    return np.sqrt((rad - R) ** 2 + h * h) - r


def sd_plane(P, p0, n):
    """Signed distance to a plane, positive on the side the normal points to."""
    return (P - p0) @ nrm(n)


def shell(d, offset, thick):
    """A layer of the given thickness centred offset outside the surface d = 0."""
    return np.abs(d - offset) - thick * 0.5


def rot_axes(x, y):
    """3x3 matrix whose columns are an orthonormal frame with x and y as given (z = x cross y)."""
    x = nrm(x); y = nrm(y - x * (x @ y)); z = np.cross(x, y)
    return np.column_stack([x, y, z])


def stretched(P, a, normal, k):
    """Points scaled by k along normal about a (used to flatten round cones into ribbons)."""
    n = nrm(normal)
    return P + np.outer((P - a) @ n, n) * (k - 1.0)


def flat_chain(P, pts, widths, normal, k=2.6, blend=0.3, legacy=False):
    """Round cones through pts, flattened by k along normal into a ribbon. (legacy: the original variant that
    flattens only the evaluation points, which also pulls the ribbon toward the plane through pts[0].)"""
    Q = stretched(P, pts[0], normal, k)
    if not legacy:
        pts = [stretched(np.atleast_2d(p), pts[0], normal, k)[0] for p in pts]
    return sd_chain(Q, pts, widths, blend) / k ** 0.5


def smooth01(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------------------
# Proportions: a little under three heads tall. Rest pose is an A-pose with the arms 40 degrees down and the
# elbows and knees slightly bent (good for IK and for Unreal's retargeter).
# ---------------------------------------------------------------------------
HEAD_C = np.array([0.0, 0.4, 80.6])            # centre of the cranium; the chin is about 19 cm below it
Z = dict(ankle=6.4, knee=19.6, hip=34.8, pelvis=36.0, waist=43.6, chest=50.0, shoulder=55.6, neck=57.8)
ARM_DOWN = math.radians(40)
SASH_KNOT = np.array([8.6, -3.6, 42.2])        # where the sash is tied, on Kai's left hip
WRIST_R, WRIST_CUT, ANKLE_R = 2.35, 0.4, 2.45  # seam sizes shared by neighbouring slots


def arm_points(s):
    S = np.array([9.6 * s, 0.6, Z["shoulder"]])
    d1 = nrm([math.cos(ARM_DOWN) * s, -0.06, -math.sin(ARM_DOWN)])
    E = S + d1 * 12.6
    d2 = nrm(d1 + np.array([0.0, -0.17, -0.05]))             # the forearm bends a little forward
    W = E + d2 * 11.2
    return S, E, W, d2


def leg_points(s):
    H = np.array([6.2 * s, 0.4, Z["hip"]])
    K = np.array([6.6 * s, -0.6, Z["knee"]])
    A = np.array([7.0 * s, 0.9, Z["ankle"]])
    B = np.array([7.5 * s, -8.4, 2.0])                        # ball of the foot
    T = np.array([7.6 * s, -13.0, 2.0])                       # toe tip
    return H, K, A, B, T


def hand_frame(s):
    """Wrist position and the hand's axes: f along the fingers, n out of the back of the hand, t toward the thumb."""
    S, E, W, d2 = arm_points(s)
    f = nrm(d2 + np.array([0.0, 0.0, -0.12]))
    n = nrm(np.cross(f, np.array([0.0, 1.0, 0.0])) * s + np.array([0.0, 0.25, 0.0]))
    n = nrm(n - f * (n @ f))
    t = nrm(np.cross(n, f)) * s
    if t[1] > 0: t = -t                                       # the thumb points forward
    return W, f, n, t


HAND_K = 1.2
FINGERS = [  # name, base offset along (f, t, n) from the wrist, segment lengths, radius, splay, curl (degrees)
    ("index", (5.4, 1.75, 0.15), (1.9, 1.35, 1.15), 0.8, 6, 14),
    ("middle", (5.7, 0.55, 0.2), (2.05, 1.45, 1.2), 0.82, 1, 16),
    ("ring", (5.5, -0.65, 0.15), (1.9, 1.35, 1.1), 0.78, -4, 18),
    ("pinky", (5.0, -1.75, 0.05), (1.55, 1.1, 0.95), 0.7, -10, 20),
]


def finger_points(s, name):
    W, f, n, t = hand_frame(s)
    k = HAND_K
    for nm, (bf, bt, bnn), segs, r, splay, curl in FINGERS:
        if nm != name: continue
        p = W + (f * bf + t * bt + n * bnn) * k
        d = nrm(f * math.cos(math.radians(splay)) + t * math.sin(math.radians(splay)))
        pts = [p]; ang = 0.0
        for L in segs:
            ang += math.radians(curl)
            dd = nrm(d * math.cos(ang) - n * math.sin(ang))
            p = p + dd * L * k; pts.append(p)
        return pts, r * k
    if name == "thumb":
        p = W + (f * 1.6 + t * 2.0 - n * 0.6) * k
        d = nrm(f * 0.55 + t * 0.7 - n * 0.45)
        pts = [p]
        for L, bend in ((1.9, 0.0), (1.5, 12.0), (1.25, 14.0)):
            d = nrm(d * math.cos(math.radians(bend)) + f * math.sin(math.radians(bend)))
            p = p + d * L * k; pts.append(p)
        return pts, 0.97 * k
    raise KeyError(name)


# ---------------------------------------------------------------------------
# Vectorised ray casting against an SDF
# ---------------------------------------------------------------------------
def ray_hits(origins, dirs, sdf, t_max=40.0, steps=400, iters=30):
    """For each ray, the first point where sdf < 0 (origins (n,3), dirs (n,3)). Rays that miss return nan."""
    origins = np.atleast_2d(origins).astype(float); dirs = np.atleast_2d(dirs).astype(float)
    dirs = dirs / np.linalg.norm(dirs, axis=1, keepdims=True)
    n = len(origins)
    ts = np.linspace(0.0, t_max, steps)
    d = sdf((origins[:, None, :] + ts[None, :, None] * dirs[:, None, :]).reshape(-1, 3)).reshape(n, steps)
    inside = d < 0
    hit = inside.any(1)
    i = np.where(hit, np.argmax(inside, 1), 1)
    lo = ts[np.maximum(i - 1, 0)]; hi = ts[i]
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        m = sdf(origins + mid[:, None] * dirs) < 0
        hi = np.where(m, mid, hi); lo = np.where(m, lo, mid)
    out = origins + hi[:, None] * dirs
    out[~hit] = np.nan
    return out


def sdf_normals(P, sdf, h=0.02):
    P = np.atleast_2d(P)
    g = np.column_stack([sdf(P + np.array(e) * h) - sdf(P - np.array(e) * h) for e in np.eye(3)])
    return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)


# ---------------------------------------------------------------------------
# Head
# ---------------------------------------------------------------------------
EAR = dict(dy=1.6, dz=-3.2)                            # where the ear's front edge meets the head
EYE = dict(x=6.9, dz=-3.4, a=4.0, b=5.3, tilt=5.0,   # centre, half width, half height (cm), lean of the tops (deg)
           R=10.0, pop=0.1, rim=0.45)             # eyeball radius, eye white's centre above the face, skin rim above it
IRIS = dict(a=2.75, b=3.45)                            # iris half width and half height
BROW = dict(dz=4.9, x0=2.3, x1=10.4, arch=0.5, slant=0.35, w=1.95, t=0.9)
MOUTH = dict(dz=-12.4)


def head_core_sdf(P):
    """Head without ears or eye windows: big round cranium, soft cheeks, small chin, small pointed nose, neck."""
    C = HEAD_C
    d = sd_ellipsoid(P, C, np.array([16.6, 17.2, 17.4]))
    d = smin(d, sd_ellipsoid(P, C + [0, -2.8, -6.4], np.array([14.6, 13.6, 12.6])), 5.0)       # cheeks and jaw
    d = smin(d, sd_ellipsoid(P, C + [0, -8.6, -14.6], np.array([5.6, 5.0, 4.4])), 4.0)        # chin
    d = smin(d, sd_ellipsoid(P, C + [0, -16.0, -5.5], np.array([1.1, 1.8, 1.3]),
                             rot_axes([1, 0, 0], [0, 1, 0.25])), 1.3)                                # small pointed nose
    return smin(d, sd_capsule(P, (0, 0.6, Z["neck"] - 1.5), (0, 0.8, C[2] - 8.0), 4.75), 2.5)     # neck


_EAR = {}


def ear_frame(s):
    """Origin on the side of the head and the ear's axes: u toward the back, v up (leaning back), n out of the ear."""
    key = float(s)
    if key in _EAR: return _EAR[key]
    n = nrm([0.86 * s, -0.36, 0.08])                                  # faces out and a little forward
    v = nrm(UP - n * (n @ UP))
    b = nrm(np.cross(n, v)); b = b if b[1] > 0 else -b
    lean = math.radians(14)                                            # the top of the ear leans back
    v, b = nrm(v * math.cos(lean) + b * math.sin(lean)), nrm(b * math.cos(lean) - v * math.sin(lean))
    z = HEAD_C[2] + EAR["dz"]
    O = ray_hits(np.array([30.0 * s, HEAD_C[1] + EAR["dy"], z]), np.array([-s, 0.0, 0.0]), head_core_sdf, t_max=30.0)[0]
    _EAR[key] = (O - n * 0.35, b, v, n)
    return _EAR[key]


def ear_local(P, s):
    O, b, v, n = ear_frame(s)
    q = P - O
    return np.column_stack([q @ b, q @ v, q @ n])


def _ear_rim():
    """Rim (helix) of the ear: a smooth C from the top front, round the top and back, down to the lobe. Finely sampled,
    and joined with a plain union, so the tube has no bumps at the joints for the cel shading to pick out."""
    pts = []
    for th in np.linspace(math.radians(148), math.radians(-112), 48):
        f = (math.radians(148) - th) / math.radians(260)
        pts.append((2.2 + 2.35 * math.cos(th), 0.25 + 3.95 * math.sin(th), 0.52 + 0.4 * f ** 2))
    return pts


EAR_RIM = _ear_rim()
EAR_K = 1.08                                                          # overall ear size
EAR_BOWL = dict(c=(2.05, 0.1), r=(1.8, 3.1))                          # outline of the hollow, in the ear's plane


def ear_sdf(P, s):
    """A stylised ear: a rolled rim curling from the top round to a soft lobe, around one smooth hollow bowl. Kept
    to simple shapes, so a two-tone shader draws it as a clean C."""
    L = ear_local(P, s) / EAR_K
    plate = sd_ellipsoid(L, np.array([2.15, 0.15, 0.55]), np.array([2.7, 4.3, 0.95]))
    rim = None
    for (u0, v0, r0), (u1, v1, r1) in zip(EAR_RIM[:-1], EAR_RIM[1:]):
        e = sd_round_cone(L, np.array([u0, v0, 1.05]), np.array([u1, v1, 1.05]), r0, r1)
        rim = e if rim is None else np.minimum(rim, e)
    d = smin(plate, rim, 0.6)
    d = smin(d, sd_ellipsoid(L, np.array([1.7, -3.2, 0.7]), np.array([1.5, 1.2, 0.95])), 0.8)       # lobe
    bowl = sd_ellipsoid(L, np.array([*EAR_BOWL["c"], 1.95]), np.array([*EAR_BOWL["r"], 1.3]))
    d = smax(d, -bowl, 1.0)
    return smax(d, -L[:, 2] - 0.8, 0.3) * EAR_K                         # nothing behind the root


def ear_zone(P, s):
    """Below 1 on and around the ear on side s (an ellipsoid in the ear's frame)."""
    L = ear_local(P, s) / EAR_K
    return np.linalg.norm((L - np.array([2.1, 0.0, 0.3])) / np.array([4.0, 5.6, 3.0]), axis=1)


def _sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ear_normals(P, N):
    """Shading normals for the ears, the usual toon trick: normals taken from the smooth shape itself rather than
    the triangles, and the inside of the bowl turned to face the way the ear faces, so the hollow shades as one
    tone with a clean lit (or shaded) crescent along the rim instead of patches. Fades into N at the zone's edge."""
    N = np.array(N, float)
    for side, s in SIDES:
        r = ear_zone(P, s); m = r < 1.0
        if not m.any(): continue
        n = ear_frame(s)[3]
        Ns = sdf_normals(P[m], head_base_sdf, h=0.06)
        L = ear_local(P[m], s) / EAR_K
        e = np.hypot((L[:, 0] - EAR_BOWL["c"][0]) / EAR_BOWL["r"][0], (L[:, 1] - EAR_BOWL["c"][1]) / EAR_BOWL["r"][1])
        w = (1 - _sstep(0.7, 0.95, e)) * _sstep(-0.5, 0.0, L[:, 2]) * _sstep(0.0, 0.5, Ns @ n)
        Ns = Ns * (1 - w[:, None]) + n * w[:, None]
        Ns /= np.linalg.norm(Ns, axis=1, keepdims=True)
        f = (1 - _sstep(0.75, 1.0, r[m]))[:, None]
        Nm = N[m] * (1 - f) + Ns * f
        N[m] = Nm / np.linalg.norm(Nm, axis=1, keepdims=True)
    return N


def head_base_sdf(P):
    """Head with ears, without eye windows."""
    d = head_core_sdf(P)
    for side, s in SIDES:
        d = smin(d, ear_sdf(P, s), 0.9)
    return d


_EYES = {}
_FACE = {}


def eye_layout():
    """Eye pivots and frames. Each eye is a round eyeball (EYE["R"]) whose centre sits EYE["pop"] proud of the face, so
    the eyes bulge out of the head rather than sitting in sockets."""
    if _EYES: return _EYES
    for side, s in SIDES:
        c = ray_hits(np.array([EYE["x"] * s, -40.0, HEAD_C[2] + EYE["dz"]]), np.array([0.0, 1.0, 0.0]), head_base_sdf)[0]
        n = nrm(sdf_normals(c, head_base_sdf)[0] * 0.75 + FWD * 0.25)    # look a little more forward than the skin
        u0 = nrm(np.cross(UP, n)); v0 = nrm(np.cross(n, u0))           # u0 toward +X, v0 up
        tilt = -math.radians(EYE["tilt"]) * s                             # the tops of the eyes lean outward
        u = nrm(u0 * math.cos(tilt) + v0 * math.sin(tilt)); v = nrm(np.cross(n, u))
        R = EYE["R"]
        _EYES[side] = dict(center=c, n=n, u=u, v=v, pivot=c + n * (EYE["pop"] - R), R=R, a=EYE["a"], b=EYE["b"])
    return _EYES


def _eye_dome_weight(P, e):
    """1 over the eye and just around it, fading to 0 by 1.8 times the eye's size; only in front of the pivot."""
    q = P - e["pivot"]
    rho = np.hypot(q @ e["u"] / e["a"], q @ e["v"] / e["b"])
    return (1 - _sstep(1.2, 1.8, rho)) * _sstep(0.0, 3.0, q @ e["n"])


def head_skin_sdf(P):
    """Head with ears, and the skin around each eye drawn into a soft dome that sits EYE["rim"] above the eyeball,
    so the rim of the eye opening is the same small height all round (room for the hidden lids, no deep socket)."""
    d = head_base_sdf(P)
    for side, s in SIDES:
        e = eye_layout()[side]
        w = _eye_dome_weight(P, e); m = w > 0
        if m.any():
            dome = np.linalg.norm(P[m] - e["pivot"], axis=1) - (e["R"] + EYE["rim"])
            d[m] = d[m] * (1 - w[m]) + dome * w[m]
    return d


def eye_dome_normals(P, N):
    """Shading normals over the eye domes taken from the face without them (head_base_sdf): the domes push the eyes
    out in silhouette, but the face still shades as one smooth surface, with no shadow ring round the eyes."""
    N = np.array(N, float)
    for side, s in SIDES:
        e = eye_layout()[side]
        q = P - e["pivot"]
        rho = np.hypot(q @ e["u"] / e["a"], q @ e["v"] / e["b"])
        w = (1 - _sstep(1.8, 2.3, rho)) * _sstep(0.0, 3.0, q @ e["n"])   # the whole dome, fading out past its edge
        m = w > 0
        if not m.any(): continue
        Nb = sdf_normals(P[m], head_base_sdf, h=0.06)
        Nm = N[m] * (1 - w[m, None]) + Nb * w[m, None]
        N[m] = Nm / np.linalg.norm(Nm, axis=1, keepdims=True)
    return N


def face_layout():
    """Eye pivots and frames, brow and mouth placement, all fitted to the skin."""
    if _FACE: return _FACE
    brows = {}
    for side, s in SIDES:
        c = ray_hits(np.array([(BROW["x0"] + BROW["x1"]) * 0.5 * s, -40.0, HEAD_C[2] + BROW["dz"]]),
                     np.array([0.0, 1.0, 0.0]), head_skin_sdf)[0]
        brows[side] = dict(center=c, n=sdf_normals(c, head_skin_sdf)[0])
    mc = ray_hits(np.array([0.0, -40.0, HEAD_C[2] + MOUTH["dz"]]), np.array([0.0, 1.0, 0.0]), head_skin_sdf)[0]
    _FACE.update(eyes=eye_layout(), brows=brows, mouth=dict(center=mc, n=sdf_normals(mc, head_skin_sdf)[0]))
    return _FACE


def eye_window_sdf(P, e):
    """Region in front of the eye sphere inside the eye's oval: subtracted from the head to open the window."""
    q = P - e["pivot"]
    x, y, w = q @ e["u"], q @ e["v"], q @ e["n"]
    a, b = e["a"], e["b"]
    oval = (np.sqrt((x / a) ** 2 + (y / b) ** 2) - 1.0) * min(a, b)
    behind = (e["R"] - 0.6) - np.linalg.norm(q, axis=1)
    return np.maximum(np.maximum(oval, behind), -w)


def head_sdf(P):
    d = head_skin_sdf(P)
    F = face_layout()
    for side, s in SIDES:
        d = smax(d, -eye_window_sdf(P, F["eyes"][side]), 0.2)
    return d


HEAD_BOX = ((-19.5, 19.5), (-19.5, 20.0), (Z["neck"] - 9.0, HEAD_C[2] + 18.5))


# Face features as explicit meshes: (verts, faces, local coordinates per vertex)
def _grid(nx, ny):
    f = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            f.append((a, a + 1, a + nx + 1, a + nx))
    return np.array(f)


def sphere_patch(e, radius, xs, ys):
    """Grid on the eye's sphere, parametrised by tangent-plane coordinates (x along u, y along v)."""
    X, Y = np.meshgrid(xs, ys)
    return e["pivot"] + sphere_dirs(e, X.ravel(), Y.ravel()) * radius, X.ravel(), Y.ravel()


def sphere_dirs(e, X, Y):
    """Directions from the eye's pivot to the points that sit X, Y across the eye (along u, v) on its sphere."""
    X, Y = X / e["R"], Y / e["R"]
    return (X[:, None] * e["u"][None] + Y[:, None] * e["v"][None]
            + np.sqrt(np.maximum(1 - X * X - Y * Y, 0.0))[:, None] * e["n"][None])


def keep_faces(faces, keep_vert):
    f = faces[keep_vert[faces].all(1)]
    used = np.unique(f); remap = -np.ones(keep_vert.size, int); remap[used] = np.arange(len(used))
    return used, remap[f]


def eye_pieces(side):
    """Eye white, iris, upper and lower lids for one eye. Returns {name: (verts, faces, local(n,2))}."""
    e = face_layout()["eyes"][side]; a, b, R = e["a"], e["b"], e["R"]
    out = {}
    xs = np.linspace(-a - 1.0, a + 1.0, 30); ys = np.linspace(-b - 1.0, b + 1.0, 38)
    V, X, Y = sphere_patch(e, R, xs, ys)
    used, F = keep_faces(_grid(len(xs), len(ys)), (X / (a + 1.0)) ** 2 + (Y / (b + 1.0)) ** 2 < 1.35)
    out["sclera"] = (V[used], F, np.column_stack([X[used] / a, Y[used] / b]))
    # iris: polar grid, slightly in front of the white
    nr, na = 10, 40
    rr = np.linspace(0, 1, nr); aa = np.linspace(0, 2 * math.pi, na, endpoint=False)
    X = np.outer(rr, np.cos(aa)).ravel() * IRIS["a"]; Y = np.outer(rr, np.sin(aa)).ravel() * IRIS["b"]
    V = e["pivot"] + sphere_dirs(e, X, Y) * (R + 0.08)
    F = []
    for i in range(nr - 1):
        for j in range(na):
            j2 = (j + 1) % na
            F.append((i * na + j, i * na + j2, (i + 1) * na + j2, (i + 1) * na + j))
    out["iris"] = (V, np.array(F), np.column_stack([X / IRIS["a"], Y / IRIS["b"]]))
    # lids: skin-coloured caps that rest hidden under the skin above and below the eye and swing over it. Each column
    # sits at a fixed distance x along the hinge axis u, and its rows are angles about that axis, so turning the lid
    # bone by lid_close_angle slides the lid exactly over the eye at any eyeball size.
    xs = np.linspace(-a - 1.1, a + 1.1, 28)
    t = np.linspace(0, 1, 18)
    for name, sign, radius in (("lid_upper", 1.0, R + 0.22), ("lid_lower", -1.0, R + 0.13)):
        edge = (b + 0.35 if sign > 0 else b + 0.5) - (0.3 if sign > 0 else 0.25) * b * np.clip(xs / a, -1.2, 1.2) ** 2
        ca = np.sqrt(1 - (xs / R) ** 2)                                      # cos of the column's angle off the n-v plane
        phi0 = np.arcsin(edge / (R * ca))                                    # angle of the lid's edge about u, at rest
        span = lid_close_angle(side, "upper" if sign > 0 else "lower") + 0.12
        phi = sign * (phi0[None] + t[:, None] * span)                        # rows from the edge outward
        X = np.repeat((xs / radius * (radius / R))[None], len(t), 0)         # sin of the column's angle
        C = np.sqrt(1 - X ** 2)
        dirs = (X[..., None] * e["u"] + C[..., None] * (np.cos(phi)[..., None] * e["n"]
                                                        + np.sin(phi)[..., None] * e["v"])).reshape(-1, 3)
        V = e["pivot"] + dirs * radius
        F = _grid(len(xs), len(t))
        if sign < 0: F = F[:, ::-1]
        dist = (np.abs(phi) - phi0[None]) * R * ca[None]                     # cm from the lid's edge
        out[name] = (V, F, np.column_stack([(xs[None].repeat(len(t), 0) / a).ravel(), dist.ravel()]))
    return out


def lid_close_angle(side, which="upper"):
    """Rotation (radians, about the lid bone's local X) that closes the lid: the upper lid comes down to the bottom
    of the eye, the lower lid rises to the middle."""
    e = face_layout()["eyes"][side]; R, b = e["R"], e["b"]
    if which == "upper":
        return float(np.arcsin((b + 0.35) / R) + np.arcsin((b + 0.25) / R))
    return float(np.arcsin((b + 0.5) / R))


def surface_offset(points, sdf, offset, dirs=None):
    """Project points onto the surface along dirs (default: +Y, from the front) and push them out by offset."""
    points = np.atleast_2d(points)
    if dirs is None: dirs = np.repeat(np.array([[0.0, 1.0, 0.0]]), len(points), 0)
    hits = ray_hits(points - dirs * 20.0, dirs, sdf, t_max=80.0, steps=640)
    return hits + sdf_normals(hits, sdf) * offset


def brow_piece(side):
    """A thick, tapered stroke over the eye, standing just off the forehead."""
    s = 1.0 if side == "L" else -1.0
    us = np.linspace(0, 1, 22)
    x = (BROW["x0"] + (BROW["x1"] - BROW["x0"]) * us) * s
    zc = HEAD_C[2] + BROW["dz"] + BROW["arch"] * np.sin(math.pi * us) + BROW["slant"] * us
    spine = surface_offset(np.column_stack([x, np.full_like(x, -40.0), zc]), head_skin_sdf, 0.45)
    N = sdf_normals(spine, head_skin_sdf)
    T = np.gradient(spine, axis=0); T /= np.linalg.norm(T, axis=1, keepdims=True)
    W = np.cross(N, T); W /= np.linalg.norm(W, axis=1, keepdims=True)
    width = BROW["w"] * (0.95 + 0.15 * np.sin(math.pi * us)) * (1 - 0.25 * us)            # thick and straight
    width[0] *= 0.8; width[-1] *= 0.6
    na = 12; ang = np.linspace(0, 2 * math.pi, na, endpoint=False)
    V = []
    for i in range(len(us)):
        for aa in ang:
            V.append(spine[i] + W[i] * math.cos(aa) * width[i] * 0.5 + N[i] * math.sin(aa) * BROW["t"] * 0.5 * (width[i] / BROW["w"]))
    V = np.array(V); F = []
    for i in range(len(us) - 1):
        for j in range(na):
            j2 = (j + 1) % na
            F.append((i * na + j, i * na + j2, (i + 1) * na + j2, (i + 1) * na + j))
    c0 = len(V); V = np.vstack([V, spine[0], spine[-1]])
    last = (len(us) - 1) * na
    for j in range(na):
        F.append((c0, (j + 1) % na, j)); F.append((c0 + 1, last + j, last + (j + 1) % na))
    local = np.column_stack([np.concatenate([np.repeat(us, na), [0.0, 1.0]]), np.zeros(len(V))])
    return V, F, local


MOUTH_SHAPES = {   # top and bottom edge of the mouth as functions of s in -1..1 (cm, relative to the mouth centre)
    "rest": dict(w=2.7, top=lambda s: 0.5 * s * s + 0.06, bot=lambda s: 0.5 * s * s - 0.22 * (1 - s * s)),
    "Mouth_Smile": dict(w=2.9, top=lambda s: 0.95 * s * s - 0.05, bot=lambda s: 0.95 * s * s - 0.65 * (1 - s * s) ** 0.8),
    "Mouth_Open": dict(w=2.4, top=lambda s: 0.25 * s * s + 0.1, bot=lambda s: 0.25 * s * s - 2.0 * (1 - s * s) ** 0.75),
    "Mouth_Shout": dict(w=2.9, top=lambda s: 0.55 * (1 - s * s) ** 0.6 + 0.15 * s * s, bot=lambda s: -2.6 * (1 - s * s) ** 0.6),
    "Mouth_O": dict(w=1.25, top=lambda s: 0.85 * (1 - s * s) ** 0.5, bot=lambda s: -1.2 * (1 - s * s) ** 0.5),
    "Mouth_Frown": dict(w=2.0, top=lambda s: -0.45 * s * s + 0.1, bot=lambda s: -0.45 * s * s - 0.12 * (1 - s * s)),
}


def mouth_piece():
    """Mouth as a thin decal on the face, with shape keys for expressions. Returns verts, faces, local, {key: verts}."""
    M = face_layout()["mouth"]
    c = M["center"]
    ns, nt = 30, 8
    s = np.linspace(-1, 1, ns); t = np.linspace(0, 1, nt)
    S, T = np.meshgrid(s, t)
    F = _grid(ns, nt)
    keys = {}
    for name, sh in MOUTH_SHAPES.items():
        top, bot = sh["top"](S), sh["bot"](S)
        bot = np.minimum(bot, top - 0.04)
        x = S * sh["w"]; y = bot + (top - bot) * T
        pts = np.column_stack([x.ravel(), np.full(x.size, -40.0), c[2] + y.ravel()])
        keys[name] = surface_offset(pts, head_skin_sdf, 0.07)
    local = np.column_stack([S.ravel(), T.ravel()])
    return keys["rest"], F, local, {k: v for k, v in keys.items() if k != "rest"}


# ---------------------------------------------------------------------------
# Tunic slot: tunic, sailor collar, arms
# ---------------------------------------------------------------------------
def torso_core(P):
    """Kai's torso as the tunic fits it: a kid's chest and belly, shoulders that slope down from the neck."""
    d = sd_ellipsoid(P, np.array([0, 0.6, Z["chest"]]), np.array([9.5, 7.2, 7.4]))
    d = smin(d, sd_ellipsoid(P, np.array([0, 0.4, Z["waist"]]), np.array([9.1, 7.0, 5.6])), 3.0)
    d = smin(d, sd_capsule(P, (-6.0, 0.6, Z["shoulder"] - 2.6), (6.0, 0.6, Z["shoulder"] - 2.6), 3.7), 3.0)
    for side, s in SIDES:
        S = arm_points(s)[0]
        d = smin(d, sd_sphere(P, S + np.array([-0.7 * s, 0, -0.9]), 3.45), 2.4)
    return d


HEM_Z = 31.2


def vneck(P):
    vx = np.abs(P[:, 0]) - 0.62 * (P[:, 2] - (Z["chest"] + 0.6))
    return np.maximum(np.maximum(vx * 0.85, -(P[:, 1] + 2.0)), Z["chest"] + 0.2 - P[:, 2])


def tunic_sdf(P):
    d = torso_core(P)
    Q = P.copy(); Q[:, 1] = (Q[:, 1] - 0.4) / 0.84 + 0.4                 # flared skirt, elliptic in section
    d = smin(d, sd_round_cone(Q, (0, 0.4, Z["waist"]), (0, 0.4, HEM_Z + 1.0), 9.3, 12.6), 3.0)
    for side, s in SIDES:
        S, E, W, d2 = arm_points(s)
        d1 = nrm(E - S); end = S + d1 * 6.6
        sl = smax(sd_round_cone(P, S - d1 * 1.2, end, 3.75, 3.55), sd_plane(P, end, d1), 0.25)
        d = smin(d, sl, 1.8)
    return smax(d, sd_plane(P, (0, 0, HEM_Z), (0, 0, -1)), 0.35)            # hem (the neck simply passes into it)


def collar_region(P):
    """Negative where the sailor collar lies: a square flap down the back, a band over the shoulders and two
    lapels along the V-neck."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    zs = Z["shoulder"]
    back = np.maximum.reduce([np.abs(x) - 8.8, (zs - 8.2) - z, -y - 1.0])
    band = (zs - 1.4) - z
    vx = np.abs(x) - 0.62 * (z - (Z["chest"] + 0.6))
    lapel = np.maximum.reduce([-vx, vx - 3.3, -(y + 1.0), Z["chest"] - z])
    return np.minimum(np.minimum(back, band), lapel)


def collar_sdf(P):
    d = smax(shell(tunic_sdf(P), 0.4, 0.45), collar_region(P), 0.2)
    return smax(d, -sd_capsule(P, (0, 0.5, Z["neck"] - 3.0), (0, 0.5, Z["neck"] + 12.0), 4.3), 0.3)


def tunic_part_sdf(P):
    return np.minimum(tunic_sdf(P), collar_sdf(P))


TUNIC_BOX = ((-26, 26), (-13, 13), (HEM_Z - 1.5, Z["neck"] + 6))


# ---------------------------------------------------------------------------
# Pants slot (pants and lower legs), sandals slot (feet and sandals), hands slot
# ---------------------------------------------------------------------------
def cuff_point(s):
    H, K, A, Bl, T = leg_points(s)
    return K + (A - K) * 0.4


def pants_sdf(P):
    d = sd_ellipsoid(P, np.array([0, 0.6, Z["pelvis"] + 1.6]), np.array([9.4, 7.0, 7.2]))
    d = smax(d, sd_plane(P, (0, 0, Z["waist"] + 1.0), (0, 0, 1)), 0.4)      # top tucked under the tunic
    for side, s in SIDES:
        H, K, A, Bl, T = leg_points(s)
        C = cuff_point(s); ax = nrm(C - K)
        leg = smax(sd_chain(P, [H + np.array([-0.5 * s, 0, 1.5]), K, C], [5.0, 5.15, 5.4], 0.8), sd_plane(P, C, ax), 0.3)
        d = smin(d, leg, 2.6)
        d = smin(d, sd_torus(P, C - ax * 0.3, ax, 5.1, 1.2), 0.4)
    return d


PANTS_BOX = ((-17, 17), (-12, 12), (8.0, Z["waist"] + 3))


SOLE_TOP = 1.5                                          # the foot stands on the sole at this height


def ankle_band(s):
    """Height range (z0, z1) of the sandal's ankle strap, which hides where the calf meets the foot."""
    A = leg_points(s)[2]
    return A[2] - 1.7, A[2] + 0.5


def toe_points(s):
    """Five toes along the front of the foot, big toe on the inside: (centre, radius)."""
    H, K, A, Bl, T = leg_points(s)
    out = []
    for dx, dy, r in ((-2.05, -4.45, 1.05), (-0.7, -4.4, 0.8), (0.45, -4.15, 0.74), (1.5, -3.75, 0.67), (2.4, -3.2, 0.6)):
        out.append((np.array([Bl[0] + dx * s, Bl[1] + dy, SOLE_TOP + r * 0.92]), r))
    return out


def foot_skin_sdf(P, s):
    """A chunky toon foot: tall at the ankle, tapering over the instep to a low, wide front with sculpted toes and a
    flat sole; it starts just under the top of the ankle strap."""
    H, K, A, Bl, T = leg_points(s)
    Q = P.copy(); Q[:, 0] = A[0] + (P[:, 0] - A[0]) / 1.3                 # feet are wider than they are tall
    heel = np.array([A[0], A[1] + 1.5, SOLE_TOP + 1.9])
    inst = np.array([A[0] + 0.1 * s, A[1] - 4.2, SOLE_TOP + 2.1])
    ball = np.array([Bl[0] + 0.1 * s, Bl[1] + 0.6, SOLE_TOP + 1.45])
    d = sd_round_cone(P, A + np.array([0, 0, 1.0]), A + np.array([0, -0.4, -1.4]), ANKLE_R - 0.08, 2.3)
    d = smin(d, sd_sphere(Q, heel, 1.95), 2.0)
    d = smin(d, sd_round_cone(Q, A + np.array([0, -0.6, -1.0]), inst, 2.1, 2.05), 1.2)
    d = smin(d, sd_round_cone(Q, inst, ball, 2.05, 1.55), 1.0)
    d = smin(d, sd_ellipsoid(P, np.array([Bl[0] + 0.2 * s, Bl[1] - 1.8, SOLE_TOP + 1.15]), np.array([3.55, 2.7, 1.25])), 1.0)
    toes = None
    for c, r in toe_points(s):
        t = sd_ellipsoid(P, c, np.array([r, r * 1.25, r * 0.92]))
        toes = t if toes is None else smin(toes, t, 0.25)
    d = smin(d, toes, 0.55)
    d = smax(d, SOLE_TOP - 0.12 - P[:, 2], 0.25)                        # flat underneath, resting on the sole
    return smax(d, P[:, 2] - (ankle_band(s)[1] - 0.25), 0.1)          # ends under the ankle strap


def leg_skin_sdf(P, s):
    """Calf and ankle: from inside the pants leg down to under the sandal's ankle strap."""
    H, K, A, Bl, T = leg_points(s); C = cuff_point(s)
    calf = sd_chain(P, [K + (C - K) * 0.3, C + (A - C) * 0.4, A + np.array([0, 0, -0.6])], [3.9, 3.45, ANKLE_R - 0.05], 0.8)
    return smax(calf, (ankle_band(s)[0] + 0.25) - P[:, 2], 0.1)


def legs_sdf(P):
    return np.minimum(leg_skin_sdf(P, 1.0), leg_skin_sdf(P, -1.0))


LEGS_BOX = ((-15, 15), (-12, 11), (Z["ankle"] - 3, Z["knee"] + 2))


def sandal_sdf(P):
    """Feet and sandals as one fused piece (like boots, footwear owns the feet), so the straps can never cut into
    the feet: sole, toe strap, instep strap, a T-strap up to the ankle strap, and the ankle strap around the calf."""
    d = None
    for side, s in SIDES:
        H, K, A, Bl, T = leg_points(s)
        foot = foot_skin_sdf(P, s)
        xy = P.copy(); xy[:, 2] = 0
        o = smin(sd_ellipsoid(xy, np.array([A[0], A[1] + 1.1, 0]), np.array([3.6, 4.3, 1])),
                 sd_ellipsoid(xy, np.array([Bl[0] + 0.15 * s, Bl[1] - 2.2, 0]), np.array([4.6, 5.0, 1])), 4.0) * 3.0
        sole = smax(o, np.abs(P[:, 2] - SOLE_TOP * 0.5) - SOLE_TOP * 0.5, 0.45)
        layer = shell(foot, 0.25, 0.5)
        y_toe = Bl[1] - 0.9; y_inst = (A[1] + Bl[1]) * 0.5 - 0.3
        toe = np.abs(P[:, 1] - y_toe) - 0.8
        inst = np.abs(P[:, 1] - y_inst) - 0.8
        tee = np.maximum(np.abs(P[:, 0] - (A[0] + Bl[0]) * 0.5 - 0.15 * s) - 0.7, SOLE_TOP + 2.0 - P[:, 2])
        tee = np.maximum(tee, np.maximum(P[:, 1] - A[1] + 0.6, y_inst - P[:, 1]))
        straps = smax(smax(layer, np.minimum.reduce([toe, inst, tee]), 0.12), SOLE_TOP - 0.2 - P[:, 2], 0.2)
        z0, z1 = ankle_band(s)
        skin = smin(leg_skin_sdf(P, s), foot, 0.6)
        around = np.hypot(P[:, 0] - A[0], P[:, 1] - A[1]) - (ANKLE_R + 1.0)    # only around the ankle itself
        ank = smax(shell(skin, 0.42, 0.5), np.maximum.reduce([z0 - P[:, 2], P[:, 2] - z1, around]), 0.12)
        part = smin(smin(smin(sole, foot, 0.15), straps, 0.2), ank, 0.2)
        d = part if d is None else np.minimum(d, part)
    return d


SANDAL_BOX = ((-15, 15), (-18, 11), (-1, Z["ankle"] + 3.0))


def arm_skin_sdf(P, s):
    """Upper arm (from inside the sleeve), forearm and hand as one smooth piece of skin."""
    S, E, W, d2 = arm_points(s)
    Wf, f, n, t = hand_frame(s)
    k = HAND_K
    d1 = nrm(E - S)
    h = sd_chain(P, [S - d1 * 1.2, E, W], [3.2, 2.8, 2.2], 0.7)
    R = np.column_stack([f, t, n])
    h = smin(h, sd_ellipsoid(P, W + (f * 3.0 + n * 0.1 - t * 0.1) * k, np.array([3.05, 2.75, 1.4]) * k, R), 1.5)
    fingers = None
    for fn in ("thumb", "index", "middle", "ring", "pinky"):
        pts, r = finger_points(s, fn)
        if fn == "thumb": pts = [pts[0] - (pts[1] - pts[0]) * 0.4] + pts[1:]
        fg = sd_chain(P, pts, [r * 1.05, r, r * 0.92, r * 0.86], 0.25)
        fingers = fg if fingers is None else smin(fingers, fg, 0.12)
    return smin(h, fingers, 0.7)


def arms_sdf(P):
    return np.minimum(arm_skin_sdf(P, 1.0), arm_skin_sdf(P, -1.0))


def _arms_box():
    pts = []
    for side, s in SIDES:
        S, E, W, d2 = arm_points(s)
        pts += [S, E, W]
        for fn in ("thumb", "index", "middle", "ring", "pinky"): pts += finger_points(s, fn)[0]
    pts = np.array(pts)
    return tuple((float(pts[:, i].min() - 5), float(pts[:, i].max() + 5)) for i in range(3))


# ---------------------------------------------------------------------------
# Accessories
# ---------------------------------------------------------------------------
_SASH = {}


def _on_tunic(p, out):
    """Point on the tunic surface in the horizontal direction of p from the body axis, pushed out by out (cm)."""
    d = np.array([p[0], p[1] - 0.4, 0.0]); d /= np.linalg.norm(d)
    origin = np.array([0.0, 0.4, p[2]]) + d * 30.0
    hit = ray_hits(origin, -d, tunic_sdf, t_max=30.0, steps=600)[0]
    return hit + sdf_normals(hit, tunic_sdf)[0] * out


def sash_knot():
    if "knot" not in _SASH: _SASH["knot"] = _on_tunic(SASH_KNOT, 1.35)
    return _SASH["knot"]


def sash_tail_points():
    """Two ribbon tails hanging from the knot, following the flare of the tunic's skirt."""
    if "tails" in _SASH: return _SASH["tails"]
    out = []
    k = sash_knot()
    for (ang, spread), w in (((-14.0, 0.6), (1.5, 1.6, 1.85, 2.05)), ((10.0, 1.4), (1.4, 1.5, 1.7, 1.8))):
        pts = [k + np.array([0, 0, -0.9])]
        for j in range(1, 4):
            z = k[2] - 0.9 - 3.4 * j
            a = math.atan2(k[0], -(k[1] - 0.4)) + math.radians(ang) * j / 3.0
            p = np.array([math.sin(a), -math.cos(a) + 0.4 / 30, 0.0]) * 10.0
            pts.append(_on_tunic(np.array([p[0], p[1], z]), 0.95 + 0.15 * j + spread * 0.1 * j))
        out.append((pts, w))
    _SASH["tails"] = out
    return out


def sash_sdf(P):
    band = smax(shell(tunic_sdf(P), 0.78, 1.3), np.abs(P[:, 2] - (Z["waist"] - 1.2)) - 2.3, 0.45)   # hugs the tunic
    k = sash_knot(); out = nrm(np.array([k[0], k[1] - 0.4, 0.0]))
    knot = sd_ellipsoid(P, k, np.array([2.0, 1.4, 1.75]), rot_axes(np.cross(UP, out), UP))
    d = smin(band, knot, 0.8)
    for pts, w in sash_tail_points():                               # each ribbon lies flat on the skirt beneath it
        nt = nrm(sdf_normals(np.array(pts[1:]), tunic_sdf).mean(0))
        d = smin(d, flat_chain(P, pts, w, nt, 2.8), 0.6)
    return d


SASH_BOX = ((-15, 16), (-13, 13), (Z["waist"] - 15, Z["waist"] + 5))


def neckerchief_sdf(P):
    c = np.array([0, -8.2, Z["chest"] + 1.1])
    d = sd_ellipsoid(P, c, np.array([2.0, 1.3, 1.6]))
    for s in (1, -1):
        pts = [c + np.array([0.5 * s, -0.2, -0.8]), c + np.array([1.7 * s, -0.5, -3.2]), c + np.array([2.5 * s, -0.7, -6.0])]
        d = smin(d, flat_chain(P, pts, (1.15, 1.55, 0.12), [0, -1, 0.15], 2.8), 0.5)
    return d


KERCHIEF_BOX = ((-8, 8), (-12, 8), (Z["chest"] - 8, Z["neck"] + 8))


# ---------------------------------------------------------------------------
# Hair
# ---------------------------------------------------------------------------
CRANIUM_R = np.array([16.6, 17.2, 17.4])


def _sph(phi, el):
    """Direction from the head centre: phi = 0 faces forward, positive toward Kai's left; el up from the equator."""
    p, e = math.radians(phi), math.radians(el)
    return np.array([math.sin(p) * math.cos(e), -math.cos(p) * math.cos(e), math.sin(e)])


def cranium_point(phi, el, out=0.0):
    d = _sph(phi, el)
    return HEAD_C + d * (1.0 / np.linalg.norm(d / CRANIUM_R) + out)


def hairline_el(phi):
    """Elevation (degrees) of the hairline around the head: high on the forehead, above the ears, low at the nape."""
    a = np.abs(phi)
    front = 30.0 + 0 * a
    side = np.interp(a, [0, 40, 70, 95, 120, 180], [30.0, 26.0, 14.0, 12.0, -10.0, -32.0])
    return side


def hair_cap(P, thick):
    """A thin underlayer that fills the gaps between locks (it follows the hairline)."""
    q = P - HEAD_C
    phi = np.degrees(np.arctan2(q[:, 0], -q[:, 1]))
    el = np.degrees(np.arctan2(q[:, 2], np.hypot(q[:, 0], q[:, 1])))
    return smax(sd_ellipsoid(P, HEAD_C, CRANIUM_R + thick), (hairline_el(phi) - el) * 0.3, 1.0)


def clump_points(root, tip, lift=1.5, bulge=2.0, n=7):
    """Path of a lock from root to tip (phi, el): it rises off the head, follows it, and lifts toward the tip."""
    return [cranium_point(root[0] + (tip[0] - root[0]) * t, root[1] + (tip[1] - root[1]) * t,
                          1.8 + bulge * math.sin(math.pi * t) + lift * t * t) for t in np.linspace(0, 1, n)]


def clump(P, root, tip, width, lift=1.5, bulge=2.0, k=1.5, n=7):
    """A broad, flattened lock of hair ending in a point."""
    pts = clump_points(root, tip, lift, bulge, n)
    normal = nrm(pts[n // 2] - HEAD_C)
    widths = [width * (1 - t) ** 0.65 * (0.75 + 0.25 * math.sin(math.pi * min(1.0, t * 1.6))) + 0.07
              for t in np.linspace(0, 1, n)]
    return flat_chain(P, pts, widths, normal, k, 0.5, legacy=True)


CROWN = (165, 76)
TOUSLED = dict(thick=1.2, clumps=[   # (root (phi, el), tip (phi, el), half width, lift)
    # bangs: parted a little left of centre; big locks sweep out to each side and flick up at the tips
    ((-4, 84), (-30, 20), 4.8, 2.0), ((-24, 78), (-50, 24), 3.9, 2.4), ((-40, 70), (-60, 28), 3.2, 1.8),
    ((12, 84), (26, 21), 4.4, 2.0), ((30, 76), (50, 26), 3.6, 2.4),
    # temples and sideburns, in front of the ears
    ((-62, 60), (-66, 2), 3.0, 0.8), ((62, 60), (66, 2), 3.0, 0.8),
    # over and behind the ears, flicking out
    ((-100, 64), (-104, 8), 3.6, 2.2), ((100, 64), (104, 8), 3.6, 2.2),
    # back: locks from the crown down to the nape, flaring out
    ((-135, 70), (-132, -20), 4.3, 2.8), ((135, 70), (132, -20), 4.3, 2.8),
    ((-160, 68), (-158, -30), 4.4, 3.0), ((160, 68), (158, -30), 4.4, 3.0),
    # top: volume over the crown, and two swept-back spikes
    ((60, 84), (95, 60), 4.4, 1.6), ((-60, 84), (-95, 60), 4.4, 1.6), ((120, 80), (130, 40), 4.6, 2.6),
    ((-120, 80), (-130, 40), 4.6, 2.6),
    ((130, 84), (165, 44), 3.8, 6.5), ((-170, 84), (-178, 48), 3.6, 5.8),
])

SPIKY = dict(thick=0.7, clumps=[   # short bangs and big upswept spikes
    ((-30, 70), (-34, 28), 3.6, 1.2), ((-8, 74), (-10, 26), 3.9, 1.2), ((14, 74), (17, 27), 3.8, 1.2),
    ((34, 68), (42, 30), 3.4, 1.4),
    ((-62, 58), (-66, 6), 2.8, 0.8), ((62, 58), (66, 6), 2.8, 0.8),
    ((-95, 66), (-115, 30), 3.8, 5.0), ((95, 66), (115, 30), 3.8, 5.0),
    ((-130, 68), (-150, 14), 4.0, 5.5), ((130, 68), (150, 14), 4.0, 5.5), ((180, 64), (180, -10), 4.2, 4.6),
    ((150, 86), (176, 46), 3.9, 8.5), ((-150, 86), (-172, 44), 3.7, 8.0), ((40, 86), (70, 62), 3.3, 7.0),
    ((-40, 86), (-70, 62), 3.3, 7.0), ((0, 88), (20, 72), 3.3, 6.5),
])


def hair_sdf_of(style):
    def f(P):
        locks = None
        for root, tip, w, lift in style["clumps"]:
            c = clump(P, root, tip, w, lift)
            locks = c if locks is None else smin(locks, c, 0.35)
        return smin(locks, hair_cap(P, style["thick"]), 0.6)
    return f


hair_tousled_sdf = hair_sdf_of(TOUSLED)
hair_spiky_sdf = hair_sdf_of(SPIKY)
HAIR_BOX = ((-23, 23), (-24, 28), (HEAD_C[2] - 21, HEAD_C[2] + 30))


# ---------------------------------------------------------------------------
# Skeleton
# ---------------------------------------------------------------------------
def skeleton():
    """[(name, head, tail, z_axis_hint, parent, deform)] in parent-first order. Core names and layout follow the
    Unreal Engine 5 Mannequin, so Unreal's retargeter maps animations onto Kai."""
    B = []
    add = lambda n, h, t, z, p, d=True: B.append((n, np.asarray(h, float), np.asarray(t, float), np.asarray(z, float), p, d))
    add("root", (0, 0, 0), (0, -12, 0), UP, None)
    add("pelvis", (0, 0.4, Z["pelvis"]), (0, 0.4, Z["pelvis"] + 3.4), FWD, "root")
    zs = np.linspace(Z["pelvis"] + 3.4, Z["neck"] + 0.4, 6)
    spine = [(0, 0.45, z) for z in zs]
    parent = "pelvis"
    for i in range(5):
        add(f"spine_0{i + 1}", spine[i], spine[i + 1], FWD, parent); parent = f"spine_0{i + 1}"
    nk = Z["neck"] + 0.4
    add("neck_01", (0, 0.5, nk), (0, 0.6, nk + 3.0), FWD, "spine_05")
    add("neck_02", (0, 0.6, nk + 3.0), (0, 0.5, nk + 6.0), FWD, "neck_01")
    add("head", (0, 0.5, nk + 6.0), (0, 0.5, HEAD_C[2] + 13.0), FWD, "neck_02")
    for side, s in SIDES:
        S, E, W, d2 = arm_points(s)
        add(bn("clavicle", side), (1.8 * s, -0.4, Z["shoulder"] - 0.8), S, UP, "spine_05")
        add(bn("upperarm", side), S, E, nrm(np.cross(E - S, [0, 1, 0]) * s), bn("clavicle", side))
        add(bn("lowerarm", side), E, W, nrm(np.cross(W - E, [0, 1, 0]) * s), bn("upperarm", side))
        Wp, f, n, t = hand_frame(s)
        add(bn("hand", side), W, W + f * 5.0 * HAND_K, n, bn("lowerarm", side))
        for fn in ("thumb", "index", "middle", "ring", "pinky"):
            pts, r = finger_points(s, fn)
            parent = bn("hand", side)
            for j in range(3):
                d = nrm(pts[j + 1] - pts[j])
                add(bn(f"{fn}_0{j + 1}", side), pts[j], pts[j + 1], nrm(n - d * (n @ d)), parent)
                parent = bn(f"{fn}_0{j + 1}", side)
        H, K, A, Bl, T = leg_points(s)
        add(bn("thigh", side), H, K, FWD, "pelvis")
        add(bn("calf", side), K, A, FWD, bn("thigh", side))
        add(bn("foot", side), A, Bl, UP, bn("calf", side))
        add(bn("ball", side), Bl, T, UP, bn("foot", side))
    F = face_layout()
    for side, s in SIDES:
        e = F["eyes"][side]
        P, n, u, v = e["pivot"], e["n"], e["u"], e["v"]
        add(bn("eye", side), P, P + n * 3.0, v, "head")
        add(bn("eyelid_upper", side), P, P + n * 2.5, v, "head")
        add(bn("eyelid_lower", side), P, P + n * 2.0, v, "head")
        b = F["brows"][side]
        add(bn("brow", side), b["center"], b["center"] + b["n"] * 1.5, UP, "head")
    C = HEAD_C
    add("hair_front", C + [0, -12.0, 9.0], C + [0, -16.5, 2.0], FWD, "head")
    add("hair_top", C + [0, 4.0, 16.0], C + [0, 9.0, 21.0], FWD, "head")
    add("hair_back_01", C + [0, 13.0, 4.0], C + [0, 16.0, -5.0], FWD, "head")
    add("hair_back_02", C + [0, 16.0, -5.0], C + [0, 16.5, -11.0], FWD, "hair_back_01")
    for side, s in SIDES:
        add(bn("hair_side", side), C + [14.5 * s, -6.0, 3.0], C + [15.0 * s, -7.0, -6.5], FWD, "head")
    for tail, (pts, w) in zip("ab", sash_tail_points()):
        parent = "pelvis"
        for j in range(3):
            add(f"sash_{tail}_0{j + 1}", pts[j], pts[j + 1], FWD, parent); parent = f"sash_{tail}_0{j + 1}"
    zs = Z["shoulder"]
    add("collar_back", (0, 7.0, zs + 0.5), (0, 8.8, zs - 7.5), [0, 1, 0], "spine_05")
    add("neckerchief", (0, -7.9, Z["chest"] + 0.9), (0, -8.4, Z["chest"] - 3.6), FWD, "spine_05")
    # Unreal Mannequin-style IK goals (no skin; animated to follow the hands and feet)
    add("ik_foot_root", (0, 0, 0), (0, 0, 8), FWD, "root", False)
    for side, s in SIDES:
        A = leg_points(s)[2]
        add(bn("ik_foot", side), A, A + np.array([0, -6.0, 0]), UP, "ik_foot_root", False)
    add("ik_hand_root", (0, 0, 0), (0, 0, 8), FWD, "root", False)
    Wr = arm_points(-1)[2]
    add("ik_hand_gun", Wr, Wr + np.array([0, -6.0, 0]), UP, "ik_hand_root", False)
    for side, s in SIDES:
        W = arm_points(s)[2]
        add(bn("ik_hand", side), W, W + np.array([0, -6.0, 0]), UP, "ik_hand_gun", False)
    return B


# ---------------------------------------------------------------------------
# Marching cubes
# ---------------------------------------------------------------------------
def polygonize(sdf, box, h, chunk=24):
    """Mesh of sdf = 0 inside box ((x0, x1), (y0, y1), (z0, z1)) on a grid of spacing h."""
    from skimage.measure import marching_cubes
    xs = np.arange(box[0][0], box[0][1] + h, h); ys = np.arange(box[1][0], box[1][1] + h, h)
    zs = np.arange(box[2][0], box[2][1] + h, h)
    vol = np.empty((len(xs), len(ys), len(zs)), np.float32)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    for k0 in range(0, len(zs), chunk):
        zz = zs[k0:k0 + chunk]
        P = np.column_stack([np.repeat(X.ravel(), len(zz)), np.repeat(Y.ravel(), len(zz)), np.tile(zz, X.size)])
        vol[:, :, k0:k0 + len(zz)] = sdf(P).reshape(len(xs), len(ys), len(zz))
    vol[0], vol[-1], vol[:, 0], vol[:, -1], vol[:, :, 0], vol[:, :, -1] = 1, 1, 1, 1, 1, 1   # close the mesh
    verts, faces, _, _ = marching_cubes(vol, 0.0, spacing=(h, h, h))
    verts += np.array([xs[0], ys[0], zs[0]])
    return verts, faces                                                # outward winding (skimage order)


PARTS = {   # slot: (sdf, box)
    "head": (head_sdf, HEAD_BOX), "hair_tousled": (hair_tousled_sdf, HAIR_BOX), "hair_spiky": (hair_spiky_sdf, HAIR_BOX),
    "arms": (arms_sdf, None), "tunic": (tunic_part_sdf, TUNIC_BOX), "pants": (pants_sdf, PANTS_BOX),
    "legs": (legs_sdf, LEGS_BOX), "sandals": (sandal_sdf, SANDAL_BOX),
    "sash": (sash_sdf, SASH_BOX), "neckerchief": (neckerchief_sdf, KERCHIEF_BOX),
}


def part_box(name):
    fn, box = PARTS[name]
    return _arms_box() if box is None else box
