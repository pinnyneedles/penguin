#!/usr/bin/env python3
"""Author the Pebble Chick animation set for Unreal Engine and export one FBX per clip.

    python3 tools/make_chick_anims.py --blend pebble/Pebble_Chick/Pebble_Chick.blend --out pebble/Pebble_Chick
        [--no-render] [--size 400] [--samples 12] [--pose-test]

Clips (30 fps, in place unless noted; looping clips repeat frame 1 as their last frame):
    Chick_Idle                 91 f  loop   breathing, weight shift, glance, feet planted
    Chick_Waddle               33 f  loop   walk cycle, planted feet locked to a constant ground speed
    Chick_Waddle_RootMotion    33 f  loop   same, with the root bone carrying the forward motion
    Chick_Jump_Start           10 f         crouch and launch
    Chick_Jump_Loop            25 f  loop   in the air (rising or falling)
    Chick_Jump_Land            18 f         impact, squash and settle to rest
    Chick_BellySlide_Start     24 f         crouch, lunge and flop onto the belly
    Chick_BellySlide_Loop      33 f  loop   tobogganing: feet kick, flippers paddle, body rocks
    Chick_BellySlide_End       28 f         push up with the flippers and stand

Every non-looping clip starts or ends on the rest pose (Idle frame 1) or on the first frame of
its loop, so a state machine can chain them. The armature object is exported as "Armature" so
Unreal does not add an extra root bone above "root".
"""
import argparse, json, math, os, sys
import bpy
import numpy as np
from mathutils import Vector, Matrix, Quaternion
from scipy.interpolate import PchipInterpolator

FPS = 30
FWD = Vector((0, -1, 0)); UP = Vector((0, 0, 1)); RIGHT = Vector((1, 0, 0))
SIDES = (("L", 1), ("R", -1))
TAU = 2 * math.pi


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", default="pebble/Pebble_Chick/Pebble_Chick.blend")
    ap.add_argument("--out", default="pebble/Pebble_Chick")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--pose-test", action="store_true", help="only render a few key poses")
    ap.add_argument("--size", type=int, default=400)
    ap.add_argument("--samples", type=int, default=12)
    return ap.parse_args(argv)


# ---------------------------------------------------------------------------
# Rig access: rest-frame rotations, stretchy-leg IK, mesh evaluation
# ---------------------------------------------------------------------------
class Rig:
    def __init__(self, rig, mesh):
        self.rig, self.mesh = rig, mesh
        assert all(abs(rig.matrix_world[i][j] - (1 if i == j else 0)) < 1e-6 for i in range(4) for j in range(4))
        self.rest = {b.name: b.matrix_local.copy() for b in rig.data.bones}
        self.rest3 = {k: m.to_3x3() for k, m in self.rest.items()}
        for p in rig.pose.bones:
            p.rotation_mode = "QUATERNION"
        self.acc = {}
        gi = {g.index: g.name for g in mesh.vertex_groups}
        feet, flip = [], []
        for v in mesh.data.vertices:
            names = [gi[g.group] for g in v.groups if g.weight > 1e-4]
            feet.append(any(n.startswith(("leg.", "foot.", "toe.")) for n in names))
            flip.append(any(n.startswith("flipper") for n in names))
        self.m_feet = np.array(feet); self.m_flip = np.array(flip)
        self.m_foot = {}
        for L, _ in SIDES:
            self.m_foot[L] = np.array([any(gi[g.group] in ("leg." + L, "foot." + L, "toe." + L) and g.weight > 1e-4 for g in v.groups)
                                       for v in mesh.data.vertices])
        self.m_body = ~self.m_feet & ~self.m_flip
        self.rest_ankle = {L: self.rest["foot." + L].translation.copy() for L, _ in SIDES}

    def update(self):
        bpy.context.view_layer.update()

    def reset(self):
        self.acc = {}
        for p in self.rig.pose.bones:
            p.location = (0, 0, 0); p.rotation_quaternion = (1, 0, 0, 0); p.scale = (1, 1, 1)

    def local_rot(self, bone, axis, angle):
        R = self.rest3[bone]
        return R.transposed() @ Matrix.Rotation(angle, 3, Vector(axis).normalized()) @ R

    def rot(self, bone, axis, angle):
        """Rotate about an armature-space axis taken in the parent's frame. Calls compose so that
        the LAST call is applied first: call yaw, roll, then pitch to pitch first."""
        if abs(angle) < 1e-9:
            return
        m = self.acc.get(bone, Matrix.Identity(3)) @ self.local_rot(bone, axis, angle)
        self.acc[bone] = m
        self.rig.pose.bones[bone].rotation_quaternion = m.to_quaternion()

    def move(self, bone, vec):
        p = self.rig.pose.bones[bone]
        p.location = p.location + self.rest3[bone].transposed() @ Vector(vec)

    def ik_leg(self, L, ankle):
        """Aim the leg at the ankle target and slide it along its axis to reach it exactly."""
        self.update()
        pel = self.rig.pose.bones["pelvis"].matrix
        base = pel @ (self.rest["pelvis"].inverted() @ self.rest["leg." + L])
        a = base.inverted() @ Vector(ankle)
        l = self.rig.data.bones["leg." + L].length
        d = a.normalized()
        return Vector((0, 1, 0)).rotation_difference(d), d * (a.length - l)

    def ik_foot(self, L, foot3):
        self.update()
        legm = self.rig.pose.bones["leg." + L].matrix
        basef = legm @ (self.rest["leg." + L].inverted() @ self.rest["foot." + L])
        return (basef.to_3x3().inverted() @ foot3).to_quaternion()

    def verts(self):
        self.update()
        dg = bpy.context.evaluated_depsgraph_get()
        ev = self.mesh.evaluated_get(dg); me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co); ev.to_mesh_clear()
        co = co.reshape(-1, 3); M = np.array(self.mesh.matrix_world)
        return co @ M[:3, :3].T + M[:3, 3]

    def bone_head(self, name):
        self.update(); return self.rig.pose.bones[name].head.copy()


def side_val(prm, key, L, default=0.0):
    return prm.get(f"{key}_{L}", prm.get(key, default))


def apply(R, prm):
    """Pose the rig from a parameter dict (angles in radians, offsets in cm, armature space)."""
    R.reset()
    g = lambda k, d=0.0: prm.get(k, d)
    R.move("pelvis", Vector(prm.get("pel_off", (0, 0, 0))))
    R.rot("pelvis", UP, g("pel_yaw")); R.rot("pelvis", FWD, g("pel_roll")); R.rot("pelvis", RIGHT, g("pel_pitch"))
    R.rot("body", UP, g("body_yaw")); R.rot("body", FWD, g("body_roll")); R.rot("body", RIGHT, g("body_pitch"))
    R.rot("head", UP, g("head_yaw")); R.rot("head", FWD, g("head_roll")); R.rot("head", RIGHT, g("head_pitch"))
    R.rot("tail", UP, g("tail_yaw")); R.rot("tail", RIGHT, g("tail_pitch"))
    for L, s in SIDES:
        R.rot("flipper." + L, UP, s * side_val(prm, "flip_twist", L))
        R.rot("flipper." + L, RIGHT, side_val(prm, "flip_swing", L))          # + swings the flipper back
        R.rot("flipper." + L, FWD, s * side_val(prm, "flip_out", L))          # + lifts it away from the body
        R.rot("flipper_tip." + L, RIGHT, side_val(prm, "flip_tip", L))
    w = g("ik_w")
    for L, s in SIDES:
        fk_leg = (R.local_rot("leg." + L, FWD, s * side_val(prm, "leg_out", L))
                  @ R.local_rot("leg." + L, RIGHT, side_val(prm, "leg_pitch", L))).to_quaternion()
        leg_q, leg_loc = fk_leg, Vector((0, 0, 0))
        if w > 1e-6:
            ankle = Vector(prm.get("ankle_" + L, tuple(R.rest_ankle[L])))
            iq, iloc = R.ik_leg(L, ankle)
            leg_q, leg_loc = fk_leg.slerp(iq, w), iloc * w
        pl = R.rig.pose.bones["leg." + L]; pl.rotation_quaternion = leg_q; pl.location = leg_loc
        fk_foot = R.local_rot("foot." + L, RIGHT, side_val(prm, "foot_pitch", L)).to_quaternion()
        foot_q = fk_foot
        if w > 1e-6:
            yaw = s * side_val(prm, "toe_out", L, 0.0)
            pitch = side_val(prm, "ik_foot_pitch", L, 0.0)
            want = Matrix.Rotation(yaw, 3, UP) @ Matrix.Rotation(pitch, 3, RIGHT) @ R.rest3["foot." + L]
            foot_q = fk_foot.slerp(R.ik_foot(L, want), w)
        R.rig.pose.bones["foot." + L].rotation_quaternion = foot_q
        R.rig.pose.bones["toe." + L].rotation_quaternion = R.local_rot("toe." + L, RIGHT, side_val(prm, "toe_pitch", L)).to_quaternion()
    if "root_off" in prm:
        R.move("root", Vector(prm["root_off"]))


def _shift_feet(R, prm, dz, sides=("L", "R")):
    for L in sides:
        a = list(prm.get("ankle_" + L, tuple(R.rest_ankle[L]))); a[2] += dz; prm["ankle_" + L] = tuple(a)


def solve(R, prm):
    """Apply and enforce ground contact. mode: 'feet' (IK feet, nothing else below ground),
    'belly' (lowest non-foot point exactly on the ground), 'free' (only prevent penetration).
    'feet_ground' (cm) moves the IK foot targets so the lowest foot point sits at that height."""
    prm = dict(prm)
    apply(R, prm)
    mode = prm.get("mode", "feet")
    V = R.verts()
    if mode == "belly":
        dz = prm.get("contact", 0.0) - V[~R.m_feet, 2].min()
        off = list(prm.get("pel_off", (0, 0, 0))); off[2] += dz; prm["pel_off"] = tuple(off)
        apply(R, prm); V = R.verts()
    if prm.get("feet_ground") is not None and prm.get("ik_w", 0) > 0.999:
        _shift_feet(R, prm, prm["feet_ground"] - V[R.m_feet, 2].min())
        apply(R, prm); V = R.verts()
    for _ in range(4):                         # nothing may sink below the ground
        changed = False
        body_low = V[~R.m_feet, 2].min()
        if mode == "free":
            low = V[:, 2].min()                # airborne: lift the whole character
            if low < -0.05:
                off = list(prm.get("pel_off", (0, 0, 0))); off[2] -= low; prm["pel_off"] = tuple(off)
                if prm.get("ik_w", 0) > 1e-6: _shift_feet(R, prm, -low)
                changed = True
        else:
            if mode == "feet" and body_low < -0.05:      # body only: raise the pelvis, feet stay planted
                off = list(prm.get("pel_off", (0, 0, 0))); off[2] -= body_low; prm["pel_off"] = tuple(off)
                changed = True
            if prm.get("ik_w", 0) > 1e-6:
                for L, _ in SIDES:                      # a sinking foot lifts only itself
                    fl = V[R.m_foot[L], 2].min()
                    if fl < -0.05:
                        _shift_feet(R, prm, -fl, (L,)); changed = True
        if not changed:
            break
        apply(R, prm); V = R.verts()
    prm["_minz"] = float(V[:, 2].min()); prm["_minz_body"] = float(V[R.m_body, 2].min())
    prm["_minz_feet"] = float(V[R.m_feet, 2].min())
    return prm


# ---------------------------------------------------------------------------
# Parameter curves
# ---------------------------------------------------------------------------
def keyed(keys, n, defaults=None):
    """keys: list of (frame, dict). Smooth, overshoot-free (PCHIP) interpolation of every numeric
    parameter; tuples are interpolated per component; 'mode' is taken from mode_ranges."""
    defaults = defaults or {}
    flat = []
    for f, d in keys:
        e = {}
        for k, v in d.items():
            if isinstance(v, (tuple, list, Vector)):
                for i, c in enumerate(v): e[f"{k}#{i}"] = float(c)
            elif isinstance(v, (int, float)):
                e[k] = float(v)
        flat.append((f, e))
    names = sorted({k for _, e in flat for k in e})
    frames = np.array([f for f, _ in flat], float)
    out = [dict() for _ in range(n)]
    for k in names:
        base = k.split("#")[0]
        dv = defaults.get(base, 0.0)
        if "#" in k and isinstance(dv, (tuple, list, Vector)):
            dv = dv[int(k.split("#")[1])]
        ys = np.array([e.get(k, dv) for _, e in flat])
        vals = PchipInterpolator(frames, ys)(np.arange(1, n + 1))
        for i in range(n):
            out[i][k] = float(vals[i])
    res = []
    for e in out:
        d = {}
        for k, v in e.items():
            if "#" in k:
                b, i = k.split("#"); d.setdefault(b, [0.0, 0.0, 0.0])[int(i)] = v
            else:
                d[k] = v
        res.append({k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()})
    return res


def with_modes(frames, ranges):
    for (a, b), m in ranges:
        for f in range(a, b + 1):
            frames[f - 1]["mode"] = m
    return frames


def smoother(u):
    u = min(max(u, 0.0), 1.0); return u * u * u * (u * (u * 6 - 15) + 10)


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------
def idle_params(R, n=91):
    out = []
    for f in range(1, n + 1):
        ph = TAU * (f - 1) / (n - 1)
        out.append(dict(
            mode="feet", ik_w=1.0,
            pel_off=(1.4 * math.sin(ph), 0.0, 0.35 * math.sin(2 * ph)),
            pel_roll=-0.022 * math.sin(ph), pel_yaw=0.02 * math.sin(ph),
            body_pitch=-0.014 * math.sin(2 * ph), body_roll=-0.012 * math.sin(ph),
            head_yaw=0.15 * math.sin(ph) + 0.03 * math.sin(3 * ph),
            head_pitch=0.010 * math.sin(2 * ph) - 0.03 * (1 - math.cos(ph)) / 2,
            head_roll=0.035 * math.sin(ph),
            flip_out=0.03 * (1 - math.cos(2 * ph)) / 2,
            flip_swing_L=0.035 * math.sin(ph), flip_swing_R=-0.035 * math.sin(ph),
            flip_tip=0.03 * math.sin(2 * ph),
            tail_yaw=0.12 * math.sin(2 * ph)))
    return out


SPEED = 23.25        # cm/s ground speed matched by the waddle
WCYCLE = 32          # frames per two-step cycle
DUTY = 0.56          # fraction of the cycle each foot is planted (brief double support)


def waddle_params(R, root_motion=False):
    T = WCYCLE / FPS
    Ls = SPEED * DUTY * T                     # distance a planted foot travels backward
    out = []
    for f in range(1, WCYCLE + 2):
        t = (f - 1) / WCYCLE
        prm = dict(mode="feet", ik_w=1.0)
        for L, s in SIDES:
            phase = (t + (0.0 if L == "L" else 0.5)) % 1.0
            a = R.rest_ankle[L].copy()
            if phase < DUTY:                       # planted: constant backward speed
                y = -Ls / 2 + Ls * phase / DUTY; z = a.z; x = a.x; pitch = 0.0
            else:                                  # swing: lift, carry forward, toes drop
                u = (phase - DUTY) / (1 - DUTY)
                y = Ls / 2 - Ls * smoother(u)
                z = a.z + 6.0 * math.sin(math.pi * u) ** 1.2
                x = a.x + s * 1.2 * math.sin(math.pi * u)
                pitch = 0.14 * math.sin(math.pi * u) ** 2
            prm["ankle_" + L] = (x, a.y + y, z)
            prm["ik_foot_pitch_" + L] = pitch
            prm["toe_out_" + L] = 0.10
            prm["toe_pitch_" + L] = 0.12 * max(0.0, math.sin(math.pi * (phase - DUTY) / (1 - DUTY))) if phase >= DUTY else 0.0
        c = math.cos(TAU * (t - DUTY / 2))       # +1 = weight over the left foot
        sn = math.sin(TAU * (t - DUTY / 2))
        prm.update(
            pel_off=(5.0 * c, 0.0, 1.4 * math.cos(2 * TAU * (t - DUTY / 2))),
            pel_roll=-0.11 * c, pel_yaw=-0.07 * math.cos(TAU * t),
            body_roll=-0.05 * c, body_pitch=0.05 + 0.02 * math.cos(2 * TAU * t), body_yaw=0.04 * math.cos(TAU * t),
            head_roll=0.12 * c, head_pitch=0.04 * math.cos(2 * TAU * t - 0.6), head_yaw=0.03 * math.cos(TAU * t),
            tail_yaw=-0.25 * math.cos(TAU * (t - DUTY / 2) - 0.6), tail_pitch=0.06 * math.sin(2 * TAU * t),
        )
        for L, s in SIDES:
            fwd = -(prm["ankle_" + L][1] - R.rest_ankle[L].y) / (Ls / 2)      # +1 = this foot forward
            prm["flip_out_" + L] = 0.22 + 0.08 * (c * s)
            prm["flip_swing_" + L] = 0.20 * fwd
            prm["flip_tip_" + L] = 0.10 * fwd
        if root_motion:
            prm["root_off"] = tuple(FWD * (SPEED * (f - 1) / FPS))
        out.append(prm)
    return out


AIR = dict(mode="free", ik_w=0.0, leg_pitch=-0.15, foot_pitch=0.60, toe_pitch=0.25, flip_out=0.80,
           flip_swing=-0.25, flip_tip=0.15, body_pitch=-0.06, head_pitch=-0.08, tail_pitch=0.15)


def jump_loop_params(n=25):
    out = []
    for f in range(1, n + 1):
        ph = TAU * (f - 1) / (n - 1)
        p = dict(AIR)
        p.update(flip_out=0.80 + 0.25 * math.sin(2 * ph), flip_tip=0.15 + 0.20 * math.sin(2 * ph),
                 leg_pitch_L=-0.15 + 0.10 * math.sin(ph), leg_pitch_R=-0.15 - 0.10 * math.sin(ph),
                 body_pitch=-0.06 + 0.02 * math.sin(2 * ph), head_pitch=-0.08 + 0.02 * math.sin(2 * ph),
                 tail_pitch=0.15 + 0.08 * math.sin(2 * ph))
        out.append(p)
    return out


def jump_start_params(loop0):
    keys = [(1, dict(ik_w=1.0)),
            (5, dict(ik_w=1.0, pel_off=(0, 0, -6), body_pitch=0.12, head_pitch=-0.08, flip_out=0.15, flip_swing=0.35)),
            (8, dict(ik_w=1.0, pel_off=(0, 0, 3), body_pitch=-0.05, head_pitch=-0.06, flip_out=0.55, flip_swing=-0.15)),
            (10, {k: v for k, v in loop0.items() if k != "mode"})]
    fr = keyed(keys, 10)
    return with_modes(fr, [((1, 8), "feet"), ((9, 10), "free")])


def jump_land_params(loop0):
    keys = [(1, {k: v for k, v in loop0.items() if k != "mode"}),
            (3, dict(ik_w=1.0, pel_off=(0, 0, -2), flip_out=0.60, flip_swing=-0.10)),
            (6, dict(ik_w=1.0, pel_off=(0, 0, -6), body_pitch=0.16, head_pitch=-0.12, flip_out=0.35, flip_swing=0.30)),
            (11, dict(ik_w=1.0, pel_off=(0, 0, 1.5), body_pitch=-0.03, head_pitch=0.02, flip_out=0.10, flip_swing=-0.05)),
            (15, dict(ik_w=1.0, pel_off=(0, 0, -0.4))),
            (18, dict(ik_w=1.0))]
    fr = keyed(keys, 18)
    return with_modes(fr, [((1, 2), "free"), ((3, 18), "feet")])


LIE = dict(mode="belly", ik_w=0.0, pel_pitch=1.70, body_pitch=-0.62, head_pitch=-0.75,
           flip_out=0.60, flip_swing=0.10, flip_tip=0.10, leg_pitch=0.30, foot_pitch=1.60,
           toe_pitch=0.20, tail_pitch=-0.20)
FOOT_LIE_PITCH = 2.55        # toes point back, soles up, claws on the ice


def lie_setup(R):
    """Pelvis offset that centres the lying body over the root and rests the belly on the ground,
    plus ankle targets just behind the rear of the body for the trailing feet."""
    prm = dict(LIE, pel_off=(0, 0, 0))
    for _ in range(3):
        prm = solve(R, prm)
        V = R.verts()
        my = float(V[R.m_body, 1].mean())
        off = list(prm["pel_off"]); off[1] -= my; prm["pel_off"] = tuple(off)
    prm = solve(R, prm)
    V = R.verts()
    rear = float(np.percentile(V[R.m_body, 1], 99.5))
    ankles = {L: (s * 20.0, rear - 9.0, 6.0) for L, s in SIDES}
    return prm["pel_off"], ankles


def lie_params(lie_off, ankles):
    p = dict(LIE, pel_off=lie_off, ik_w=1.0, feet_ground=0.4)
    for L, _ in SIDES:
        p["ankle_" + L] = ankles[L]; p["ik_foot_pitch_" + L] = FOOT_LIE_PITCH
    return p


def slide_loop_params(lie_off, ankles, n=33):
    out = []
    base = lie_params(lie_off, ankles)
    for f in range(1, n + 1):
        ph = TAU * (f - 1) / (n - 1)
        p = dict(base)
        for L, s in SIDES:                     # alternate kicks: lift and push back
            k = math.sin(ph + (0 if L == "L" else math.pi))
            a = ankles[L]
            p["ankle_" + L] = (a[0], a[1] + 5.0 * k, a[2] + 4.5 * max(0.0, k) ** 1.5)
            p["ik_foot_pitch_" + L] = FOOT_LIE_PITCH - 0.25 * k
        p.update(flip_out=0.60 + 0.12 * math.sin(2 * ph), flip_swing=0.10 + 0.10 * math.sin(2 * ph - 0.9),
                 flip_tip=0.10 + 0.10 * math.sin(2 * ph - 1.4),
                 pel_roll=0.05 * math.sin(ph), head_pitch=-0.75 + 0.03 * math.sin(2 * ph),
                 tail_yaw=0.20 * math.sin(2 * ph))
        out.append(p)
    return out


def strip(d):
    return {k: v for k, v in d.items() if k != "mode" and not k.startswith("_")}


def slide_start_params(R, loop0, lie_off):
    lo = Vector(lie_off)
    lie = strip(loop0)
    dflt = {"ankle_" + L: tuple(R.rest_ankle[L]) for L, _ in SIDES}
    keys = [(1, dict(ik_w=1.0)),
            (6, dict(ik_w=1.0, pel_off=(0, -2, -5.5), pel_pitch=0.28, body_pitch=0.12, head_pitch=-0.10, flip_swing=0.35, flip_out=0.18)),
            (10, dict(ik_w=1.0, pel_off=(0, -8, -3), pel_pitch=0.75, body_pitch=0.05, head_pitch=-0.35, flip_swing=0.55, flip_out=0.30)),
            (13, dict(ik_w=0.0, pel_off=tuple(Vector((0, -8, -3)).lerp(lo, 0.55)), pel_pitch=1.20, body_pitch=-0.30,
                      head_pitch=-0.55, flip_out=0.45, flip_swing=0.30, leg_pitch=0.35, foot_pitch=1.0)),
            (15, dict(ik_w=0.0, pel_off=tuple(lo), pel_pitch=1.55, body_pitch=-0.45, head_pitch=-0.62, flip_out=0.55,
                      leg_pitch=0.30, foot_pitch=1.6, **{k: v for k, v in lie.items() if k.startswith(("ankle_", "ik_foot_pitch_"))})),
            (17, dict(lie, body_pitch=-0.45, head_pitch=-0.62)),            # belly contact, head stays up
            (20, dict(lie, body_pitch=-0.60, head_pitch=-0.80, flip_out=0.68)),
            (24, lie)]
    fr = keyed(keys, 24, dflt)
    for f in fr:
        f["feet_ground"] = 0.4 if f.get("ik_w", 0) > 0.999 and f.get("pel_pitch", 0) > 1.0 else None
    return with_modes(fr, [((1, 11), "feet"), ((12, 15), "free"), ((16, 24), "belly")])


def slide_end_params(R, loop0, lie_off):
    lo = Vector(lie_off)
    lie = strip(loop0)
    dflt = {"ankle_" + L: tuple(R.rest_ankle[L]) for L, _ in SIDES}
    lie_feet = {k: v for k, v in lie.items() if k.startswith(("ankle_", "ik_foot_pitch_"))}
    keys = [(1, lie),
            (5, dict(lie, flip_swing=-0.75, flip_out=0.35, body_pitch=-0.70, head_pitch=-0.65, pel_pitch=1.50)),
            (8, dict(ik_w=0.0, pel_off=tuple(lo), pel_pitch=1.30, body_pitch=-0.55, head_pitch=-0.45, flip_swing=-0.95,
                     flip_out=0.30, leg_pitch=0.0, foot_pitch=1.2, **lie_feet)),
            (11, dict(ik_w=0.0, pel_off=tuple(lo.lerp(Vector((0, -4, -6)), 0.5)), pel_pitch=0.95, body_pitch=-0.35,
                      head_pitch=-0.30, flip_swing=-0.80, flip_out=0.25, leg_pitch=-0.70, foot_pitch=0.30)),
            (13, dict(ik_w=0.6, pel_off=(0, -4, -6), pel_pitch=0.55, body_pitch=-0.10, head_pitch=-0.15,
                      flip_swing=-0.30, flip_out=0.25, leg_pitch=-0.45)),
            (15, dict(ik_w=1.0, pel_off=(0, -2, -5.5), pel_pitch=0.30, body_pitch=0.05, head_pitch=-0.05, flip_swing=0.10, flip_out=0.30)),
            (21, dict(ik_w=1.0, pel_off=(0, 0, 1.2), pel_pitch=-0.03, body_pitch=-0.04, head_pitch=0.02, flip_out=0.12)),
            (28, dict(ik_w=1.0))]
    fr = keyed(keys, 28, dflt)
    for i, f in enumerate(fr, start=1):
        f["feet_ground"] = 0.4 if i <= 5 else None
    return with_modes(fr, [((1, 7), "belly"), ((8, 14), "free"), ((15, 28), "feet")])


# ---------------------------------------------------------------------------
# Bake, export, render
# ---------------------------------------------------------------------------
def bake(R, name, params):
    rig = R.rig
    act = bpy.data.actions.new(name); act.use_fake_user = True
    rig.animation_data_create(); rig.animation_data.action = act
    if hasattr(act, "slots") and hasattr(rig.animation_data, "action_slot"):
        if not act.slots:
            act.slots.new(id_type="OBJECT", name=rig.name)
        rig.animation_data.action_slot = act.slots[0]
    prev = {}
    solved = []
    for f, prm in enumerate(params, start=1):
        s = solve(R, prm); solved.append(s)
        for p in rig.pose.bones:
            q = p.rotation_quaternion.copy()
            if p.name in prev and q.dot(prev[p.name]) < 0:
                q.negate(); p.rotation_quaternion = q
            prev[p.name] = q
            p.keyframe_insert("location", frame=f, group=p.name)
            p.keyframe_insert("rotation_quaternion", frame=f, group=p.name)
            p.keyframe_insert("scale", frame=f, group=p.name)
    fcs = []
    if hasattr(act, "layers"):
        for layer in act.layers:
            for strip in layer.strips:
                for cb in strip.channelbags: fcs.extend(cb.fcurves)
    if not fcs and hasattr(act, "fcurves"):
        fcs = list(act.fcurves)
    for fc in fcs:
        for k in fc.keyframe_points: k.interpolation = "LINEAR"
    return act, solved


def export(R, act, path):
    sc = bpy.context.scene; rig = R.rig
    rig.animation_data.action = act
    if hasattr(act, "slots") and act.slots: rig.animation_data.action_slot = act.slots[0]
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


def setup_render(size, samples):
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = size; sc.render.resolution_percentage = 100
    sc.render.engine = "CYCLES"; sc.cycles.samples = samples; sc.cycles.use_denoising = True; sc.cycles.device = "CPU"
    sc.render.image_settings.file_format = "PNG"
    cam = sc.camera; cam.data.type = "ORTHO"
    return sc, cam


def aim(cam, loc, target, scale):
    cam.location = Vector(loc); cam.data.ortho_scale = scale
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()


VIEWS = {"stand": ((265, -470, 250), (0, 0, 92), 235), "jump": ((265, -470, 250), (0, 0, 100), 265),
         "slide": ((330, -430, 190), (0, -5, 55), 270)}


def render(R, act, out_dir, view, frames):
    sc = bpy.context.scene
    R.rig.animation_data.action = act
    if hasattr(act, "slots") and act.slots: R.rig.animation_data.action_slot = act.slots[0]
    aim(sc.camera, *VIEWS[view])
    paths = []
    os.makedirs(out_dir, exist_ok=True)
    for f in frames:
        sc.frame_set(f)
        p = os.path.join(out_dir, f"{act.name}_{f:03d}.png"); sc.render.filepath = p
        bpy.ops.render.render(write_still=True); paths.append(p)
    print("rendered", act.name, len(paths), flush=True)
    return paths


def gif(paths, path, fps):
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in paths]
    ims[0].save(path, save_all=True, append_images=ims[1:], duration=int(round(1000 / fps)), loop=0)


def main():
    a = parse()
    bpy.ops.wm.open_mainfile(filepath=a.blend)
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    mesh = next(o for o in bpy.data.objects if o.type == "MESH" and o.parent == rig)
    rig.name = "Armature"                       # Unreal drops a root node named "Armature"
    for act in list(bpy.data.actions):          # replace any earlier clips
        bpy.data.actions.remove(act)
    R = Rig(rig, mesh)

    lie_off, lie_ankles = lie_setup(R)
    print("lie offset", tuple(round(c, 2) for c in lie_off), "ankles", {k: tuple(round(c, 1) for c in v) for k, v in lie_ankles.items()}, flush=True)
    clips = {}
    clips["Chick_Idle"] = idle_params(R)
    clips["Chick_Waddle"] = waddle_params(R)
    clips["Chick_Waddle_RootMotion"] = waddle_params(R, root_motion=True)
    jl = jump_loop_params()
    clips["Chick_Jump_Start"] = jump_start_params(jl[0])
    clips["Chick_Jump_Loop"] = jl
    clips["Chick_Jump_Land"] = jump_land_params(jl[0])
    sl = slide_loop_params(lie_off, lie_ankles)
    clips["Chick_BellySlide_Start"] = slide_start_params(R, sl[0], lie_off)
    clips["Chick_BellySlide_Loop"] = sl
    clips["Chick_BellySlide_End"] = slide_end_params(R, sl[0], lie_off)
    if a.pose_test:
        clips = {k: v for k, v in clips.items() if k in ("Chick_BellySlide_Start", "Chick_BellySlide_Loop", "Chick_BellySlide_End")}

    acts, report = {}, {}
    for name, params in clips.items():
        act, solved = bake(R, name, params)
        acts[name] = act
        report[name] = dict(frames=len(params),
                            min_z=round(min(s["_minz"] for s in solved), 2),
                            min_z_body=round(min(s["_minz_body"] for s in solved), 2),
                            min_z_feet=round(min(s["_minz_feet"] for s in solved), 2))
        print("baked", name, report[name], flush=True)

    if not a.pose_test:
        for name, act in acts.items():
            export(R, act, os.path.join(a.out, f"AN_Pebble_{name}.fbx"))
        rig.animation_data.action = acts["Chick_Idle"]
        if hasattr(acts["Chick_Idle"], "slots"): rig.animation_data.action_slot = acts["Chick_Idle"].slots[0]
        bpy.context.scene.frame_set(1)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(a.out, "Pebble_Chick_Anims.blend"))
        json.dump(dict(fps=FPS, waddle_speed_cm_s=SPEED, lie_pelvis_offset_cm=list(lie_off), clips=report),
                  open(os.path.join(a.out, "anim_stats.json"), "w"), indent=2)

    if a.no_render:
        return
    sc, cam = setup_render(a.size, a.samples)
    tmp = os.path.join(a.out, "_anim_frames")
    if a.pose_test:
        from PIL import Image
        shots = [("Chick_BellySlide_Start", f) for f in (6, 10, 13, 17, 24)] + [("Chick_BellySlide_Loop", 9), ("Chick_BellySlide_End", 9), ("Chick_BellySlide_End", 15)]
        paths = [render(R, acts[c], tmp, "slide", [f])[0] for c, f in shots]
        ims = [Image.open(p).convert("RGB") for p in paths]
        w = ims[0].width; sheet = Image.new("RGB", (w * 4, w * 2))
        for i, im in enumerate(ims): sheet.paste(im, ((i % 4) * w, (i // 4) * w))
        sheet.save(os.path.join(a.out, "_pose_test.png")); return
    P = {}
    P["idle"] = render(R, acts["Chick_Idle"], tmp, "stand", list(range(1, 91, 2)))
    P["waddle"] = render(R, acts["Chick_Waddle"], tmp, "stand", list(range(1, 33)))
    P["js"] = render(R, acts["Chick_Jump_Start"], tmp, "jump", list(range(1, 11)))
    P["jl"] = render(R, acts["Chick_Jump_Loop"], tmp, "jump", list(range(1, 25)))
    P["jd"] = render(R, acts["Chick_Jump_Land"], tmp, "jump", list(range(1, 19)))
    P["ss"] = render(R, acts["Chick_BellySlide_Start"], tmp, "slide", list(range(1, 25)))
    P["sl"] = render(R, acts["Chick_BellySlide_Loop"], tmp, "slide", list(range(1, 33)))
    P["se"] = render(R, acts["Chick_BellySlide_End"], tmp, "slide", list(range(1, 29)))
    gif(P["idle"], os.path.join(a.out, "Pebble_Chick_Idle.gif"), 15)
    gif(P["waddle"], os.path.join(a.out, "Pebble_Chick_Waddle.gif"), 30)
    gif(P["js"] + P["jl"] + P["jd"], os.path.join(a.out, "Pebble_Chick_Jump.gif"), 30)
    gif(P["ss"] + P["sl"] + P["sl"] + P["se"], os.path.join(a.out, "Pebble_Chick_BellySlide.gif"), 30)
    from PIL import Image
    picks = [P["idle"][0], P["waddle"][9], P["js"][4], P["jl"][0], P["jd"][5], P["ss"][9], P["sl"][8], P["se"][12]]
    ims = [Image.open(p).convert("RGB") for p in picks]; w = ims[0].width
    sheet = Image.new("RGB", (w * 4, w * 2))
    for i, im in enumerate(ims): sheet.paste(im, ((i % 4) * w, (i // 4) * w))
    sheet.save(os.path.join(a.out, "Preview_Animations.png"))
    print("RENDER_DONE", flush=True)


if __name__ == "__main__":
    main()
