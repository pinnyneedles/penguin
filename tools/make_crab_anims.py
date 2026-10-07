#!/usr/bin/env python3
"""Author the crab's animation set for Unreal Engine and export one FBX per clip.

    python3 tools/make_crab_anims.py --blend crab/Crab.blend --out crab [--no-render] [--pose-test]
        [--size 360] [--samples 12]

Clips (30 fps, in place; looping clips repeat frame 1 as their last frame):
    Crab_Idle            91 f  loop   breathing, eye stalks look around, claw snips, a leg shuffle
    Crab_Scuttle_Left    15 f  loop   sideways run toward the crab's left; planted feet match 50 cm/s
    Crab_Scuttle_Right   15 f  loop   the same toward its right
    Crab_Walk_Forward    25 f  loop   slow forward walk; planted feet match 22 cm/s
    Crab_Threat          55 f         rears up, claws raised wide and open, two snaps (frames 22 and 34)
    Crab_Attack_Snap     33 f         wind-up, lunge and double pinch (hit on frame 13)
    Crab_Hit             21 f         flinch: knocked back, eyes fold down, claws tucked
    Crab_Death           60 f         flinch, curl, flip onto its back (lands on frame 25), legs twitch

Legs use an exact 2-bone IK with the tip leaning outward, so planted feet stay put. Every piece of the
crab is rigid and belongs to one bone, so ground contact is computed exactly from the bone transforms.
The armature object is named "Armature" so Unreal does not add an extra root bone.
"""
import argparse, json, math, os, sys
import bpy
import numpy as np
from mathutils import Vector, Matrix, Quaternion, Euler
from scipy.interpolate import PchipInterpolator

FPS = 30
TAU = 2 * math.pi
SIDES = (("L", 1), ("R", -1))
GROUP_A = {("L", 1), ("R", 2), ("L", 3), ("R", 4)}           # alternating tetrapod gait
SCUTTLE_SPEED, WALK_SPEED = 50.0, 22.0


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", default="crab/Crab.blend")
    ap.add_argument("--out", default="crab")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--pose-test", action="store_true")
    ap.add_argument("--size", type=int, default=360)
    ap.add_argument("--samples", type=int, default=12)
    return ap.parse_args(argv)


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


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
        self.bones = [b.name for b in rig.data.bones]
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in rig.data.bones}
        self.rest = {b.name: b.matrix_local.copy() for b in rig.data.bones}
        self.rest_inv = {k: m.inverted() for k, m in self.rest.items()}
        self.rel = {n: (self.rest_inv[p] @ self.rest[n]) if p else self.rest[n] for n, p in self.parent.items()}
        self.rel_inv = {k: m.inverted() for k, m in self.rel.items()}
        for p in rig.pose.bones: p.rotation_mode = "QUATERNION"
        self.C = self.rest["body"].translation.copy()
        self.T_rest, self.sign, self.knee = {}, {}, {}
        for side, s in SIDES:
            for i in range(1, 5):
                k = (side, i)
                self.knee[k] = math.radians(rig.data.bones[f"leg{i}_upper.{side}"].get("knee_tilt_deg", 0.0))
                self.T_rest[k] = self.rest[f"leg{i}_tip.{side}"] @ Vector((0, self.length(f"leg{i}_tip.{side}"), 0))
                H, K, D, T = self.leg_rest_points(side, i)
                u = (D - H).normalized(); w = ((K - H) - u * (K - H).dot(u)).normalized()
                x_rest = self.rest[f"leg{i}_upper.{side}"].to_3x3().col[0]
                self.sign[k] = 1.0 if u.cross(w).dot(x_rest) > 0 else -1.0
                self.tilt = math.atan2((T - D).cross(Vector((0, 0, -1))).length, (T - D).dot(Vector((0, 0, -1))))
        # rigid skinning: vertices by bone, for exact ground contact
        gi = {g.index: g.name for g in mesh.vertex_groups}
        co = np.array([v.co[:] for v in mesh.data.vertices])
        bone_of = np.array([gi[v.groups[0].group] for v in mesh.data.vertices])
        self.vgroups = {b: co[bone_of == b] for b in set(bone_of)}
        top = self.vgroups["body"][:, 2].max()
        self.shell_top = top - self.C.z                       # carapace top above the body pivot

    def length(self, b):
        return self.rig.data.bones[b].length

    def leg_rest_points(self, side, i):
        H = self.rest[f"leg{i}_upper.{side}"].translation.copy()
        K = self.rest[f"leg{i}_lower.{side}"].translation.copy()
        D = self.rest[f"leg{i}_tip.{side}"].translation.copy()
        return H, K, D, self.T_rest[(side, i)] if (side, i) in self.T_rest else D

    def lengths(self, side, i):
        return tuple(self.length(f"leg{i}_{seg}.{side}") for seg in ("upper", "lower", "tip"))

    def solve(self, prm):
        """prm -> {bone: posed matrix in armature space}."""
        P = {}
        root = prm.get("root", Matrix.Identity(4))
        P["root"] = root @ self.rest["root"]
        bd = prm.get("body", {})
        d = Vector(bd.get("loc", (0, 0, 0))); r = bd.get("rot", (0, 0, 0))
        R = Euler(r, "XYZ").to_matrix().to_4x4()
        A = Matrix.Translation(self.C + d) @ R @ Matrix.Translation(-self.C)
        P["body"] = P["root"] @ self.rest_inv["root"] @ A @ self.rest["body"]
        Rb = (P["body"] @ self.rest_inv["body"]).to_3x3()
        up_b = (Rb @ Vector((0, 0, 1))).normalized()

        def under(b):                                      # bone carried by its posed parent, no own motion
            p = self.parent[b]
            return P[p] @ self.rel[b]

        def fk(b, q):
            P[b] = under(b) @ q.to_matrix().to_4x4()

        for side, s in SIDES:
            e = prm.get("eyes", {}).get(side, (0, 0, 0))
            fk(f"eye.{side}", euler_q(e[0], e[1], e[2] * s * EYE_SIGN))
            c = prm.get("claws", {}).get(side, {})
            fk(f"claw_arm.{side}", euler_q(c.get("arm", (0, 0, 0))[0], c.get("arm", (0, 0, 0))[1], c.get("arm", (0, 0, 0))[2] * s))
            fk(f"claw_wrist.{side}", euler_q(c.get("wrist", (0, 0, 0))[0], c.get("wrist", (0, 0, 0))[1], c.get("wrist", (0, 0, 0))[2] * s))
            fk(f"claw_hand.{side}", euler_q(c.get("hand", (0, 0, 0))[0], c.get("hand", (0, 0, 0))[1], c.get("hand", (0, 0, 0))[2] * s))
            fk(f"claw_pincer.{side}", euler_q(-c.get("open", 0.0), 0, 0))
            for i in range(1, 5):
                lg = prm.get("legs", {}).get((side, i), {"mode": "ik", "T": self.T_rest[(side, i)]})
                names = [f"leg{i}_{seg}.{side}" for seg in ("upper", "lower", "tip")]
                if lg["mode"] == "fk":
                    for b, q in zip(names, lg["q"]): fk(b, q)
                    continue
                H = under(names[0]).translation
                T = Vector(lg["T"])
                L1, L2, L3 = self.lengths(side, i)
                v = T - H
                out = (v - up_b * v.dot(up_b)).normalized()
                dd = (-up_b * math.cos(self.tilt) + out * math.sin(self.tilt)).normalized()
                Dp = T - dd * L3
                vv = Dp - H; dist = vv.length
                dist_c = min(max(dist, abs(L1 - L2) + 1e-3), L1 + L2 - 1e-3)
                u = vv / dist
                a = math.acos(min(max((L1 * L1 + dist_c * dist_c - L2 * L2) / (2 * L1 * dist_c), -1), 1))
                fb = Rb @ Vector((0, -1, 0))                            # knee bends up, tilted toward the front
                fp = fb - out * fb.dot(out) - up_b * fb.dot(up_b)
                fp = fp.normalized() if fp.length > 1e-6 else Vector((0, 0, 0))
                g = self.knee[(side, i)]
                pole = up_b * math.cos(g) + fp * math.sin(g)
                w = (pole - u * u.dot(pole)).normalized()
                K = H + L1 * (math.cos(a) * u + math.sin(a) * w)
                Dp = K + (Dp - K).normalized() * L2                    # exact segment lengths when out of reach
                Tp = Dp + (T - Dp).normalized() * L3
                n = u.cross(w).normalized() * self.sign[(side, i)]
                for b, h, t in zip(names, (H, K, Dp), (K, Dp, Tp)):
                    y = (t - h).normalized(); x = (n - y * n.dot(y)).normalized(); z = x.cross(y)
                    M = Matrix((x, y, z)).transposed().to_4x4(); M.translation = h
                    P[b] = M
        return P

    def basis(self, P):
        out = {}
        for b in self.bones:
            p = self.parent[b]
            out[b] = (self.rest_inv[b] @ P[b]) if p is None else (self.rel_inv[b] @ P[p].inverted() @ P[b])
        return out

    def min_z(self, P, skip_tips=False):
        z = np.inf
        for b, V in self.vgroups.items():
            if skip_tips and "_tip." in b: continue
            M = np.array(P[b] @ self.rest_inv[b])
            z = min(z, float((V @ M[:3, :3].T + M[:3, 3])[:, 2].min()))
        return z

    def tips(self, P):
        return {(side, i): P[f"leg{i}_tip.{side}"] @ Vector((0, self.length(f"leg{i}_tip.{side}"), 0))
                for side, s in SIDES for i in range(1, 5)}


# ---------------------------------------------------------------------------
# Clip parameters
# ---------------------------------------------------------------------------
def base(R):
    return {"body": {"loc": (0, 0, 0), "rot": (0, 0, 0)}, "claws": {}, "eyes": {},
            "legs": {(side, i): {"mode": "ik", "T": R.T_rest[(side, i)].copy()} for side, s in SIDES for i in range(1, 5)}}


def gait(R, f, P, duty, stride, lift, direction, phase_b=0.5):
    legs = {}
    for side, s in SIDES:
        for i in range(1, 5):
            c = ((f - 1) / P + (0.0 if (side, i) in GROUP_A else phase_b)) % 1.0
            if c < duty:
                off, z = stride * (0.5 - c / duty), 0.0
            else:
                sw = (c - duty) / (1 - duty)
                off, z = stride * (-0.5 + smoothstep(sw)), lift * math.sin(math.pi * sw) ** 0.85
            legs[(side, i)] = {"mode": "ik", "T": R.T_rest[(side, i)] + Vector(direction) * off + Vector((0, 0, z))}
    return legs


GUARD = {"arm": (-0.18, 0, 0.05), "wrist": (-0.05, 0, 0), "hand": (0.05, 0, 0)}


def idle_params(R, n=91):
    out = []
    for f in range(1, n + 1):
        t = (f - 1) / (n - 1)
        p = base(R)
        p["body"] = {"loc": (0.25 * math.sin(TAU * t), 0, 0.45 * math.sin(2 * TAU * t)),     # zero at both ends: rest pose
                     "rot": (0.015 * math.sin(TAU * t), 0.012 * math.sin(2 * TAU * t), 0.02 * math.sin(TAU * t) * math.cos(TAU * t))}
        ey = keyed([(1, 0), (16, 0), (21, 0.35), (38, 0.35), (43, -0.25), (62, -0.25), (67, 0), (91, 0)], f)
        ep = keyed([(1, 0), (16, 0), (21, -0.1), (38, -0.1), (43, 0.08), (62, 0.08), (67, 0), (91, 0)], f)
        p["eyes"] = {"L": (ep, 0, ey), "R": (ep, 0, ey + 0.06 * math.sin(TAU * 3 * t))}
        snipL = keyed([(1, 0), (26, 0), (29, 0.5), (32, 0.04), (35, 0.45), (38, 0), (91, 0)], f)
        snipR = keyed([(1, 0), (58, 0), (62, 0.55), (66, 0.02), (91, 0)], f)
        sway = 0.05 * math.sin(TAU * t)
        lift = -0.06 * math.sin(math.pi * t) ** 2
        p["claws"] = {"L": {"arm": (lift + sway, 0, 0.03 * math.sin(math.pi * t)), "wrist": (0, 0, 0), "hand": (0.02 * math.sin(TAU * t), 0, 0), "open": snipL},
                      "R": {"arm": (lift - sway, 0, 0.03 * math.sin(math.pi * t)), "wrist": (0, 0, 0), "hand": (-0.02 * math.sin(TAU * t), 0, 0), "open": snipR}}
        if 48 <= f <= 58:                                    # shuffle one back leg
            u = (f - 48) / 10
            p["legs"][("R", 3)]["T"] = R.T_rest[("R", 3)] + Vector((0.8 * math.sin(math.pi * u), -1.2 * math.sin(math.pi * u), 3.5 * math.sin(math.pi * u)))
        out.append(p)
    return out


def scuttle_params(R, direction, P=14):
    duty = 0.6
    stride = SCUTTLE_SPEED * duty * P / FPS
    out = []
    for f in range(1, P + 2):
        t = (f - 1) / P
        p = base(R)
        p["legs"] = gait(R, f, P, duty, stride, 5.5, (direction, 0, 0))
        p["body"] = {"loc": (0.6 * direction * math.sin(2 * TAU * t), 0, -0.5 + 0.55 * math.cos(2 * TAU * t)),
                     "rot": (0.0, 0.035 * direction + 0.012 * math.sin(2 * TAU * t), 0.0)}
        b = 0.06 * math.cos(2 * TAU * t)
        p["claws"] = {sd: {"arm": (GUARD["arm"][0] + b, 0, GUARD["arm"][2]), "wrist": GUARD["wrist"], "hand": GUARD["hand"], "open": 0.0}
                      for sd, s in SIDES}
        p["eyes"] = {sd: (0.05 * math.sin(2 * TAU * t), 0, 0.15 * direction) for sd, s in SIDES}
        out.append(p)
    return out


def walk_params(R, P=24):
    duty = 0.65
    stride = WALK_SPEED * duty * P / FPS
    out = []
    for f in range(1, P + 2):
        t = (f - 1) / P
        p = base(R)
        p["legs"] = gait(R, f, P, duty, stride, 4.0, (0, -1, 0))
        p["body"] = {"loc": (0.4 * math.sin(2 * TAU * t), 0, -0.3 + 0.35 * math.cos(2 * TAU * t)),
                     "rot": (0.02 * math.sin(2 * TAU * t), 0.015 * math.sin(TAU * t), 0.02 * math.sin(TAU * t))}
        p["claws"] = {sd: {"arm": (GUARD["arm"][0] + 0.04 * math.sin(TAU * t + (0 if s > 0 else math.pi)), 0, GUARD["arm"][2]),
                           "wrist": GUARD["wrist"], "hand": GUARD["hand"], "open": 0.0} for sd, s in SIDES}
        p["eyes"] = {sd: (0.04 * math.sin(TAU * t), 0, 0.08 * math.sin(TAU * t + s)) for sd, s in SIDES}
        out.append(p)
    return out


def claw_keys(f, keys):
    """keys: [(frame, dict(arm=(x,y,z), wrist=..., hand=..., open=a))] -> claw dict at f."""
    res = {}
    for part in ("arm", "wrist", "hand"):
        res[part] = tuple(keyed([(k[0], k[1][part]) for k in keys], f))
    res["open"] = float(keyed([(k[0], k[1]["open"]) for k in keys], f))
    return res


REST_CLAW = dict(arm=(0, 0, 0), wrist=(0, 0, 0), hand=(0, 0, 0), open=0.0)
RAISED = dict(arm=(-0.70, 0, -1.00), wrist=(-0.25, 0, -0.30), hand=(0.15, 0, -0.10), open=0.80)


def threat_params(R, n=55):
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
        out.append(p)
    return out


WIND = dict(arm=(-0.45, 0, -0.75), wrist=(-0.2, 0, -0.15), hand=(0.15, 0, 0), open=0.8)   # wide, beside the eyes
STRIKE = dict(arm=(-0.12, 0, 0.06), wrist=(0.05, 0, -0.05), hand=(-0.05, 0, -0.08), open=0.8)   # forward, claws apart
SNAPPED = dict(STRIKE, open=0.0)


def attack_params(R, n=33):
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
        out.append(p)
    return out


TUCK = dict(arm=(0.35, 0, 0.35), wrist=(0.15, 0, 0.1), hand=(0.1, 0, 0), open=0.0)


def hit_params(R, n=21):
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
        out.append(p)
    return out


def death_params(R, n=60):
    """Flinch, curl the legs, hop and flip onto the back, land on frame 25, twitch and go still."""
    out = []
    switch = 6
    for f in range(1, n + 1):
        p = base(R)
        roll = keyed([(1, 0), (switch, 0.08), (12, 0.25), (19, math.pi * 0.62), (25, math.pi), (28, math.pi * 0.985), (32, math.pi)], f)
        x = keyed([(1, 0), (12, 2.0), (25, 14.0), (32, 15.0)], f)
        z = keyed([(1, 0), (switch, 1.5), (10, -3.0), (17, 14.0), (25, R.shell_top - R.C.z + 0.3), (28, R.shell_top - R.C.z + 2.0),
                   (32, R.shell_top - R.C.z + 0.3)], f)
        p["body"] = {"loc": (x, keyed([(1, 0), (switch, 3.0), (25, 2.0)], f), z), "rot": (keyed([(1, 0), (switch, -0.12), (20, 0.05), (32, 0)], f), roll, 0)}
        p["claws"] = {sd: claw_keys(f, [(1, REST_CLAW), (switch, TUCK), (24, dict(arm=(0.2, 0, 0.5), wrist=(0.3, 0, 0.2), hand=(0.2, 0, 0), open=0.0)),
                                        (40, dict(arm=(0.05, 0, 0.2), wrist=(0.1, 0, 0.1), hand=(0.05, 0, 0), open=0.25)),
                                        (60, dict(arm=(0.1, 0, 0.25), wrist=(0.15, 0, 0.1), hand=(0.05, 0, 0), open=0.2))]) for sd, s in SIDES}
        p["eyes"] = {sd: (keyed([(1, 0), (switch, -0.9), (40, -0.7), (60, -0.95)], f), 0, keyed([(1, 0), (40, 0.25 * s), (60, 0.35 * s)], f)) for sd, s in SIDES}
        out.append(p)
    return out


def apply_death_legs(R, params, switch=6, curl_by=16, n=60):
    """Legs plant until the flinch, then blend (in the body's frame) to a curled pose and twitch."""
    P_sw = R.solve(params[switch - 1]); B_sw = R.basis(P_sw)
    for side, s in SIDES:
        for i in range(1, 5):
            names = [f"leg{i}_{seg}.{side}" for seg in ("upper", "lower", "tip")]
            qs = [B_sw[b].to_quaternion() for b in names]
            sg = R.sign[(side, i)]
            # bend about each segment's hinge so the leg folds in under the body (sign checked in __main__)
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


CURL_SIGN = 1.0
EYE_SIGN = 1.0          # set in main so that a positive eye yaw turns both stalks toward the crab's left


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
    prev, stats = {}, dict(min_z=[], tips=[])
    for f, prm in enumerate(params, start=1):
        P = R.solve(prm)
        mz = R.min_z(P, skip_tips=not clamp_tips)                   # planted leg tips touch the ground by design
        if ground and mz < -0.05:                                   # keep the shell and limbs above the ground
            prm["body"]["loc"] = tuple(Vector(prm["body"]["loc"]) + Vector((0, 0, -mz)))
            P = R.solve(prm)
        mz = R.min_z(P)
        stats["min_z"].append(mz); stats["tips"].append({f"{k[0]}{k[1]}": tuple(v) for k, v in R.tips(P).items()})
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
         "death": ((170, -200, 150), (6, -4, 12), 135)}


def render(R, act, out_dir, view, frames):
    sc = bpy.context.scene
    set_action(R.rig, act)
    aim(sc.camera, *VIEWS[view])
    paths = []
    os.makedirs(out_dir, exist_ok=True)
    for f in frames:
        sc.frame_set(f)
        p = os.path.join(out_dir, f"{act.name}_{view}_{f:03d}.png"); sc.render.filepath = p
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


def load(blend):
    """Open the crab scene, keep only the deform skeleton (the posing controls are for animators) and set the
    sign conventions the clips rely on. Returns the Rig."""
    global CURL_SIGN, EYE_SIGN
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
    if "Controls" in rig.data.collections: rig.data.collections.remove(rig.data.collections["Controls"])
    R = Rig(rig, mesh)
    # rest check: the solver must reproduce the rest pose exactly
    B0 = R.basis(R.solve(base(R)))
    err = max((B0[b].to_quaternion().angle if B0[b].to_quaternion().angle < math.pi else TAU - B0[b].to_quaternion().angle) for b in R.bones)
    terr = max(B0[b].translation.length for b in R.bones)
    print(f"REST_CHECK rot {math.degrees(err):.4f} deg, loc {terr:.4f} cm", flush=True)
    assert math.degrees(err) < 0.05 and terr < 0.01, "solver does not reproduce the rest pose"
    # curl direction: bending the lower leg by +x must bring its tip under the body
    P = R.solve(base(R)); tip0 = R.tips(P)[("L", 2)]
    test = base(R); B = R.basis(P)
    test["legs"][("L", 2)] = {"mode": "fk", "q": [B["leg2_upper.L"].to_quaternion(), B["leg2_lower.L"].to_quaternion() @ euler_q(0.4, 0, 0), B["leg2_tip.L"].to_quaternion()]}
    tip1 = R.tips(R.solve(test))[("L", 2)]
    CURL_SIGN = 1.0 if Vector((tip1.x, tip1.y)).length < Vector((tip0.x, tip0.y)).length else -1.0
    # eye yaw: a positive value turns both stalks toward the crab's left
    t0 = R.solve(base(R))["eye.L"] @ Vector((0, 1, 0))
    tq = base(R); tq["eyes"] = {"L": (0, 0, 0.3)}
    EYE_SIGN = 1.0
    t1 = R.solve(tq)["eye.L"] @ Vector((0, 1, 0))
    EYE_SIGN = 1.0 if t1.x > t0.x else -1.0
    print("CURL_SIGN", CURL_SIGN, "EYE_SIGN", EYE_SIGN, flush=True)
    return R


def make_clips(R):
    return [("Crab_Idle", idle_params(R), True), ("Crab_Scuttle_Left", scuttle_params(R, 1), True),
            ("Crab_Scuttle_Right", scuttle_params(R, -1), True), ("Crab_Walk_Forward", walk_params(R), True),
            ("Crab_Threat", threat_params(R), False), ("Crab_Attack_Snap", attack_params(R), False),
            ("Crab_Hit", hit_params(R), False), ("Crab_Death", apply_death_legs(R, death_params(R)), False)]


def main():
    a = parse()
    R = load(a.blend); rig = R.rig
    clips = make_clips(R)
    if a.pose_test:
        return pose_test(R, clips, a)
    acts, stats = {}, {}
    for name, params, loop in clips:
        act, st = bake(R, name, params, clamp_tips=(name == "Crab_Death"))
        acts[name] = act
        stats[name] = dict(frames=len(params), loop=loop, min_z=round(min(st["min_z"]), 3))
        print("baked", name, len(params), "frames, min z", round(min(st["min_z"]), 2), flush=True)
        stats[name]["_tips"] = st["tips"]
    os.makedirs(a.out, exist_ok=True)
    for name, act in acts.items():
        export(R, act, os.path.join(a.out, f"AN_{name}.fbx"))
    events = {"Crab_Scuttle_Left": {"footsteps": [1, 8]}, "Crab_Scuttle_Right": {"footsteps": [1, 8]},
              "Crab_Walk_Forward": {"footsteps": [1, 13]}, "Crab_Threat": {"snap": [22, 34]},
              "Crab_Attack_Snap": {"hit": [13]}, "Crab_Death": {"land": [25]}}
    tips = {k: v.pop("_tips") for k, v in stats.items()}
    Pa = R.solve(clips[5][1][12])                                 # Crab_Attack_Snap, frame 13
    pin = [Pa[f"claw_pincer.{sd}"] @ Vector((0, R.length(f"claw_pincer.{sd}"), 0)) for sd, s in SIDES]
    mid = (pin[0] + pin[1]) / 2
    attack = dict(hit_frame=13, pincer_tips_cm=[[round(c, 1) for c in p] for p in pin],
                  reach_forward_cm=round(-mid.y, 1), height_cm=round(mid.z, 1),
                  note="Forward is the crab's facing direction, measured from the root (the actor's origin).")
    json.dump(dict(fps=FPS, scuttle_speed_cm_s=SCUTTLE_SPEED, walk_speed_cm_s=WALK_SPEED, clips=stats, events=events, attack=attack,
                   notes="Frame numbers are 1-based. Locomotion clips are in place; move the capsule at the listed speed."),
              open(os.path.join(a.out, "anim_stats.json"), "w"), indent=2)
    set_action(rig, acts["Crab_Idle"]); bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 91
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.out, "Crab_Anims.blend"))
    if a.no_render:
        return
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = a.size; sc.cycles.samples = a.samples
    frames_dir = os.path.join(a.out, "_anim_frames")
    G = {}
    G["Idle"] = render(R, acts["Crab_Idle"], frames_dir, "hero", range(1, 91, 2)), 15
    G["Scuttle"] = render(R, acts["Crab_Scuttle_Left"], frames_dir, "front", range(1, 15)) * 3, 30
    G["Scuttle_Travel"] = render_travel(R, acts["Crab_Scuttle_Left"], frames_dir, 14, SCUTTLE_SPEED, 43), 30
    G["Walk"] = render(R, acts["Crab_Walk_Forward"], frames_dir, "hero", range(1, 25)) * 2, 30
    G["Threat"] = render(R, acts["Crab_Threat"], frames_dir, "hero", range(1, 56)), 30
    G["Attack"] = render(R, acts["Crab_Attack_Snap"], frames_dir, "hero", range(1, 34)), 30
    G["Hit"] = render(R, acts["Crab_Hit"], frames_dir, "hero", range(1, 22)), 30
    G["Death"] = render(R, acts["Crab_Death"], frames_dir, "death", range(1, 61)), 30
    for k, (paths, fps) in G.items():
        gif(paths, os.path.join(a.out, f"Crab_{k}.gif"), fps)
    from PIL import Image, ImageDraw
    picks = [("Idle", 30), ("Scuttle", 4), ("Threat", 20), ("Attack", 8), ("Attack", 13), ("Hit", 4), ("Death", 18), ("Death", 40)]
    sheet = Image.new("RGB", (4 * a.size, 2 * a.size + 40), (240, 240, 238)); dr = ImageDraw.Draw(sheet)
    for k, (clip, fr) in enumerate(picks):
        paths = G[clip][0]
        im = Image.open(paths[min(fr - 1, len(paths) - 1)] if clip != "Idle" else paths[fr // 2]).convert("RGB")
        x, y = (k % 4) * a.size, (k // 4) * (a.size + 20)
        sheet.paste(im, (x, y)); dr.text((x + 6, y + a.size + 4), f"{clip} frame {fr}", fill=(30, 30, 30))
    sheet.save(os.path.join(a.out, "Preview_Animations.png"))


def pose_test(R, clips, a):
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = a.size; sc.cycles.samples = a.samples
    picks = {"Crab_Idle": [30], "Crab_Scuttle_Left": [1, 5], "Crab_Threat": [20], "Crab_Attack_Snap": [8, 13],
             "Crab_Hit": [4], "Crab_Death": [12, 19, 40]}
    from PIL import Image, ImageDraw
    ims = []
    for name, params, loop in clips:
        if name not in picks: continue
        act, st = bake(R, name, params, clamp_tips=(name == "Crab_Death"))
        for fr in picks[name]:
            ims.append((name, fr, render(R, act, os.path.join(a.out, "_pose"), "death" if "Death" in name else "hero", [fr])[0]))
    cols = 5; rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGB", (cols * a.size, rows * (a.size + 20)), (240, 240, 238)); dr = ImageDraw.Draw(sheet)
    for k, (name, fr, p) in enumerate(ims):
        x, y = (k % cols) * a.size, (k // cols) * (a.size + 20)
        sheet.paste(Image.open(p).convert("RGB"), (x, y)); dr.text((x + 6, y + a.size + 4), f"{name} {fr}", fill=(30, 30, 30))
    sheet.save(os.path.join(a.out, "_pose_test.png"))


if __name__ == "__main__":
    main()
