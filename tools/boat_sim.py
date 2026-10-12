#!/usr/bin/env python3
"""Tune the boat's Blueprint physics before it goes into Unreal: a small rigid-body simulation that applies exactly
the forces the guide's BP_KaiBoat applies each tick, with Unreal's units (cm, kg, s) and Chaos-style damping.

    python3 tools/boat_sim.py [boat]            # writes boat/physics_tuning.json and boat/Preview_Boat_Physics.png

Mass properties come from the hull's own collision pieces (UCX_SM_Boat_Hull_*, uniform density, scaled to the mass
override), which is how Unreal computes them, then the guide's Center Of Mass Offset moves the centre of mass aft
and down to where the outboard and driver put it. The forces, per tick:
  buoyancy   at each Pontoon_* socket under water: up = Stiffness x depth (depth capped) - Damping x point's vertical speed
  thrust     at the Propeller socket when it is under water, along the motor's forward axis (half in reverse)
  water drag forward, at the centre of mass: -(DragLinear x v + DragQuadratic x v|v|)
             sideways, at two keel points KeelSpacing ahead of and behind the centre of mass: -SideDrag/2 x sideways
             speed of that point (this also steadies the yaw); all drag is scaled by the fraction of pontoons in water
  damping    Unreal's Linear/Angular Damping: v *= max(0, 1 - damping x dt)
The script checks the boat settles at its design waterline, its top speed, acceleration, turning circle, heel in
turns and coasting, at 30, 60 and 120 frames per second.
"""
import json, math, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boat_geometry as B

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
D = os.path.abspath(argv[0] if argv and not argv[0].startswith("--") else "boat")
G = 980.0

# Blueprint defaults (the guide's tuning table)
P = dict(
    mass_kg=150.0,            # Hull > Physics > Mass (kg) override: boat, motor and Kai
    linear_damping=0.05,      # Hull > Physics > Linear Damping
    angular_damping=1.2,      # Hull > Physics > Angular Damping
    buoy_stiffness=None,      # per pontoon, kg/s^2 (computed below so the boat floats at its design waterline)
    buoy_damping=None,        # per pontoon, kg/s (computed below for a slightly underdamped bob)
    buoy_max_depth=40.0,      # cm: deeper than this a pontoon pushes no harder
    com_offset_cm=None,       # Hull > Physics > Center Of Mass Offset (computed below: auto centre of mass -> DESIGN_COM)
    thrust=67000.0,           # kg cm/s^2 at full throttle
    reverse_scale=0.35,
    drag_linear=60.0,         # kg/s: forward water drag, linear part (lets the boat glide to a stop)
    drag_quadratic=0.03,      # kg/cm: forward water drag, quadratic part (with the linear part, sets the top speed)
    side_drag=1500.0,         # kg/s: sideways water drag, shared by the two keel points
    keel_spacing=40.0,        # cm: keel points ahead of and behind the centre of mass
    steer_assist=0.0,         # kg cm^2/s^2 per unit steer at speed (an arcade yaw torque; physical thrust steering is enough)
    throttle_rate=2.5,        # FInterpTo speeds for the inputs
    steer_rate=4.0,
)
HEAVE_ZETA = 0.45


def ucx_mass_properties(path):
    """Volume, centroid and inertia (density 1) of the hull's convex collision pieces in Boat.blend."""
    import bpy
    bpy.ops.wm.open_mainfile(filepath=path)
    vol, first, second = 0.0, np.zeros(3), np.zeros((3, 3))
    canon = np.array([[2, 1, 1], [1, 2, 1], [1, 1, 2]]) / 120.0
    for o in bpy.data.objects:
        if not o.name.startswith("UCX_SM_Boat_Hull_"): continue
        M = np.array(o.matrix_world)
        V = np.array([v.co[:] for v in o.data.vertices]) @ M[:3, :3].T + M[:3, 3]
        o.data.calc_loop_triangles()
        for t in o.data.loop_triangles:
            A = V[list(t.vertices)].T                     # columns a, b, c (tetrahedron with the origin)
            d = np.linalg.det(A)
            vol += d / 6.0
            first += d / 24.0 * A.sum(1)
            second += d * A @ canon @ A.T
    c = first / vol
    C = second - vol * np.outer(c, c)                     # covariance about the centroid
    I = np.trace(C) * np.eye(3) - C
    return vol, c, I


def quat_mul(a, b):
    w1, x1, y1, z1 = a; w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def quat_mat(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


class Boat:
    def __init__(self, P, com, I_unit, vol, pontoons, prop):
        self.P = P; self.m = P["mass_kg"]
        self.com = com                                   # boat frame
        self.I = I_unit * (self.m / vol)                 # body inertia about the COM
        self.Iinv = np.linalg.inv(self.I)
        self.pont = pontoons - com                       # relative to the COM
        self.prop = prop - com
        self.reset()

    def reset(self, z=0.0, roll=0.0, pitch=0.0):
        self.x = np.array([0.0, 0.0, 0.0]) + self.com + np.array([0, 0, z])   # COM position (water at 0)
        self.q = quat_mul(np.array([math.cos(math.radians(roll) / 2), math.sin(math.radians(roll) / 2), 0, 0]),
                          np.array([math.cos(math.radians(pitch) / 2), 0, math.sin(math.radians(pitch) / 2), 0]))
        self.v = np.zeros(3); self.w = np.zeros(3)
        self.throttle = 0.0; self.steer = 0.0; self.t = 0.0

    def origin(self):
        """World position of the hull's origin (keel bottom amidships)."""
        return self.x - quat_mat(self.q) @ self.com

    def water(self, p):
        return WAVE["amp"] * math.sin(2 * math.pi * (p[0] / WAVE["length"] - self.t / WAVE["period"])) if WAVE["amp"] else 0.0

    def step(self, dt, throttle_in, steer_in):
        P = self.P
        self.throttle += (throttle_in - self.throttle) * min(1.0, P["throttle_rate"] * dt)
        self.steer += (steer_in - self.steer) * min(1.0, P["steer_rate"] * dt)
        R = quat_mat(self.q)
        F = np.array([0.0, 0.0, -G * self.m]); T = np.zeros(3)
        wet = 0.0
        for r in self.pont:
            pw = self.x + R @ r
            depth = self.water(pw) - pw[2]
            if depth <= 0: continue
            wet += 1
            vp = self.v + np.cross(self.w, R @ r)
            f = P["buoy_stiffness"] * min(depth, P["buoy_max_depth"]) - P["buoy_damping"] * vp[2]
            f = np.array([0, 0, max(f, 0.0)])
            F += f; T += np.cross(R @ r, f)
        wet /= len(self.pont)
        pw = self.x + R @ self.prop
        if self.water(pw) > pw[2]:
            yaw = math.radians(B.STEER_MAX * self.steer)          # + = steer right (Blender: motor turns anticlockwise)
            fwd = R @ np.array([math.cos(yaw), math.sin(yaw), 0.0])
            thr = self.throttle * (1.0 if self.throttle >= 0 else P["reverse_scale"])
            f = fwd * P["thrust"] * thr
            F += f; T += np.cross(R @ self.prop, f)
        vl = R.T @ self.v
        F += R @ np.array([-(P["drag_linear"] * vl[0] + P["drag_quadratic"] * vl[0] * abs(vl[0])), 0.0, 0.0]) * wet
        side = R @ np.array([0, 1.0, 0])
        for sgn in (1.0, -1.0):
            r = R @ np.array([sgn * P["keel_spacing"], 0, 0])
            vp = self.v + np.cross(self.w, r)
            f = -0.5 * P["side_drag"] * (vp @ side) * side * wet
            F += f; T += np.cross(r, f)
        T += R @ np.array([0, 0, P["steer_assist"] * self.steer * float(np.clip(vl[0] / 300.0, -1, 1))])
        # integrate (semi-implicit Euler), then Chaos-style damping
        self.v += F / self.m * dt
        Iw = R @ self.I @ R.T
        self.w += np.linalg.solve(Iw, T - np.cross(self.w, Iw @ self.w)) * dt
        self.v *= max(0.0, 1 - P["linear_damping"] * dt)
        self.w *= max(0.0, 1 - P["angular_damping"] * dt)
        self.x += self.v * dt
        dq = np.concatenate([[0.0], self.w]) * 0.5 * dt
        self.q = self.q + quat_mul(dq, self.q); self.q /= np.linalg.norm(self.q)
        self.t += dt

    def euler(self):
        R = quat_mat(self.q)
        pitch = math.degrees(math.asin(max(-1, min(1, -R[2, 0]))))
        roll = math.degrees(math.atan2(R[2, 1], R[2, 2]))
        yaw = math.degrees(math.atan2(R[1, 0], R[0, 0]))
        return roll, pitch, yaw


WAVE = dict(amp=0.0, length=600.0, period=2.4)


def run(boat, dt, seconds, throttle=0.0, steer=0.0, log=None):
    n = int(round(seconds / dt))
    for i in range(n):
        th = throttle(boat.t) if callable(throttle) else throttle
        st = steer(boat.t) if callable(steer) else steer
        boat.step(dt, th, st)
        if log is not None: log.append((boat.t, boat.origin().copy(), boat.v.copy(), boat.w.copy(), boat.euler(), boat.throttle, boat.steer))
    return boat


def scenarios(boat, dt):
    out = {}
    # 1. drop from 10 cm above the water: settle at the design waterline
    boat.reset(z=10.0); L = []; run(boat, dt, 6.0, log=L)
    draft = -L[-1][1][2]
    out["waterline_cm"] = round(draft, 2)
    roll, pitch, _ = L[-1][4]
    out["rest_pitch_deg"] = round(pitch, 2); out["rest_roll_deg"] = round(roll, 2)
    settle = next((t for t, o, v, w, e, *_ in L if all(abs(-oo[1][2] - draft) < 0.5 and abs(oo[2][2]) < 2 for oo in L if oo[0] >= t)), None)
    out["settle_s"] = round(settle, 2) if settle is not None else None
    out["drop_overshoot_cm"] = round(max(0.0, max(-o[2] for t, o, *_ in L) - draft), 2)
    # 2. full throttle straight ahead
    boat.reset(z=-draft); L = []; run(boat, dt, 12.0, throttle=1.0, log=L)
    sp = np.array([np.linalg.norm(v[:2]) for t, o, v, *_ in L])
    out["top_speed_cm_s"] = round(float(sp[-1]), 1)
    out["to_90pct_s"] = round(float(L[int(np.argmax(sp > 0.9 * sp[-1]))][0]), 2)
    out["squat_pitch_deg"] = round(float(L[-1][4][1]), 2)
    out["running_waterline_cm"] = round(float(-L[-1][1][2]), 2)
    # 3. full right at full speed: turning circle, yaw rate, heel
    L = []; run(boat, dt, 8.0, throttle=1.0, steer=1.0, log=L)
    tail = L[len(L) // 2:]
    yaw_rate = np.mean([w[2] for t, o, v, w, *_ in tail])
    speed = np.mean([np.linalg.norm(v[:2]) for t, o, v, *_ in tail])
    out["turn_yaw_rate_deg_s"] = round(math.degrees(yaw_rate), 1)
    out["turn_radius_cm"] = round(float(speed / max(abs(yaw_rate), 1e-6)), 0)
    out["turn_speed_cm_s"] = round(float(speed), 1)
    out["turn_heel_deg"] = round(max(abs(e[0]) for t, o, v, w, e, *_ in L), 2)
    out["turns_right"] = bool(yaw_rate < 0)            # Blender/boat frame: clockwise from above is negative yaw
    # 4. let go at full speed: coast down to walking pace
    boat.reset(z=-draft); run(boat, dt, 10.0, throttle=1.0)
    L = []; run(boat, dt, 15.0, throttle=0.0, log=L)
    sp = [np.linalg.norm(v[:2]) for t, o, v, *_ in L]
    slow = np.flatnonzero(np.array(sp) < 50.0)
    out["coast_to_50_s"] = round(float(L[slow[0]][0] - L[0][0] + dt), 2) if len(slow) else None
    # 5. reverse
    boat.reset(z=-draft); L = []; run(boat, dt, 10.0, throttle=-1.0, log=L)
    out["reverse_speed_cm_s"] = round(float(np.linalg.norm(L[-1][2][:2])), 1)
    # 6. righting: let go at 20 degrees of heel
    boat.reset(z=-draft, roll=20.0); L = []; run(boat, dt, 5.0, log=L)
    out["righting_roll_after_2s_deg"] = round(abs(L[int(2.0 / dt)][4][0]), 2)
    # 7. gentle swell: how much it bobs and rocks at rest
    WAVE["amp"] = 4.0
    boat.reset(z=-draft); L = []; run(boat, dt, 10.0, log=L)
    WAVE["amp"] = 0.0
    zs = [o[2] for t, o, *_ in L[len(L) // 2:]]; ps = [e[1] for t, o, v, w, e, *_ in L[len(L) // 2:]]
    out["swell_bob_cm"] = round(float(max(zs) - min(zs)), 2)
    out["swell_pitch_deg"] = round(float(max(ps) - min(ps)), 2)
    return out


def main():
    vol, com_auto, I_unit = ucx_mass_properties(os.path.join(D, "Boat.blend"))
    com = B.DESIGN_COM.copy()
    P["com_offset_cm"] = np.round(com - com_auto, 1).tolist()
    pont = np.array([loc for n, (loc, f, u) in B.sockets().items() if n.startswith("Pontoon_")])
    prop = B.PROP_C
    m = P["mass_kg"]
    # stiffness: at rest every pontoon is as deep as the design waterline above its socket
    depth0 = B.WATERLINE - pont[:, 2]
    P["buoy_stiffness"] = round(m * G / float(np.clip(depth0, 0, None).sum()), 0)
    k_tot = P["buoy_stiffness"] * (depth0 > 0).sum()
    P["buoy_damping"] = round(2 * HEAVE_ZETA * math.sqrt(k_tot * m) / (depth0 > 0).sum(), 0)
    boat = Boat(P, com, I_unit, vol, pont, prop)
    res = {}
    for hz in (30, 60, 120):
        res[f"{hz}fps"] = scenarios(boat, 1.0 / hz)
        print(hz, json.dumps(res[f"{hz}fps"]), flush=True)
    r60 = res["60fps"]
    problems = []
    for hz, r in res.items():
        if abs(r["waterline_cm"] - B.WATERLINE) > 1.0: problems.append(f"{hz}: floats at {r['waterline_cm']} cm, not {B.WATERLINE}")
        if abs(r["rest_pitch_deg"]) > 2.0: problems.append(f"{hz}: rests {r['rest_pitch_deg']} degrees nose up/down")
        if r["settle_s"] is None or r["settle_s"] > 3.0: problems.append(f"{hz}: bobs too long after landing ({r['settle_s']} s)")
        if not r["turns_right"]: problems.append(f"{hz}: steering right does not turn right")
        if r["turn_heel_deg"] > 15: problems.append(f"{hz}: heels {r['turn_heel_deg']} degrees in a full turn")
        if abs(r["top_speed_cm_s"] - r60["top_speed_cm_s"]) > 0.03 * r60["top_speed_cm_s"]:
            problems.append(f"{hz}: top speed differs from 60 fps ({r['top_speed_cm_s']})")
        if r["righting_roll_after_2s_deg"] > 3: problems.append(f"{hz}: slow to come upright")
        if r["coast_to_50_s"] is None or r["coast_to_50_s"] > 8: problems.append(f"{hz}: coasts too long ({r['coast_to_50_s']} s)")
        if not 35 <= abs(r["turn_yaw_rate_deg_s"]) <= 75: problems.append(f"{hz}: turns at {r['turn_yaw_rate_deg_s']} deg/s")
    doc = dict(ok=not problems, problems=problems, blueprint=P, design_waterline_cm=B.WATERLINE,
               mass_properties=dict(auto_centre_of_mass_cm=np.round(com_auto, 2).tolist(), centre_of_mass_cm=com.tolist(),
                                    inertia_kg_cm2=np.round(np.diag(I_unit * m / vol), 0).tolist()),
               pontoons={n: np.round(loc, 2).tolist() for n, (loc, f, u) in B.sockets().items() if n.startswith("Pontoon_")},
               results=res)
    json.dump(doc, open(os.path.join(D, "physics_tuning.json"), "w"), indent=1)
    plot(boat, com, os.path.join(D, "Preview_Boat_Physics.png"))
    print("\n".join(problems) if problems else "", "SIM_OK" if not problems else f"SIM_FAIL {len(problems)}")
    sys.exit(1 if problems else 0)


def plot(boat, com, path):
    """Top-down tracks of a figure-of-eight test drive, and speed / heel over time."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    dt = 1 / 60
    boat.reset(z=-B.WATERLINE)
    steer = lambda t: 0.0 if t < 4 else (1.0 if t < 10 else (-1.0 if t < 16 else 0.0))
    throttle = lambda t: 1.0 if t < 20 else 0.0
    L = []; run(boat, dt, 26.0, throttle=throttle, steer=steer, log=L)
    t = np.array([l[0] for l in L]); xy = np.array([l[1][:2] for l in L]) / 100.0
    sp = np.array([np.linalg.norm(l[2][:2]) for l in L]) / 100.0
    heel = np.array([l[4][0] for l in L]); pitch = np.array([l[4][1] for l in L])
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw=dict(width_ratios=[1.1, 1]))
    ax[0].plot(xy[:, 0], xy[:, 1], color="#2b4c8c", lw=2)
    ax[0].set_aspect("equal"); ax[0].set_xlabel("x (m)"); ax[0].set_ylabel("y (m)")
    ax[0].set_title("Test drive from above\n4 s straight, 6 s full right, 6 s full left, coast", fontsize=10)
    ax[0].grid(alpha=0.3)
    ax[1].plot(t, sp, label="speed (m/s)", color="#c0392b", lw=2)
    ax[1].plot(t, heel, label="heel (deg)", color="#2b4c8c")
    ax[1].plot(t, pitch, label="pitch (deg)", color="#888")
    ax[1].set_xlabel("time (s)"); ax[1].legend(); ax[1].grid(alpha=0.3); ax[1].set_title("Speed, heel and pitch")
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


if __name__ == "__main__":
    main()
