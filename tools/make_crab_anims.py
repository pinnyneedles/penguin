#!/usr/bin/env python3
"""Author the crab's animation set for Unreal Engine, export one FBX per clip and write the data a procedural
animation setup needs.

    python3 tools/make_crab_anims.py --blend crab/Crab.blend --out crab [--no-render] [--pose-test]
        [--size 360] [--samples 12] [--classic Crab_Idle,...]

Clips (30 fps, in place; looping clips repeat frame 1 as their last frame):
    Crab_Idle             91 f  loop   breathing, eye stalks glance around, antenna flicks, mouthparts, claw snips
    Crab_Scuttle_Left     15 f  loop   sideways run toward the crab's left; planted feet match 50 cm/s
    Crab_Scuttle_Right    15 f  loop   the same toward its right
    Crab_Walk_Forward     25 f  loop   slow forward walk; planted feet match 22 cm/s
    Crab_Walk_Backward    25 f  loop   backing away, claws up; planted feet match 18 cm/s
    Crab_Turn_Left        21 f  loop   turn in place, counter-clockwise seen from above, 60 degrees per second
    Crab_Turn_Right       21 f  loop   the same, clockwise
    Crab_Threat           55 f         rears up, claws raised wide and open, snaps (frames 22, 34)
    Crab_Attack_Snap      33 f         wind-up, lunge and double pinch (hit on frame 13)
    Crab_Claw_Snap        31 f         claws only, for a layered blend on top of any clip: snaps on frames 9 and 23
    Crab_Hit              21 f         flinch: knocked back, eyes fold down, claws tucked
    Crab_Death            60 f         flinch, curl, flip onto its back (lands on frame 25), legs twitch

Every clip also animates the helper bones: ik_legN_l/r follow the foot contact points and ik_claw_l/r the claw
tips, as Unreal's ik_foot bones do, so foot locking and ground adaptation can read them.

Legs use an exact two-bone IK with the tip leaning outward, so planted feet stay put. The gait is an alternating
tetrapod with a small back-to-front ripple. In the idle, locomotion and attack clips the eye stalks, antennae and
claws carry secondary motion: each is a damped spring driven by its own acceleration. Every piece of the crab is
rigid and belongs to one bone, so ground contact is computed exactly from the bone transforms. The armature object
is named "Armature" so Unreal does not add an extra root bone.

Also written: procedural_rig.json (chains, IK goals, poles, gait timing, spring settings for a Control Rig or
AnimGraph setup), Rig_Diagram.png, and Crab_Procedural_Terrain.gif, which drives the rig the procedural way:
a gait clock, feet planted on uneven ground, and the body fitted to the feet.
"""
import argparse, json, math, os, sys
import bpy
import numpy as np
from mathutils import Vector, Matrix, Euler
from scipy.interpolate import PchipInterpolator

FPS = 30
TAU = 2 * math.pi
SIDES = (("L", 1), ("R", -1))
LEGS = [(side, i) for side, s in SIDES for i in range(1, 5)]
GROUP_A = {("L", 1), ("R", 2), ("L", 3), ("R", 4)}           # alternating tetrapod gait
SCUTTLE_SPEED, WALK_SPEED, BACK_SPEED, TURN_RATE = 50.0, 22.0, 18.0, 60.0
METACHRONAL = 0.035      # each leg's phase lead over the leg in front of it: the back legs step first
LAG = 0.10               # the body dips this fraction of a cycle after a set of feet lands
REACH_OUT = 1.2          # cm: a swinging foot arcs outward by this much
LEAD_LIFT = 0.2          # sideways runs: the leading legs step 20% higher, the trailing legs 20% lower
PLANT_Z = 0.5            # cm: a foot whose IK goal is lower than this is planted
G_CM = 981.0
# secondary motion: (radians of lean per g of acceleration, natural frequency Hz, damping ratio, limit radians)
JIGGLE = {"eye": (0.10, 5.0, 0.30, 0.22), "antenna": (0.32, 3.2, 0.18, 0.45), "claw_arm": (0.04, 3.0, 0.45, 0.10)}
# Clips kept at the previous version's motion: in blind side-by-side reviews (three reviewers, sides randomised) the
# refined versions of these did not win clearly enough. Idle, the scuttles, the forward walk and the attack did.
CLASSIC = {"Crab_Threat", "Crab_Hit", "Crab_Death"}


def bn(name, side):
    return f"{name}_{side.lower()}"


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", default="crab/Crab.blend")
    ap.add_argument("--out", default="crab")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--pose-test", action="store_true")
    ap.add_argument("--size", type=int, default=360)
    ap.add_argument("--samples", type=int, default=12)
    ap.add_argument("--classic", default="", help="comma-separated clips to author with the previous motion")
    ap.add_argument("--demo-only", action="store_true", help="only render Crab_Procedural_Terrain.gif")
    return ap.parse_args(argv)


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def smootherstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (x * (6 * x - 15) + 10)


def pulse(f, f0, dur):
    """0 -> 1 -> 0 over dur frames from f0, smooth at both ends."""
    u = (f - f0) / dur
    return math.sin(math.pi * u) ** 2 if 0 < u < 1 else 0.0


def window(t, a, b, r):
    """1 between a and b (fractions of the clip), easing in and out over r."""
    return smoothstep((t - a) / r) * smoothstep((b - t) / r)


def keyed(keys, f):
    """Monotone cubic through (frame, value) keys, held flat outside."""
    fr = [k[0] for k in keys]; vals = np.array([k[1] for k in keys], float)
    if f <= fr[0]: return vals[0]
    if f >= fr[-1]: return vals[-1]
    return PchipInterpolator(fr, vals, axis=0)(f)


def euler_q(x=0.0, y=0.0, z=0.0):
    return Euler((x, y, z), "XYZ").to_quaternion()


# ---------------------------------------------------------------------------
# Rig: rest data, pose solve, rigid ground contact
# ---------------------------------------------------------------------------
class Rig:
    def __init__(self, rig, mesh):
        self.rig, self.mesh = rig, mesh
        bones = rig.data.bones
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.bones = []                                       # parents before children
        def visit(n):
            if n in self.bones: return
            if self.parent[n]: visit(self.parent[n])
            self.bones.append(n)
        for b in bones: visit(b.name)
        self.rest = {b.name: b.matrix_local.copy() for b in bones}
        self.rest_inv = {k: m.inverted() for k, m in self.rest.items()}
        self.rel = {n: (self.rest_inv[p] @ self.rest[n]) if p else self.rest[n] for n, p in self.parent.items()}
        self.rel_inv = {k: m.inverted() for k, m in self.rel.items()}
        self.length = {b.name: b.length for b in bones}
        for p in rig.pose.bones: p.rotation_mode = "QUATERNION"
        self.C = self.rest["body"].translation.copy()
        # IK goal bones copy the bone they shadow on every frame (their children follow them)
        self.goals = {bn(f"ik_leg{i}", side): bn(f"leg{i}_end", side) for side, i in LEGS}
        self.goals.update({bn("ik_claw", side): bn("claw_tip", side) for side, s in SIDES})
        self.after_goal = set()
        for b in self.bones:
            if b in self.goals or self.parent[b] in self.after_goal: self.after_goal.add(b)
        self.T_rest, self.sign, self.knee, self.tilt, self.L = {}, {}, {}, {}, {}
        for side, i in LEGS:
            k = (side, i)
            up, lo, tp = (bn(f"leg{i}_{seg}", side) for seg in ("upper", "lower", "tip"))
            self.knee[k] = math.radians(bones[up].get("knee_tilt_deg", 0.0))
            H, K, D = (self.rest[b].translation.copy() for b in (up, lo, tp))
            T = self.rest[bn(f"leg{i}_end", side)].translation.copy()
            self.T_rest[k] = T
            self.L[k] = (self.length[up], self.length[lo], self.length[tp])
            u = (D - H).normalized(); w = ((K - H) - u * (K - H).dot(u)).normalized()
            self.sign[k] = 1.0 if u.cross(w).dot(self.rest[up].to_3x3().col[0]) > 0 else -1.0
            self.tilt[k] = math.atan2((T - D).cross(Vector((0, 0, -1))).length, (T - D).dot(Vector((0, 0, -1))))
        # rigid skinning: vertices by bone, for exact ground contact
        gi = {g.index: g.name for g in mesh.vertex_groups}
        co = np.array([v.co[:] for v in mesh.data.vertices])
        bone_of = np.array([gi[v.groups[0].group] for v in mesh.data.vertices])
        self.vgroups = {b: co[bone_of == b] for b in set(bone_of)}
        self.shell_top = self.vgroups["body"][:, 2].max()

    def solve(self, prm):
        """prm -> {bone: posed matrix in armature space} for every bone, helpers included."""
        P = {}
        P["root"] = prm.get("root", Matrix.Identity(4)) @ self.rest["root"]
        bd = prm["body"]
        A = (Matrix.Translation(self.C + Vector(bd["loc"])) @ Euler(bd["rot"], "XYZ").to_matrix().to_4x4()
             @ Matrix.Translation(-self.C))
        P["body"] = P["root"] @ self.rest_inv["root"] @ A @ self.rest["body"]
        Rb = (P["body"] @ self.rest_inv["body"]).to_3x3()
        up_b = (Rb @ Vector((0, 0, 1))).normalized()
        jig = prm.get("jiggle", {})

        def fk(b, x=0.0, y=0.0, z=0.0):
            q = euler_q(x, y, z)
            j = jig.get(b)
            if j is not None: q = q @ euler_q(j[0], 0.0, j[1])
            P[b] = P[self.parent[b]] @ self.rel[b] @ q.to_matrix().to_4x4()

        for side, s in SIDES:
            e = prm.get("eyes", {}).get(side, (0, 0, 0))
            fk(bn("eye", side), e[0], e[1], e[2] * s * SIGN["eye"])
            a = prm.get("antennae", {}).get(side, (0, 0))
            fk(bn("antenna", side), a[0], 0, a[1] * s * SIGN["antenna"])
            m = prm.get("mouth", {}).get(side, (0, 0))
            fk(bn("mouthpart", side), m[0], 0, m[1] * s * SIGN["mouthpart"])
            c = prm.get("claws", {}).get(side, {})
            for part in ("arm", "wrist", "hand"):
                v = c.get(part, (0, 0, 0)); fk(bn(f"claw_{part}", side), v[0], v[1], v[2] * s)
            fk(bn("claw_pincer", side), -c.get("open", 0.0))
            for i in range(1, 5):
                self.solve_leg(P, prm, side, i, Rb, up_b)
        for b in self.bones:
            if b not in P and b not in self.after_goal: P[b] = P[self.parent[b]] @ self.rel[b]
        for g, src in self.goals.items(): P[g] = P[src].copy()
        for b in self.bones:
            if b not in P: P[b] = P[self.parent[b]] @ self.rel[b]
        return P

    def solve_leg(self, P, prm, side, i, Rb, up_b):
        k = (side, i)
        names = [bn(f"leg{i}_{seg}", side) for seg in ("upper", "lower", "tip")]
        lg = prm["legs"].get(k) or {"mode": "ik", "T": self.T_rest[k]}
        if lg["mode"] == "fk":
            for b, q in zip(names, lg["q"]):
                P[b] = P[self.parent[b]] @ self.rel[b] @ q.to_matrix().to_4x4()
            return
        H = (P[self.parent[names[0]]] @ self.rel[names[0]]).translation
        T = Vector(lg["T"])
        L1, L2, L3 = self.L[k]
        v = T - H
        out = (v - up_b * v.dot(up_b)).normalized()
        def tip_base(tilt):
            return T - (-up_b * math.cos(tilt) + out * math.sin(tilt)).normalized() * L3
        Dp = tip_base(self.tilt[k])
        reach = L1 + L2 - 2e-3
        if (Dp - H).length > reach:            # stretched: the tip pivots on its point, leaning out to bring its
            lo, hi = self.tilt[k], self.tilt[k] + math.radians(40)        # base closer, so the foot stays planted
            if (tip_base(hi) - H).length > reach: lo = hi
            for _ in range(30 if lo < hi else 0):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if (tip_base(mid) - H).length > reach else (lo, mid)
            Dp = tip_base(hi)
        vv = Dp - H; dist = vv.length
        dist_c = min(max(dist, abs(L1 - L2) + 1e-3), L1 + L2 - 1e-3)
        u = vv / dist
        a = math.acos(min(max((L1 * L1 + dist_c * dist_c - L2 * L2) / (2 * L1 * dist_c), -1), 1))
        fb = Rb @ Vector((0, -1, 0))                            # knee bends up, tilted toward the front or back
        fp = fb - out * fb.dot(out) - up_b * fb.dot(up_b)
        fp = fp.normalized() if fp.length > 1e-6 else Vector((0, 0, 0))
        g = self.knee[k]
        pole = up_b * math.cos(g) + fp * math.sin(g)
        w = (pole - u * u.dot(pole)).normalized()
        K = H + L1 * (math.cos(a) * u + math.sin(a) * w)
        Dp = K + (Dp - K).normalized() * L2                    # exact segment lengths when out of reach
        Tp = Dp + (T - Dp).normalized() * L3
        n = u.cross(w).normalized() * self.sign[k]
        for b, h, t in zip(names, (H, K, Dp), (K, Dp, Tp)):
            y = (t - h).normalized(); x = (n - y * n.dot(y)).normalized(); z = x.cross(y)
            M = Matrix((x, y, z)).transposed().to_4x4(); M.translation = h
            P[b] = M

    def basis(self, P):
        out = {}
        for b in self.bones:
            p = self.parent[b]
            out[b] = (self.rest_inv[b] @ P[b]) if p is None else (self.rel_inv[b] @ P[p].inverted() @ P[b])
        return out

    def min_z(self, P, skip_tips=False):
        z = np.inf
        for b, V in self.vgroups.items():
            if skip_tips and "_tip_" in b: continue
            M = np.array(P[b] @ self.rest_inv[b])
            z = min(z, float((V @ M[:3, :3].T + M[:3, 3])[:, 2].min()))
        return z

    def feet(self, P):
        return {k: P[bn(f"leg{k[1]}_end", k[0])].translation.copy() for k in LEGS}


SIGN = {"eye": 1.0, "antenna": 1.0, "mouthpart": 1.0}   # set in load(): a positive yaw swings the bone outward
CURL_SIGN = 1.0


# ---------------------------------------------------------------------------
# Secondary motion
# ---------------------------------------------------------------------------
def spring(drive, hz, zeta, loop, sub=8):
    """Damped spring x'' = w^2 (drive - x) - 2 zeta w x', drive given per frame. Loops: three warm-up cycles, then
    the residual seam error is spread over the cycle so the last frame equals the first. One-shots start at rest
    and settle back to rest over the last eight frames."""
    w = TAU * hz; dt = 1.0 / (FPS * sub)
    n = len(drive); x = np.zeros(drive.shape[1]); v = np.zeros_like(x)
    cycles = 4 if loop else 1
    rec = []
    for c in range(cycles):
        for f in range(n):
            if c == cycles - 1: rec.append(x.copy())
            d0 = drive[f]; d1 = drive[(f + 1) % n] if loop else drive[min(f + 1, n - 1)]
            for k in range(sub):
                d = d0 + (d1 - d0) * (k / sub)
                v += (w * w * (d - x) - 2 * zeta * w * v) * dt
                x += v * dt
    if loop:
        rec.append(x.copy()); rec = np.array(rec)
        rec -= np.outer(np.arange(n + 1) / n, rec[-1] - rec[0])
    else:
        rec = np.array(rec)
        rec *= np.array([smoothstep((n - 1 - f) / 8.0) for f in range(n)])[:, None]
    return rec


def add_jiggle(R, params, loop, amount=1.0):
    """Each jiggle bone leans against the acceleration of its own midpoint, measured in the frame its parent carries
    it in (so body sway, bob and rotation all count, and so does gravity when the body tilts)."""
    n = len(params) - (1 if loop else 0)                       # loops repeat frame 1 as their last frame
    Ps = [R.solve(p) for p in params[:n]]
    g = np.array([0.0, 0.0, G_CM])
    for kind, (gain, hz, zeta, lim) in JIGGLE.items():
        for side, s in SIDES:
            b = bn(kind, side); par = R.parent[b]
            F = [P[par] @ R.rel[b] for P in Ps]
            mids = np.array([tuple(M @ Vector((0, R.length[b] * 0.5, 0))) for M in F])
            rots = np.array([np.array(M.to_3x3()) for M in F])
            if loop:
                acc = (np.roll(mids, -1, 0) - 2 * mids + np.roll(mids, 1, 0)) * FPS ** 2
            else:
                pad = np.concatenate([mids[:1], mids, mids[-1:]])
                acc = (pad[2:] - 2 * pad[1:-1] + pad[:-2]) * FPS ** 2
            R0 = np.array(R.rest[b].to_3x3())
            loc = np.einsum("fji,fj->fi", rots, acc + g) - R0.T @ g
            drive = np.stack([-loc[:, 2], loc[:, 0]], 1) * (gain * amount / G_CM)
            x = spring(drive, hz, zeta, loop)
            x = lim * np.tanh(x / lim)
            for f, prm in enumerate(params):
                prm.setdefault("jiggle", {})[b] = (float(x[f, 0]), float(x[f, 1]))
    return params


# ---------------------------------------------------------------------------
# Clip parameters
# ---------------------------------------------------------------------------
def base(R):
    return {"body": {"loc": (0, 0, 0), "rot": (0, 0, 0)}, "claws": {}, "eyes": {}, "antennae": {}, "mouth": {},
            "legs": {k: {"mode": "ik", "T": R.T_rest[k].copy()} for k in LEGS}}


def leg_phase(k, f, P, ref):
    c = (f - 1) / P + (0.0 if k in GROUP_A else 0.5)
    if ref: c += METACHRONAL * (k[1] - 1)
    return c % 1.0


def gait(R, f, P, duty, stride, lift, move, ref, turn=0):
    """Foot goals for frame f of a P-frame cycle. Straight gaits slide the planted feet along -move by stride over
    the stance; turn=+1/-1 instead sweeps them about the root by stride radians (counter-clockwise = +1)."""
    legs = {}
    for side, s in SIDES:
        for i in range(1, 5):
            k = (side, i)
            c = leg_phase(k, f, P, ref)
            u = None
            if c < duty:
                frac, z = 0.5 - c / duty, 0.0
            else:
                u = (c - duty) / (1 - duty)
                if ref:
                    frac = -0.5 + smootherstep(u)
                    wv = u + 0.5 * u * (1 - u)                   # quick lift-off, gentle touch-down
                    z = lift * (1 + LEAD_LIFT * s * move[0]) * math.sin(math.pi * wv)
                else:
                    frac, z = -0.5 + smoothstep(u), lift * math.sin(math.pi * u) ** 0.85
            T0 = R.T_rest[k]
            T = (Matrix.Rotation(turn * stride * frac, 4, "Z") @ T0) if turn else (T0 + Vector(move) * stride * frac)
            if ref and u is not None:
                T = T + Vector((T0.x - R.C.x, T0.y - R.C.y, 0)).normalized() * (REACH_OUT * math.sin(math.pi * u))
            legs[k] = {"mode": "ik", "T": T + Vector((0, 0, z))}
    return legs


def look(yaw_left, pitch=0.0):
    """Both eye stalks lean toward the crab's left by yaw_left (negative: right)."""
    return {sd: (pitch, 0, yaw_left * s) for sd, s in SIDES}


def mouth_flutter(t, cycles, amp, env=1.0):
    """Mouthparts part and swing forward in a quick rhythm (a whole number of cycles per clip keeps loops seamless)."""
    v = 0.5 - 0.5 * math.cos(TAU * cycles * t)
    return {sd: (0.6 * amp * env * v, amp * env * v) for sd, s in SIDES}


GUARD = {"arm": (-0.18, 0, 0.05), "wrist": (-0.05, 0, 0), "hand": (0.05, 0, 0)}


def idle_params(R, ref, n=91):
    out = []
    for f in range(1, n + 1):
        t = (f - 1) / (n - 1)
        p = base(R)
        p["body"] = {"loc": (0.25 * math.sin(TAU * t), 0, 0.45 * math.sin(2 * TAU * t)),     # zero at both ends: rest pose
                     "rot": (0.015 * math.sin(TAU * t), 0.012 * math.sin(2 * TAU * t), 0.02 * math.sin(TAU * t) * math.cos(TAU * t))}
        snipL = keyed([(1, 0), (26, 0), (29, 0.5), (32, 0.04), (35, 0.45), (38, 0), (91, 0)], f)
        snipR = keyed([(1, 0), (58, 0), (62, 0.55), (66, 0.02), (91, 0)], f)
        sway = 0.05 * math.sin(TAU * t)
        lift = -0.06 * math.sin(math.pi * t) ** 2
        p["claws"] = {"L": {"arm": (lift + sway, 0, 0.03 * math.sin(math.pi * t)), "wrist": (0, 0, 0), "hand": (0.02 * math.sin(TAU * t), 0, 0), "open": snipL},
                      "R": {"arm": (lift - sway, 0, 0.03 * math.sin(math.pi * t)), "wrist": (0, 0, 0), "hand": (-0.02 * math.sin(TAU * t), 0, 0), "open": snipR}}
        if 48 <= f <= 58:                                    # shuffle one back leg
            u = (f - 48) / 10
            p["legs"][("R", 3)]["T"] = R.T_rest[("R", 3)] + Vector((0.8 * math.sin(math.pi * u), -1.2 * math.sin(math.pi * u), 3.5 * math.sin(math.pi * u)))
        if not ref:
            ey = keyed([(1, 0), (16, 0), (21, 0.35), (38, 0.35), (43, -0.25), (62, -0.25), (67, 0), (91, 0)], f)
            ep = keyed([(1, 0), (16, 0), (21, -0.1), (38, -0.1), (43, 0.08), (62, 0.08), (67, 0), (91, 0)], f)
            p["eyes"] = {"L": (ep, 0, ey), "R": (ep, 0, ey + 0.06 * math.sin(TAU * 3 * t))}
        else:
            # the stalks glance left, then right, then back, the right one a couple of frames behind the left
            eyes = {}
            for sd, s in SIDES:
                d = 0 if s > 0 else 2
                yl = keyed([(1, 0), (14, 0), (19, 0.28), (37, 0.28), (42, -0.26), (61, -0.26), (67, 0), (91, 0)], f - d)
                ep = keyed([(1, 0), (14, 0), (19, -0.08), (37, -0.08), (42, 0.06), (61, 0.06), (67, 0), (91, 0)], f - d)
                eyes[sd] = (ep - 0.10 * pulse(f, 78 + d, 6), 0, yl * s)          # a quick blink-like dip near the end
            p["eyes"] = eyes
            p["antennae"] = {sd: (0.05 * math.sin(TAU * t + (0 if s > 0 else 1.3)) * math.sin(math.pi * t)
                                  - 0.45 * sum(pulse(f, f0, 6) for f0 in ((9, 33, 70) if s > 0 else (13, 52, 74))), 0.0)
                             for sd, s in SIDES}
            env = window(t, 0.04, 0.36, 0.05) + window(t, 0.55, 0.88, 0.05)
            p["mouth"] = mouth_flutter(t, 12, 0.14, env)
            if 21 <= f <= 30:                                # a smaller shift of a front leg while the eyes look left
                u = (f - 21) / 9
                p["legs"][("L", 1)]["T"] = R.T_rest[("L", 1)] + Vector((0.6, -0.8, 2.2)) * math.sin(math.pi * u)
        out.append(p)
    return add_jiggle(R, out, True, 0.8) if ref else out


def scuttle_params(R, direction, ref, P=14):
    duty = 0.6
    stride = SCUTTLE_SPEED * duty * P / FPS
    out = []
    for f in range(1, P + 2):
        t = (f - 1) / P
        p = base(R)
        p["legs"] = gait(R, f, P, duty, stride, 5.5, (direction, 0, 0), ref)
        if not ref:
            p["body"] = {"loc": (0.6 * direction * math.sin(2 * TAU * t), 0, -0.5 + 0.55 * math.cos(2 * TAU * t)),
                         "rot": (0.0, 0.035 * direction + 0.012 * math.sin(2 * TAU * t), 0.0)}
            b = 0.06 * math.cos(2 * TAU * t)
            p["claws"] = {sd: {"arm": (GUARD["arm"][0] + b, 0, GUARD["arm"][2]), "wrist": GUARD["wrist"], "hand": GUARD["hand"], "open": 0.0}
                          for sd, s in SIDES}
            p["eyes"] = {sd: (0.05 * math.sin(2 * TAU * t), 0, 0.15 * direction) for sd, s in SIDES}
        else:
            ph = 2 * TAU * (t - LAG)
            p["body"] = {"loc": (0.5 * direction * math.sin(ph), 0.25 * math.sin(TAU * t), -0.55 - 0.45 * math.cos(ph)),
                         "rot": (0.012 * math.sin(TAU * t + 0.7), 0.04 * direction + 0.014 * math.sin(ph), 0.02 * math.sin(TAU * t))}
            p["claws"] = {sd: {"arm": (GUARD["arm"][0] - 0.04 + 0.03 * math.cos(ph), 0, GUARD["arm"][2]), "wrist": GUARD["wrist"],
                               "hand": GUARD["hand"], "open": 0.0} for sd, s in SIDES}
            p["eyes"] = look(0.16 * direction, -0.05)
            p["antennae"] = {sd: (-0.25, 0.12) for sd, s in SIDES}
            p["mouth"] = mouth_flutter(t, 1, 0.05)
        out.append(p)
    return add_jiggle(R, out, True) if ref else out


def walk_params(R, ref, P=24):
    duty = 0.65
    stride = WALK_SPEED * duty * P / FPS
    out = []
    for f in range(1, P + 2):
        t = (f - 1) / P
        p = base(R)
        p["legs"] = gait(R, f, P, duty, stride, 4.0, (0, -1, 0), ref)
        if not ref:
            p["body"] = {"loc": (0.4 * math.sin(2 * TAU * t), 0, -0.3 + 0.35 * math.cos(2 * TAU * t)),
                         "rot": (0.02 * math.sin(2 * TAU * t), 0.015 * math.sin(TAU * t), 0.02 * math.sin(TAU * t))}
            p["claws"] = {sd: {"arm": (GUARD["arm"][0] + 0.04 * math.sin(TAU * t + (0 if s > 0 else math.pi)), 0, GUARD["arm"][2]),
                               "wrist": GUARD["wrist"], "hand": GUARD["hand"], "open": 0.0} for sd, s in SIDES}
            p["eyes"] = {sd: (0.04 * math.sin(TAU * t), 0, 0.08 * math.sin(TAU * t + s)) for sd, s in SIDES}
        else:
            ph = 2 * TAU * (t - LAG)
            p["body"] = {"loc": (0.35 * math.sin(TAU * (t - LAG)), 0.3 * math.sin(ph), -0.35 - 0.3 * math.cos(ph)),
                         "rot": (0.012 * math.sin(ph), 0.018 * math.sin(TAU * (t - LAG)), 0.025 * math.sin(TAU * t + 0.5))}
            p["claws"] = {sd: {"arm": (GUARD["arm"][0] + 0.04 * math.sin(TAU * t + (0 if s > 0 else math.pi)), 0, GUARD["arm"][2]),
                               "wrist": GUARD["wrist"], "hand": GUARD["hand"], "open": 0.0} for sd, s in SIDES}
            p["eyes"] = look(0.10 * math.sin(TAU * t), -0.03)
            p["antennae"] = {sd: (0.08 * math.sin(TAU * t + (0 if s > 0 else math.pi)), 0.05) for sd, s in SIDES}
            p["mouth"] = mouth_flutter(t, 2, 0.06)
        out.append(p)
    return add_jiggle(R, out, True) if ref else out


def walk_back_params(R, P=24):
    duty = 0.68
    stride = BACK_SPEED * duty * P / FPS
    out = []
    for f in range(1, P + 2):
        t = (f - 1) / P
        p = base(R)
        p["legs"] = gait(R, f, P, duty, stride, 3.5, (0, 1, 0), True)
        ph = 2 * TAU * (t - LAG)
        p["body"] = {"loc": (0.3 * math.sin(TAU * (t - LAG)), 1.2 + 0.25 * math.sin(ph), 0.6 - 0.3 * math.cos(ph)),
                     "rot": (-0.05 + 0.01 * math.sin(ph), 0.015 * math.sin(TAU * (t - LAG)), 0.02 * math.sin(TAU * t + 0.5))}
        p["claws"] = {sd: {"arm": (-0.38 + 0.03 * math.sin(TAU * t + (0 if s > 0 else math.pi)), 0, -0.12), "wrist": (-0.1, 0, -0.05),
                           "hand": (0.08, 0, 0), "open": 0.12 + 0.08 * math.sin(TAU * t) ** 2} for sd, s in SIDES}
        p["eyes"] = look(0.06 * math.sin(TAU * t), -0.10)
        p["antennae"] = {sd: (0.15, 0.10) for sd, s in SIDES}
        p["mouth"] = mouth_flutter(t, 2, 0.08)
        out.append(p)
    return add_jiggle(R, out, True)


def turn_params(R, turn, P=20):
    duty = 0.6
    sweep = math.radians(TURN_RATE) * duty * P / FPS
    out = []
    for f in range(1, P + 2):
        t = (f - 1) / P
        p = base(R)
        p["legs"] = gait(R, f, P, duty, sweep, 4.5, (0, 0, 0), True, turn=turn)
        ph = 2 * TAU * (t - LAG)
        p["body"] = {"loc": (0.2 * math.sin(TAU * (t - LAG)), 0, -0.35 - 0.3 * math.cos(ph)),
                     "rot": (0.01 * math.sin(ph), 0.015 * math.sin(TAU * (t - LAG)), 0.06 * turn + 0.012 * math.sin(ph))}
        p["claws"] = {sd: {"arm": (GUARD["arm"][0] + 0.03 * math.cos(ph), 0, GUARD["arm"][2]), "wrist": GUARD["wrist"],
                           "hand": GUARD["hand"], "open": 0.0} for sd, s in SIDES}
        p["eyes"] = look(0.22 * turn, -0.04)
        p["antennae"] = {sd: (0.05, 0.10 * turn * s) for sd, s in SIDES}
        p["mouth"] = mouth_flutter(t, 1, 0.05)
        out.append(p)
    return add_jiggle(R, out, True)


def claw_keys(f, keys):
    """keys: [(frame, dict(arm=(x,y,z), wrist=..., hand=..., open=a))] -> claw dict at f."""
    res = {}
    for part in ("arm", "wrist", "hand"):
        res[part] = tuple(keyed([(k[0], k[1][part]) for k in keys], f))
    res["open"] = float(keyed([(k[0], k[1]["open"]) for k in keys], f))
    return res


REST_CLAW = dict(arm=(0, 0, 0), wrist=(0, 0, 0), hand=(0, 0, 0), open=0.0)
RAISED = dict(arm=(-0.70, 0, -1.00), wrist=(-0.25, 0, -0.30), hand=(0.15, 0, -0.10), open=0.80)


def step_out(R, k, f, f_out, f_back, dist, lift, dur=6):
    """A planted foot steps outward by dist (negative: inward) at f_out and back at f_back."""
    T0 = R.T_rest[k]
    o = Vector((T0.x - R.C.x, T0.y - R.C.y, 0)).normalized()
    d = smootherstep((f - f_out) / dur) - smootherstep((f - f_back) / dur)
    z = lift * (math.sin(math.pi * (f - f_out) / dur) if f_out < f < f_out + dur else 0.0) \
        + lift * (math.sin(math.pi * (f - f_back) / dur) if f_back < f < f_back + dur else 0.0)
    return {"mode": "ik", "T": T0 + o * dist * d + Vector((0, 0, z))}


def threat_params(R, ref, n=55):
    out = []
    for f in range(1, n + 1):
        p = base(R)
        lift = keyed([(1, 0), (10, 5.0), (44, 5.0), (55, 0)], f)
        pitch = keyed([(1, 0), (10, -0.16), (44, -0.16), (55, 0)], f)
        pump = 0.0 if f < 12 or f > 42 else math.sin(TAU * (f - 12) / 15) * 0.8
        p["body"] = {"loc": (0, keyed([(1, 0), (10, 2.0), (44, 2.0), (55, 0)], f), lift + pump), "rot": (pitch, 0, 0)}
        snap = lambda f0: max(0.0, 1 - abs(f - f0) / 3.0)
        claws = {}
        for sd, s in SIDES:
            c = claw_keys(f, [(1, REST_CLAW), (11, RAISED), (44, RAISED), (55, REST_CLAW)])
            c["arm"] = (c["arm"][0] - 0.12 * pump / 0.8, c["arm"][1], c["arm"][2])
            c["open"] = c["open"] * (1 - snap(22 if s > 0 else 23) - snap(34 if s > 0 else 35))
            claws[sd] = c
        p["claws"] = claws
        p["eyes"] = {sd: (keyed([(1, 0), (10, -0.25), (44, -0.25), (55, 0)], f), 0, 0) for sd, s in SIDES}
        if ref:
            # the front and back legs step in under the body as it rears up (they would be over-stretched
            # otherwise), and back out at the end
            for (sd, i), f0, f1 in ((("L", 1), 2, 45), (("R", 1), 3, 46), (("L", 4), 4, 47), (("R", 4), 5, 48)):
                p["legs"][(sd, i)] = step_out(R, (sd, i), f, f0, f1, -1.5, 2.8)
            raise_ = keyed([(1, 0), (10, 1.0), (44, 1.0), (55, 0)], f)
            p["antennae"] = {sd: (0.35 * raise_, 0.25 * raise_) for sd, s in SIDES}
            fl = 0.0 if f < 12 or f > 44 else 0.5 - 0.5 * math.cos(TAU * (f - 12) / 8)
            p["mouth"] = {sd: (0.10 * raise_ + 0.04 * fl, 0.16 * raise_ + 0.06 * fl) for sd, s in SIDES}
            p["eyes"] = {sd: (keyed([(1, 0), (10, -0.25), (44, -0.25), (55, 0)], f), 0, 0.10 * raise_) for sd, s in SIDES}
        out.append(p)
    return add_jiggle(R, out, False) if ref else out


WIND = dict(arm=(-0.45, 0, -0.75), wrist=(-0.2, 0, -0.15), hand=(0.15, 0, 0), open=0.8)   # wide, beside the eyes
STRIKE = dict(arm=(-0.12, 0, 0.06), wrist=(0.05, 0, -0.05), hand=(-0.05, 0, -0.08), open=0.8)   # forward, claws apart
SNAPPED = dict(STRIKE, open=0.0)


def attack_params(R, ref, n=33):
    out = []
    for f in range(1, n + 1):
        p = base(R)
        y = keyed([(1, 0), (8, 4.0), (12, -9.0), (17, -8.0), (33, 0)], f)
        z = keyed([(1, 0), (8, -1.5), (12, 1.0), (17, 0.6), (33, 0)], f)
        pitch = keyed([(1, 0), (8, -0.08), (12, 0.08), (17, 0.06), (33, 0)], f)
        p["body"] = {"loc": (0, y, z), "rot": (pitch, 0, 0)}
        p["claws"] = {sd: claw_keys(f, [(1, REST_CLAW), (8, WIND), (12, STRIKE), (13, SNAPPED), (17, SNAPPED), (33, REST_CLAW)])
                      for sd, s in SIDES}
        p["eyes"] = {sd: (keyed([(1, 0), (6, -0.7), (15, -0.6), (33, 0)], f), 0, 0) for sd, s in SIDES}   # fold down
        if ref:
            ap = keyed([(1, 0), (7, 0.15), (12, -0.40), (20, -0.32), (33, 0)], f)
            p["antennae"] = {sd: (ap, 0.10 * min(1.0, abs(ap) * 3)) for sd, s in SIDES}
            mo = keyed([(1, 0), (8, 0.05), (12, 0.20), (18, 0.16), (33, 0)], f)
            p["mouth"] = {sd: (0.6 * mo, mo) for sd, s in SIDES}
        out.append(p)
    return add_jiggle(R, out, False) if ref else out


CLAW_READY = dict(arm=(-0.32, 0, -0.30), wrist=(-0.12, 0, -0.10), hand=(0.08, 0, -0.04), open=0.75)


def claw_snap_params(R, n=31):
    """Claws only (everything else stays at rest): the left claw snaps on frame 9, the right on frame 23."""
    out = []
    for f in range(1, n + 1):
        p = base(R)
        p["claws"] = {
            "L": claw_keys(f, [(1, REST_CLAW), (6, CLAW_READY), (7, dict(CLAW_READY, open=0.85)), (9, dict(CLAW_READY, open=0.0)),
                               (12, dict(CLAW_READY, open=0.05)), (20, REST_CLAW), (31, REST_CLAW)]),
            "R": claw_keys(f, [(1, REST_CLAW), (12, REST_CLAW), (20, CLAW_READY), (21, dict(CLAW_READY, open=0.85)),
                               (23, dict(CLAW_READY, open=0.0)), (26, dict(CLAW_READY, open=0.05)), (31, REST_CLAW)])}
        out.append(p)
    return out


TUCK = dict(arm=(0.35, 0, 0.35), wrist=(0.15, 0, 0.1), hand=(0.1, 0, 0), open=0.0)


def hit_params(R, ref, n=21):
    out = []
    for f in range(1, n + 1):
        p = base(R)
        y = keyed([(1, 0), (4, 5.0), (10, 3.0), (21, 0)], f)
        z = keyed([(1, 0), (4, 2.0), (8, -0.8), (14, 0.2), (21, 0)], f)
        pitch = keyed([(1, 0), (4, -0.15), (9, 0.04), (21, 0)], f)
        roll = keyed([(1, 0), (4, 0.08), (10, -0.03), (21, 0)], f)
        p["body"] = {"loc": (0, y, z), "rot": (pitch, roll, 0)}
        p["claws"] = {sd: claw_keys(f, [(1, REST_CLAW), (4, TUCK), (11, TUCK), (21, REST_CLAW)]) for sd, s in SIDES}
        fold = keyed([(1, 0), (4, -0.9), (11, -0.9), (21, 0)], f)
        p["eyes"] = {sd: (fold, 0, 0) for sd, s in SIDES}
        if ref:
            p["antennae"] = {sd: (keyed([(1, 0), (4, -0.55), (11, -0.42), (21, 0)], f), 0.0) for sd, s in SIDES}
            mo = keyed([(1, 0), (3, 0.22), (12, 0.06), (21, 0)], f)
            p["mouth"] = {sd: (0.6 * mo, mo) for sd, s in SIDES}
        out.append(p)
    return add_jiggle(R, out, False) if ref else out


def death_params(R, ref, n=60):
    """Flinch, curl the legs, hop and flip onto the back, land on frame 25, twitch and go still."""
    out = []
    switch = 6
    top = R.shell_top - R.C.z
    for f in range(1, n + 1):
        p = base(R)
        roll = keyed([(1, 0), (switch, 0.08), (12, 0.25), (19, math.pi * 0.62), (25, math.pi), (28, math.pi * 0.985), (32, math.pi)], f)
        x = keyed([(1, 0), (12, 2.0), (25, 14.0), (32, 15.0)], f)
        z = keyed([(1, 0), (switch, 1.5), (10, -3.0), (17, 14.0), (25, top - R.C.z + 0.3), (28, top - R.C.z + 2.0),
                   (32, top - R.C.z + 0.3)], f)
        p["body"] = {"loc": (x, keyed([(1, 0), (switch, 3.0), (25, 2.0)], f), z), "rot": (keyed([(1, 0), (switch, -0.12), (20, 0.05), (32, 0)], f), roll, 0)}
        p["claws"] = {sd: claw_keys(f, [(1, REST_CLAW), (switch, TUCK), (24, dict(arm=(0.2, 0, 0.5), wrist=(0.3, 0, 0.2), hand=(0.2, 0, 0), open=0.0)),
                                        (40, dict(arm=(0.05, 0, 0.2), wrist=(0.1, 0, 0.1), hand=(0.05, 0, 0), open=0.25)),
                                        (60, dict(arm=(0.1, 0, 0.25), wrist=(0.15, 0, 0.1), hand=(0.05, 0, 0), open=0.2))]) for sd, s in SIDES}
        p["eyes"] = {sd: (keyed([(1, 0), (switch, -0.9), (40, -0.7), (60, -0.95)], f), 0, keyed([(1, 0), (40, 0.25 * s), (60, 0.35 * s)], f)) for sd, s in SIDES}
        if ref:
            p["antennae"] = {sd: (keyed([(1, 0), (switch, -0.45), (24, -0.2), (40, 0.25), (60, 0.35)], f), keyed([(1, 0), (40, 0.2), (60, 0.25)], f))
                             for sd, s in SIDES}
            tw = 0.0 if f < 26 else math.exp(-(f - 26) / 9.0) * (0.5 - 0.5 * math.cos(TAU * (f - 26) / 5))
            p["mouth"] = {sd: (0.6 * (0.08 + 0.12 * tw), 0.10 + 0.12 * tw) for sd, s in SIDES}
        out.append(p)
    return out


def apply_death_legs(R, params, switch=6, curl_by=16, n=60):
    """Legs plant until the flinch, then blend (in the body's frame) to a curled pose and twitch."""
    P_sw = R.solve(params[switch - 1]); B_sw = R.basis(P_sw)
    for side, s in SIDES:
        for i in range(1, 5):
            names = [bn(f"leg{i}_{seg}", side) for seg in ("upper", "lower", "tip")]
            qs = [B_sw[b].to_quaternion() for b in names]
            # bend about each segment's hinge so the leg folds in under the body (sign checked in load())
            target = [euler_q(0.40 * CURL_SIGN, 0, 0), euler_q(1.30 * CURL_SIGN, 0, 0), euler_q(0.90 * CURL_SIGN, 0, 0)]
            for f in range(switch + 1, n + 1):
                w = smoothstep((f - switch) / (curl_by - switch))
                tw = 0.0
                if f > 26:
                    k = (f - 26) / 30
                    tw = 0.22 * math.exp(-3.2 * k) * math.sin(TAU * (f - 26) / (5 + i) + 1.7 * i + (0 if s > 0 else 2.1))
                qf = [qs[j].slerp(target[j] @ euler_q(tw * (1.0 if j else 0.6) * CURL_SIGN, 0, 0), w) for j in range(3)]
                params[f - 1]["legs"][(side, i)] = {"mode": "fk", "q": qf}
    return params


def make_clips(R, classic=()):
    """[(name, params, loop)] for every clip; clips named in classic use the previous version's motion."""
    ref = lambda name: name not in classic and name not in CLASSIC
    death = apply_death_legs(R, death_params(R, ref("Crab_Death")))
    if ref("Crab_Death"): add_jiggle(R, death, False, 0.5)
    return [("Crab_Idle", idle_params(R, ref("Crab_Idle")), True),
            ("Crab_Scuttle_Left", scuttle_params(R, 1, ref("Crab_Scuttle_Left")), True),
            ("Crab_Scuttle_Right", scuttle_params(R, -1, ref("Crab_Scuttle_Right")), True),
            ("Crab_Walk_Forward", walk_params(R, ref("Crab_Walk_Forward")), True),
            ("Crab_Walk_Backward", walk_back_params(R), True),
            ("Crab_Turn_Left", turn_params(R, 1), True),
            ("Crab_Turn_Right", turn_params(R, -1), True),
            ("Crab_Threat", threat_params(R, ref("Crab_Threat")), False),
            ("Crab_Attack_Snap", attack_params(R, ref("Crab_Attack_Snap")), False),
            ("Crab_Claw_Snap", claw_snap_params(R), False),
            ("Crab_Hit", hit_params(R, ref("Crab_Hit")), False),
            ("Crab_Death", death, False)]


LOCOMOTION = {"Crab_Scuttle_Left": dict(speed_cm_s=SCUTTLE_SPEED, direction="crab's left"),
              "Crab_Scuttle_Right": dict(speed_cm_s=SCUTTLE_SPEED, direction="crab's right"),
              "Crab_Walk_Forward": dict(speed_cm_s=WALK_SPEED, direction="forward"),
              "Crab_Walk_Backward": dict(speed_cm_s=BACK_SPEED, direction="backward"),
              "Crab_Turn_Left": dict(turn_deg_s=TURN_RATE, direction="counter-clockwise seen from above"),
              "Crab_Turn_Right": dict(turn_deg_s=-TURN_RATE, direction="clockwise seen from above")}


# ---------------------------------------------------------------------------
# Bake, export, render
# ---------------------------------------------------------------------------
def bake(R, name, params, ground=True, clamp_tips=False):
    rig = R.rig
    act = bpy.data.actions.new(name); act.use_fake_user = True
    rig.animation_data_create(); rig.animation_data.action = act
    if hasattr(act, "slots") and hasattr(rig.animation_data, "action_slot"):
        if not act.slots:
            act.slots.new(id_type="OBJECT", name=rig.name)
        rig.animation_data.action_slot = act.slots[0]
    prev, stats = {}, dict(min_z=[], feet=[], claw_tips=[])
    for f, prm in enumerate(params, start=1):
        P = R.solve(prm)
        mz = R.min_z(P, skip_tips=not clamp_tips)                   # planted leg tips touch the ground by design
        if ground and mz < -0.05:                                   # keep the shell and limbs above the ground
            prm["body"]["loc"] = tuple(Vector(prm["body"]["loc"]) + Vector((0, 0, -mz)))
            P = R.solve(prm)
        stats["min_z"].append(R.min_z(P))
        stats["feet"].append({bn(f"leg{k[1]}", k[0]): tuple(v) for k, v in R.feet(P).items()})
        stats["claw_tips"].append({sd: tuple(P[bn("claw_tip", sd)].translation) for sd, s in SIDES})
        B = R.basis(P)
        for pb in rig.pose.bones:
            loc, q, sc = B[pb.name].decompose()
            if pb.name in prev and q.dot(prev[pb.name]) < 0: q.negate()
            prev[pb.name] = q
            pb.location, pb.rotation_quaternion, pb.scale = loc, q, (1, 1, 1)
            pb.keyframe_insert("location", frame=f, group=pb.name)
            pb.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)
            pb.keyframe_insert("scale", frame=f, group=pb.name)
    fcs = []
    if hasattr(act, "layers"):
        for layer in act.layers:
            for strip in layer.strips:
                for cb in strip.channelbags: fcs.extend(cb.fcurves)
    if not fcs and hasattr(act, "fcurves"): fcs = list(act.fcurves)
    for fc in fcs:
        for k in fc.keyframe_points: k.interpolation = "LINEAR"
    return act, stats


def plant_frames(feet, loop):
    """1-based frames on which each foot touches down (its contact point drops to the ground)."""
    out = {}
    n = len(feet) - (1 if loop else 0)
    for leg in feet[0]:
        z = [feet[f][leg][2] for f in range(n)]
        out[leg] = [f + 1 for f in range(n) if (f or loop) and z[f] < PLANT_Z <= z[f - 1]]
    return out


def set_action(rig, act):
    rig.animation_data.action = act
    if hasattr(act, "slots") and act.slots: rig.animation_data.action_slot = act.slots[0]


def export(R, act, path):
    sc = bpy.context.scene; rig = R.rig
    set_action(rig, act)
    n = int(round(act.frame_range[1]))
    sc.frame_start, sc.frame_end = 1, n; sc.frame_set(1)
    old = sc.name; sc.name = act.name
    bpy.ops.object.select_all(action="DESELECT"); rig.select_set(True); bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE"}, global_scale=1, apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_UNITS", axis_forward="X", axis_up="Z", use_space_transform=True,
        bake_space_transform=False, add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X",
        use_armature_deform_only=True, bake_anim=True, bake_anim_use_all_bones=True,
        bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True,
        bake_anim_step=1, bake_anim_simplify_factor=0)
    sc.name = old


def aim(cam, loc, target, scale):
    cam.location = Vector(loc); cam.data.ortho_scale = scale
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()


VIEWS = {"hero": ((150, -220, 140), (0, -6, 12), 128), "front": ((0, -300, 70), (0, -6, 18), 128),
         "death": ((170, -200, 150), (6, -4, 12), 135), "high": ((110, -170, 250), (0, -2, 8), 140)}


def render(R, act, out_dir, view, frames, tag=None):
    sc = bpy.context.scene
    set_action(R.rig, act)
    aim(sc.camera, *VIEWS[view])
    paths = []
    os.makedirs(out_dir, exist_ok=True)
    for f in frames:
        sc.frame_set(f)
        p = os.path.join(out_dir, f"{tag or act.name}_{view}_{f:03d}.png"); sc.render.filepath = p
        bpy.ops.render.render(write_still=True); paths.append(p)
    print("rendered", act.name, len(paths), flush=True)
    return paths


def render_travel(R, act, out_dir, period, speed, nframes):
    """Move the whole rig at the clip's ground speed past a fixed camera (the clip itself is in place)."""
    sc = bpy.context.scene
    set_action(R.rig, act)
    span = speed * (nframes - 1) / FPS
    aim(sc.camera, (40, -260, 120), (0, -2, 10), 150)
    paths = []
    for k in range(nframes):
        R.rig.location.x = -span / 2 + speed * k / FPS
        sc.frame_set(k % period + 1)
        p = os.path.join(out_dir, f"{act.name}_travel_{k + 1:03d}.png"); sc.render.filepath = p
        bpy.ops.render.render(write_still=True); paths.append(p)
    R.rig.location.x = 0.0
    print("rendered travel", act.name, len(paths), flush=True)
    return paths


def gif(paths, path, fps):
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in paths]
    pal = ims[len(ims) // 2].quantize(colors=160, method=Image.Quantize.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in ims]
    q[0].save(path, save_all=True, append_images=q[1:], duration=int(round(1000 / fps)), loop=0, optimize=True)


# ---------------------------------------------------------------------------
# Procedural locomotion demo: the rig driven the way a Control Rig would drive it in the game
# ---------------------------------------------------------------------------
def terrain_height(x, y):
    return (0.10 * x + 3.2 * math.sin(0.050 * x + 0.6) * math.cos(0.035 * y + 0.3)
            + 1.6 * math.sin(0.13 * x + 0.09 * y + 1.1) + 0.8 * math.sin(0.23 * y - 0.17 * x))


def terrain_object(x0, x1, y0, y1, step=2.5):
    nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    xs, ys = np.linspace(x0, x1, nx), np.linspace(y0, y1, ny)
    verts = [(x, y, terrain_height(x, y)) for y in ys for x in xs]
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]
    me = bpy.data.meshes.new("Terrain"); me.from_pydata(verts, [], faces); me.update()
    for poly in me.polygons: poly.use_smooth = True
    ob = bpy.data.objects.new("Procedural demo terrain", me)
    mat = bpy.data.materials.new("Demo sand"); mat.use_nodes = True
    nt = mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 0.6; noise.inputs["Detail"].default_value = 6
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35; ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[0].color = (0.16, 0.13, 0.09, 1); ramp.color_ramp.elements[1].color = (0.34, 0.28, 0.20, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    me.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def ground_frame(R, x):
    """Body frame over the terrain at body position x: a plane fitted through the ground under each rest foot sets
    the height and tilt (as line traces under the feet would in the game)."""
    pts = []
    for k in LEGS:
        T = R.T_rest[k]; px, py = x + T.x, T.y
        pts.append((px, py, terrain_height(px, py)))
    A = np.array([(1.0, p[0], p[1]) for p in pts]); z = np.array([p[2] for p in pts])
    a, b, c = np.linalg.lstsq(A, z, rcond=None)[0]
    nrm = Vector((-b, -c, 1.0)).normalized()
    q = Vector((0, 0, 1)).rotation_difference(nrm)
    q = Euler((0, 0, 0)).to_quaternion().slerp(q, 0.85)             # follow the slope a little less than fully
    return Matrix.Translation((x, 0.0, a + b * x)) @ q.to_matrix().to_4x4()


def procedural_demo(R, out_dir, nframes=105, speed=40.0, P=15, duty=0.6, lift=5.0):
    """Scuttle left over bumpy, rising ground. Each foot is planted where its rest position falls under the body at
    mid-stance, on the terrain; swinging feet arc to the next plant; the body follows a plane fitted to the ground
    under the feet. Returns the rendered frame paths and contact statistics."""
    sc = bpy.context.scene; rig = R.rig
    if rig.animation_data: rig.animation_data.action = None
    for o in bpy.data.objects:
        if o.name == "Studio floor": o.hide_render = True
    x_start = -0.5 * speed * (nframes - 1) / FPS
    terr = terrain_object(x_start - 200, -x_start + 240, -260, 340)
    sun = bpy.data.objects.new("Demo sun", bpy.data.lights.new("Demo sun", "SUN"))   # low, raking: shows the relief
    sun.data.energy = 2.2; sun.data.angle = math.radians(3); sun.data.color = (1.0, 0.93, 0.82)
    sun.rotation_euler = Euler((math.radians(68), 0, math.radians(-35)), "XYZ"); bpy.context.scene.collection.objects.link(sun)
    Pd = P / FPS
    off = {k: (0.0 if k in GROUP_A else 0.5) + METACHRONAL * (k[1] - 1) for k in LEGS}
    body_x = lambda t: x_start + speed * t

    def frame_at(t):                                                   # smoothed over +-0.1 s
        Ms = [ground_frame(R, body_x(t + dt)) for dt in (-0.1, -0.05, 0.0, 0.05, 0.1)]
        loc = sum((M.translation for M in Ms), Vector()) / len(Ms)
        q = Ms[2].to_quaternion()
        for M in Ms: q = q.slerp(M.to_quaternion(), 0.2)
        return Matrix.Translation(loc) @ q.to_matrix().to_4x4()

    def plant(k, m):
        tm = (m + duty / 2 - off[k]) * Pd                              # mid-stance of the m-th step
        p = frame_at(tm) @ R.T_rest[k]
        return Vector((p.x, p.y, terrain_height(p.x, p.y)))

    paths, err, slip, last, drop = [], 0.0, 0.0, {}, 0.0
    if out_dir: os.makedirs(out_dir, exist_ok=True)
    for fr in range(nframes):
        t = fr / FPS
        M = frame_at(t); Mi = M.inverted()
        prm = base(R)
        ph = 2 * TAU * (t / Pd - LAG)
        prm["body"] = {"loc": (0.5 * math.sin(ph), 0.0, -0.55 - 0.45 * math.cos(ph)), "rot": (0.0, 0.04 + 0.014 * math.sin(ph), 0.0)}
        prm["claws"] = {sd: {"arm": (GUARD["arm"][0] - 0.04 + 0.03 * math.cos(ph), 0, GUARD["arm"][2]), "wrist": GUARD["wrist"],
                             "hand": GUARD["hand"], "open": 0.0} for sd, s in SIDES}
        prm["eyes"] = look(0.16, -0.05); prm["antennae"] = {sd: (-0.25, 0.12) for sd, s in SIDES}
        world = {}
        for k in LEGS:
            s = 1 if k[0] == "L" else -1
            c = t / Pd + off[k]; m = math.floor(c); u = c - m
            if u < duty:
                p = plant(k, m)
            else:
                w = (u - duty) / (1 - duty)
                a, b = plant(k, m), plant(k, m + 1)
                h = smootherstep(w)
                p = a.lerp(b, h)
                p.z = a.z + (b.z - a.z) * h + lift * (1 + LEAD_LIFT * s) * math.sin(math.pi * (w + 0.5 * w * (1 - w)))
                T0 = R.T_rest[k]; o = (M.to_3x3() @ Vector((T0.x - R.C.x, T0.y - R.C.y, 0))).normalized()
                p = p + o * (REACH_OUT * math.sin(math.pi * w))
            world[k] = (p, u < duty)
            prm["legs"][k] = {"mode": "ik", "T": Mi @ p}
        Pz = R.solve(prm)
        for it in range(6):                    # lower the body until every foot reaches its goal (pelvis adjustment)
            miss = max((Pz[bn(f"leg{k[1]}_end", k[0])].translation - prm["legs"][k]["T"]).length for k in LEGS)
            if miss < 0.005: break
            lo = prm["body"]["loc"]; prm["body"]["loc"] = (lo[0], lo[1], lo[2] - 1.3 * miss)
            Pz = R.solve(prm)
        drop = max(drop, -prm["body"]["loc"][2] - 1.0)
        for k, (p, planted) in world.items():
            got = M @ Pz[bn(f"leg{k[1]}_end", k[0])].translation
            step = math.floor(t / Pd + off[k])
            if planted:
                err = max(err, (got - p).length)
                if last.get(k, (None, None))[1] == step: slip = max(slip, (got - last[k][0]).length)
            last[k] = (got, step if planted else None)
        rig.matrix_world = M
        B = R.basis(Pz)
        for pb in rig.pose.bones:
            loc, q, scl = B[pb.name].decompose()
            pb.location, pb.rotation_quaternion, pb.scale = loc, q, (1, 1, 1)
        bpy.context.view_layer.update()
        bx = body_x(t)
        aim(sc.camera, (bx + 70, -250, terrain_height(bx, 0) + 150), (bx + 6, 0, terrain_height(bx, 0) + 8), 150)
        if out_dir:
            p = os.path.join(out_dir, f"terrain_{fr + 1:03d}.png"); sc.render.filepath = p
            bpy.ops.render.render(write_still=True); paths.append(p)
    rig.matrix_world = Matrix.Identity(4)
    bpy.data.objects.remove(terr); bpy.data.objects.remove(sun)
    for o in bpy.data.objects:
        if o.name == "Studio floor": o.hide_render = False
    stats = dict(frames=nframes, speed_cm_s=speed, climb_cm=round(terrain_height(body_x((nframes - 1) / FPS), 0) - terrain_height(x_start, 0), 1),
                 planted_foot_error_cm=round(err, 4), planted_foot_slip_cm=round(slip, 4),
                 max_body_lowering_for_reach_cm=round(max(drop, 0.0), 2))
    print("PROCEDURAL_DEMO", json.dumps(stats), flush=True)
    return paths, stats


# ---------------------------------------------------------------------------
# Reference data for procedural setups
# ---------------------------------------------------------------------------
def procedural_rig(R):
    r = lambda v: [round(float(c), 2) for c in v]
    legs = []
    for side, i in LEGS:
        k = (side, i)
        H = R.rest[bn(f"leg{i}_upper", side)].translation
        legs.append(dict(
            leg=bn(f"leg{i}", side), side=side, index=i, gait_group="A" if k in GROUP_A else "B",
            chain=[bn(f"leg{i}_{seg}", side) for seg in ("upper", "lower", "tip")],
            foot_contact=bn(f"leg{i}_end", side), ik_goal=bn(f"ik_leg{i}", side), ik_effector=bn(f"ik_leg{i}_ankle", side),
            knee_pole=bn(f"pole_leg{i}", side), segment_lengths_cm=r(R.L[k]),
            max_reach_from_hip_cm=round(R.L[k][0] + R.L[k][1] + R.L[k][2], 2),
            hip_cm=r(H), rest_foot_cm=r(R.T_rest[k]), knee_tilt_deg=round(math.degrees(R.knee[k]), 1),
            tip_lean_deg=round(math.degrees(R.tilt[k]), 1),
            phase_offset=round((0.0 if k in GROUP_A else 0.5) + METACHRONAL * (i - 1), 4)))
    claws = [dict(claw=bn("claw", side), chain=[bn(f"claw_{p}", side) for p in ("arm", "wrist", "hand", "pincer")],
                  pincer_tip=bn("claw_tip", side), pinch_point=bn("claw_pinch", side), ik_goal=bn("ik_claw", side),
                  open_axis="claw_pincer bone local X; a negative rotation opens the moving finger (0.8 rad is wide open)",
                  lengths_cm=r([R.length[bn(f"claw_{p}", side)] for p in ("arm", "wrist", "hand", "pincer")]))
             for side, s in SIDES]
    springs = [dict(bone=bn(kind, side), lean_rad_per_g=g, frequency_hz=hz, damping_ratio=z, limit_rad=lim)
               for kind, (g, hz, z, lim) in JIGGLE.items() for side, s in SIDES]
    gaits = {
        "scuttle": dict(clip="Crab_Scuttle_Left / _Right", period_frames=14, duty=0.6, speed_cm_s=SCUTTLE_SPEED,
                        stride_cm=round(SCUTTLE_SPEED * 0.6 * 14 / FPS, 2), step_height_cm=5.5),
        "walk_forward": dict(clip="Crab_Walk_Forward", period_frames=24, duty=0.65, speed_cm_s=WALK_SPEED,
                             stride_cm=round(WALK_SPEED * 0.65 * 24 / FPS, 2), step_height_cm=4.0),
        "walk_backward": dict(clip="Crab_Walk_Backward", period_frames=24, duty=0.68, speed_cm_s=BACK_SPEED,
                              stride_cm=round(BACK_SPEED * 0.68 * 24 / FPS, 2), step_height_cm=3.5),
        "turn": dict(clip="Crab_Turn_Left / _Right", period_frames=20, duty=0.6, turn_deg_s=TURN_RATE,
                     sweep_deg=round(TURN_RATE * 0.6 * 20 / FPS, 2), step_height_cm=4.5)}
    return dict(
        units="centimetres, 30 fps", source_space="Blender: the crab faces -Y, its left is +X, Z is up. Unreal may mirror "
        "the Y axis on import, so read rest positions from the reference pose of the bones named here rather than "
        "hard-coding these numbers.",
        root="root", body="body", body_rest_height_cm=round(R.C.z, 2), shell_top_cm=round(float(R.shell_top), 2),
        foot_goal_root="ik_foot_root", claw_goal_root="ik_claw_root",
        legs=legs, claws=claws,
        eyes=dict(bones=[bn("eye", sd) for sd, s in SIDES], aim_axis="bone +Y runs up the stalk; tilt it to look"),
        antennae=[bn("antenna", sd) for sd, s in SIDES], mouthparts=[bn("mouthpart", sd) for sd, s in SIDES],
        gait=dict(pattern="alternating tetrapod: group A (leg1_l, leg2_r, leg3_l, leg4_r) and group B (the others) "
                          "half a cycle apart; each leg leads the one in front of it by metachronal_offset",
                  group_A=[bn(f"leg{i}", sd) for sd, i in sorted(GROUP_A)],
                  group_B=[bn(f"leg{i}", sd) for sd, i in LEGS if (sd, i) not in GROUP_A],
                  group_B_phase=0.5, metachronal_offset=METACHRONAL, swing_outward_arc_cm=REACH_OUT,
                  sideways_leading_legs_step_higher=LEAD_LIFT, body_dip_lag_cycles=LAG,
                  foot_plant_target="the rest foot position under the body at mid-stance, projected onto the ground",
                  presets=gaits),
        planted_rule=f"a foot is planted while its ik_legN bone is lower than {PLANT_Z} cm in the clip; use this "
                     "for foot locking or footstep effects",
        secondary_motion=springs)


def rig_diagram(R, path):
    """Top and front views of the skeleton: skinned bones, IK goals, knee poles and contact points."""
    from PIL import Image, ImageDraw, ImageFont
    W, Hh = 1800, 1000
    im = Image.new("RGB", (W, Hh), (247, 246, 242)); dr = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18); small = ImageFont.truetype("DejaVuSans.ttf", 14)
        big = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
    except OSError:
        font = small = big = ImageFont.load_default()
    sc = 7.0
    views = {"top": (lambda v: (470 - v.x * sc, 560 + v.y * sc)), "front": (lambda v: (1330 + v.x * sc, 620 - v.z * sc))}
    helper = lambda b: b.startswith(("ik_", "pole_", "claw_tip", "claw_pinch")) or "_end_" in b
    nh = sum(map(helper, R.bones))
    dr.text((30, 20), f"Crab skeleton: {len(R.bones)} bones (root, {len(R.bones) - nh - 1} that carry the mesh, {nh} helpers "
                      "for IK and procedural animation)", fill=(30, 30, 30), font=big)
    dr.text((300, 75), "Top view (crab facing up the page)", fill=(60, 60, 60), font=font)
    dr.text((1180, 75), "Front view (looking at the crab's face)", fill=(60, 60, 60), font=font)
    head = lambda b: R.rest[b].translation
    tail = lambda b: R.rest[b] @ Vector((0, R.length[b], 0))
    for vname, pr in views.items():
        for b in R.bones:
            if b == "root" or helper(b): continue
            col = (150, 30, 20) if b != "body" else (90, 90, 90)
            dr.line([pr(head(b)), pr(tail(b))], fill=col, width=5 if b != "body" else 3)
            x, y = pr(head(b)); dr.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(60, 20, 15))
        for side, i in LEGS:
            K = R.rest[bn(f"leg{i}_lower", side)].translation
            pole = head(bn(f"pole_leg{i}", side)); x, y = pr(pole)
            for a0, a1 in zip(np.linspace(0, 1, 9)[::2], np.linspace(0, 1, 9)[1::2]):
                dr.line([pr(K.lerp(pole, a0)), pr(K.lerp(pole, a1))], fill=(40, 90, 200), width=2)
            dr.polygon([(x, y - 7), (x + 7, y), (x, y + 7), (x - 7, y)], fill=(40, 90, 200))
            x, y = pr(head(bn(f"ik_leg{i}", side))); dr.ellipse([x - 9, y - 9, x + 9, y + 9], outline=(235, 120, 0), width=3)
            x, y = pr(head(bn(f"ik_leg{i}_ankle", side))); dr.rectangle([x - 5, y - 5, x + 5, y + 5], outline=(235, 120, 0), width=2)
        for side, s in SIDES:
            x, y = pr(head(bn("ik_claw", side))); dr.ellipse([x - 9, y - 9, x + 9, y + 9], outline=(235, 120, 0), width=3)
            x, y = pr(head(bn("claw_pinch", side))); dr.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(130, 60, 170))
        x, y = pr(head("root")); dr.line([x - 12, y, x + 12, y], fill=(0, 0, 0), width=2); dr.line([x, y - 12, x, y + 12], fill=(0, 0, 0), width=2)
    pr = views["top"]
    for b, txt, dx, dy in (("leg1_upper_l", "leg1_l", -40, -30), ("leg4_upper_l", "leg4_l", -20, 20), ("claw_arm_l", "claw_l (cutter)", -60, -40),
                           ("claw_arm_r", "claw_r (crusher)", 0, -40), ("eye_l", "eye_l", -10, -26), ("leg1_upper_r", "leg1_r", 10, -30)):
        x, y = pr(tail(b)); dr.text((x + dx, y + dy), txt, fill=(30, 30, 30), font=small)
    ly = 880
    items = [((150, 30, 20), "line", "skinned bone"), ((235, 120, 0), "ring", "IK goal (ik_legN, ik_claw): animated in every clip"),
             ((235, 120, 0), "square", "ik_legN_ankle: Two Bone IK effector"), ((40, 90, 200), "diamond", "knee pole (pole_legN)"),
             ((130, 60, 170), "dot", "claw_pinch: hit point"), ((0, 0, 0), "cross", "root (actor origin)")]
    for j, (col, kind, txt) in enumerate(items):
        x = 40 + (j % 3) * 580; y = ly + (j // 3) * 40
        if kind == "line": dr.line([x, y + 10, x + 30, y + 10], fill=col, width=5)
        elif kind == "ring": dr.ellipse([x + 6, y + 1, x + 24, y + 19], outline=col, width=3)
        elif kind == "square": dr.rectangle([x + 10, y + 5, x + 20, y + 15], outline=col, width=2)
        elif kind == "diamond": dr.polygon([(x + 15, y + 3), (x + 22, y + 10), (x + 15, y + 17), (x + 8, y + 10)], fill=col)
        elif kind == "dot": dr.ellipse([x + 9, y + 4, x + 21, y + 16], fill=col)
        else: dr.line([x + 5, y + 10, x + 25, y + 10], fill=col, width=2); dr.line([x + 15, y, x + 15, y + 20], fill=col, width=2)
        dr.text((x + 40, y), txt, fill=(30, 30, 30), font=font)
    im.save(path)


def load(blend):
    """Open the crab scene, keep only the exported skeleton (no constraints) and set the sign conventions the clips
    rely on. Returns the Rig."""
    global CURL_SIGN
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))
    rig = bpy.data.objects["Armature"]; mesh = bpy.data.objects["SK_Crab"]
    for o in [o for o in bpy.data.objects if o.type == "ARMATURE" and o is not rig]: bpy.data.objects.remove(o)
    for pb in rig.pose.bones:
        for c in list(pb.constraints): pb.constraints.remove(c)
    ctrl = [b.name for b in rig.data.bones if not b.use_deform]
    if ctrl:
        bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="EDIT")
        for nm in ctrl: rig.data.edit_bones.remove(rig.data.edit_bones[nm])
        bpy.ops.object.mode_set(mode="OBJECT")
    R = Rig(rig, mesh)
    # rest check: the solver must reproduce the rest pose exactly, helpers included
    B0 = R.basis(R.solve(base(R)))
    ang = lambda q: min(q.angle, TAU - q.angle)
    err = max(ang(B0[b].to_quaternion()) for b in R.bones)
    terr = max(B0[b].translation.length for b in R.bones)
    print(f"REST_CHECK rot {math.degrees(err):.4f} deg, loc {terr:.4f} cm over {len(R.bones)} bones", flush=True)
    assert math.degrees(err) < 0.05 and terr < 0.01, "solver does not reproduce the rest pose"
    # curl direction: bending the lower leg by +x must bring its tip under the body
    P = R.solve(base(R)); tip0 = R.feet(P)[("L", 2)]
    test = base(R); B = R.basis(P)
    test["legs"][("L", 2)] = {"mode": "fk", "q": [B["leg2_upper_l"].to_quaternion(), B["leg2_lower_l"].to_quaternion() @ euler_q(0.4, 0, 0),
                                                  B["leg2_tip_l"].to_quaternion()]}
    tip1 = R.feet(R.solve(test))[("L", 2)]
    CURL_SIGN = 1.0 if Vector((tip1.x, tip1.y)).length < Vector((tip0.x, tip0.y)).length else -1.0
    # a positive yaw swings the left eye stalk, antenna or mouthpart outward (toward +x); the right side mirrors it
    for kind, key in (("eye", "eyes"), ("antenna", "antennae"), ("mouthpart", "mouth")):
        b = bn(kind, "L"); SIGN[kind] = 1.0
        t0 = R.solve(base(R))[b] @ Vector((0, R.length[b], 0))
        tq = base(R); tq[key] = {"L": (0, 0, 0.3) if kind == "eye" else (0, 0.3)}
        t1 = R.solve(tq)[b] @ Vector((0, R.length[b], 0))
        SIGN[kind] = 1.0 if t1.x > t0.x else -1.0
    print("CURL_SIGN", CURL_SIGN, "SIGN", SIGN, flush=True)
    return R


def main():
    a = parse()
    R = load(a.blend); rig = R.rig
    if a.demo_only:
        sc = bpy.context.scene
        sc.render.resolution_x = sc.render.resolution_y = a.size; sc.cycles.samples = a.samples
        paths, demo = procedural_demo(R, os.path.join(a.out, "_anim_frames"))
        json.dump(demo, open(os.path.join(a.out, "procedural_demo.json"), "w"), indent=2)
        return gif(paths, os.path.join(a.out, "Crab_Procedural_Terrain.gif"), 30)
    classic = set(c for c in a.classic.split(",") if c)
    clips = make_clips(R, classic)
    if a.pose_test:
        return pose_test(R, clips, a)
    acts, stats, events = {}, {}, {}
    for name, params, loop in clips:
        act, st = bake(R, name, params, clamp_tips=(name == "Crab_Death"))
        acts[name] = act
        stats[name] = dict(frames=len(params), loop=loop, min_z=round(min(st["min_z"]), 3),
                           style="previous version" if name in classic | CLASSIC else "current")
        stats[name].update(LOCOMOTION.get(name, {}))
        if name in LOCOMOTION:
            pf = plant_frames(st["feet"], loop)
            stats[name]["foot_plant_frames"] = pf
            groups = {"A": [], "B": []}
            for leg, frs in pf.items():
                k = (leg[-1].upper(), int(leg[3]))
                groups["A" if k in GROUP_A else "B"].extend(frs)
            n = len(params) - 1                                  # one footstep per set of feet: their circular mean
            mean = lambda v: int(round(math.atan2(sum(math.sin(TAU * (f - 1) / n) for f in v),
                                                  sum(math.cos(TAU * (f - 1) / n) for f in v)) / TAU * n)) % n + 1
            events[name] = {"footsteps": sorted(mean(v) for v in groups.values() if v)}
        stats[name]["_feet"] = st["feet"]; stats[name]["_claws"] = st["claw_tips"]
        print("baked", name, len(params), "frames, min z", round(min(st["min_z"]), 2), flush=True)
    os.makedirs(a.out, exist_ok=True)
    for name, act in acts.items():
        export(R, act, os.path.join(a.out, f"AN_{name}.fbx"))
    events.update({"Crab_Threat": {"snap": [22, 34]}, "Crab_Attack_Snap": {"hit": [13]},
                   "Crab_Claw_Snap": {"snap_left": [9], "snap_right": [23]}, "Crab_Death": {"land": [25]}})
    for v in stats.values(): v.pop("_feet"); v.pop("_claws")
    Pa = R.solve({n: p for n, p, lp in clips}["Crab_Attack_Snap"][12])             # Crab_Attack_Snap, frame 13
    pin = [Pa[bn("claw_pinch", sd)].translation for sd, s in SIDES]
    mid = (pin[0] + pin[1]) / 2
    attack = dict(hit_frame=13, pinch_points_cm=[[round(c, 1) for c in p] for p in pin],
                  reach_forward_cm=round(-mid.y, 1), height_cm=round(mid.z, 1),
                  note="Measured at the claw_pinch_l/r bones (use them as hit points). Forward is the crab's facing "
                       "direction, measured from the root (the actor's origin).")
    json.dump(dict(fps=FPS, scuttle_speed_cm_s=SCUTTLE_SPEED, walk_speed_cm_s=WALK_SPEED, walk_backward_speed_cm_s=BACK_SPEED,
                   turn_rate_deg_s=TURN_RATE, clips=stats, events=events, attack=attack,
                   notes="Frame numbers are 1-based. Locomotion clips are in place; move the capsule at the listed speed "
                         "(turns: rotate the actor at the listed rate)."),
              open(os.path.join(a.out, "anim_stats.json"), "w"), indent=2)
    json.dump(procedural_rig(R), open(os.path.join(a.out, "procedural_rig.json"), "w"), indent=2)
    rig_diagram(R, os.path.join(a.out, "Rig_Diagram.png"))
    set_action(rig, acts["Crab_Idle"]); bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 91
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.out, "Crab_Anims.blend"))
    if a.no_render:
        _, demo = procedural_demo(R, "")
        json.dump(demo, open(os.path.join(a.out, "procedural_demo.json"), "w"), indent=2)
        return
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = a.size; sc.cycles.samples = a.samples
    frames_dir = os.path.join(a.out, "_anim_frames")
    G = {}
    G["Idle"] = render(R, acts["Crab_Idle"], frames_dir, "hero", range(1, 91, 2)), 15
    G["Scuttle"] = render(R, acts["Crab_Scuttle_Left"], frames_dir, "front", range(1, 15)) * 3, 30
    G["Scuttle_Travel"] = render_travel(R, acts["Crab_Scuttle_Left"], frames_dir, 14, SCUTTLE_SPEED, 43), 30
    G["Walk"] = render(R, acts["Crab_Walk_Forward"], frames_dir, "hero", range(1, 25)) * 2, 30
    G["Walk_Backward"] = render(R, acts["Crab_Walk_Backward"], frames_dir, "hero", range(1, 25)) * 2, 30
    G["Turn"] = render(R, acts["Crab_Turn_Left"], frames_dir, "high", range(1, 21)) * 3, 30
    G["Threat"] = render(R, acts["Crab_Threat"], frames_dir, "hero", range(1, 56)), 30
    G["Attack"] = render(R, acts["Crab_Attack_Snap"], frames_dir, "hero", range(1, 34)), 30
    G["Claw_Snap"] = render(R, acts["Crab_Claw_Snap"], frames_dir, "front", range(1, 32)), 30
    G["Hit"] = render(R, acts["Crab_Hit"], frames_dir, "hero", range(1, 22)), 30
    G["Death"] = render(R, acts["Crab_Death"], frames_dir, "death", range(1, 61)), 30
    paths, demo = procedural_demo(R, frames_dir)
    json.dump(demo, open(os.path.join(a.out, "procedural_demo.json"), "w"), indent=2)
    G["Procedural_Terrain"] = paths, 30
    for k, (paths, fps) in G.items():
        gif(paths, os.path.join(a.out, f"Crab_{k}.gif"), fps)
    from PIL import Image, ImageDraw
    picks = [("Idle", 30), ("Scuttle", 4), ("Turn", 6), ("Threat", 20), ("Attack", 8), ("Attack", 13), ("Claw_Snap", 9),
             ("Hit", 4), ("Death", 18), ("Death", 40), ("Walk_Backward", 6), ("Procedural_Terrain", 60)]
    cols = 4; rows = math.ceil(len(picks) / cols)
    sheet = Image.new("RGB", (cols * a.size, rows * (a.size + 20)), (240, 240, 238)); dr = ImageDraw.Draw(sheet)
    for k, (clip, fr) in enumerate(picks):
        paths = G[clip][0]
        im = Image.open(paths[fr // 2] if clip == "Idle" else paths[min(fr - 1, len(paths) - 1)]).convert("RGB")
        x, y = (k % cols) * a.size, (k // cols) * (a.size + 20)
        sheet.paste(im, (x, y)); dr.text((x + 6, y + a.size + 4), f"{clip} frame {fr}", fill=(30, 30, 30))
    sheet.save(os.path.join(a.out, "Preview_Animations.png"))


def pose_test(R, clips, a):
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = a.size; sc.cycles.samples = a.samples
    picks = {"Crab_Idle": [12, 30], "Crab_Scuttle_Left": [1, 5], "Crab_Walk_Backward": [6], "Crab_Turn_Left": [5],
             "Crab_Threat": [6, 20], "Crab_Attack_Snap": [8, 13], "Crab_Claw_Snap": [9], "Crab_Hit": [4], "Crab_Death": [12, 19, 40]}
    from PIL import Image, ImageDraw
    ims = []
    for name, params, loop in clips:
        if name not in picks: continue
        act, st = bake(R, name, params, clamp_tips=(name == "Crab_Death"))
        view = "death" if "Death" in name else "high" if "Turn" in name else "hero"
        for fr in picks[name]:
            ims.append((name, fr, render(R, act, os.path.join(a.out, "_pose"), view, [fr])[0]))
    cols = 5; rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGB", (cols * a.size, rows * (a.size + 20)), (240, 240, 238)); dr = ImageDraw.Draw(sheet)
    for k, (name, fr, p) in enumerate(ims):
        x, y = (k % cols) * a.size, (k // cols) * (a.size + 20)
        sheet.paste(Image.open(p).convert("RGB"), (x, y)); dr.text((x + 6, y + a.size + 4), f"{name} {fr}", fill=(30, 30, 30))
    sheet.save(os.path.join(a.out, "_pose_test.png"))


if __name__ == "__main__":
    main()
