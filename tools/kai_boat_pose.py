#!/usr/bin/env python3
"""Pose Kai driving his boat and export the driving poses for Unreal.

    python3 tools/kai_boat_pose.py [--kai kai] [--boat boat]

Opens kai/Kai.blend, brings in the boat from boat/Boat.blend and seats Kai at the boat's Driver_Root: on the stern
thwart, feet on the floorboards, both hands on the wheel at ten to two, leaning in a little. Five poses: full left lock,
half left, straight ahead, half right and full right (the hands go round with the rim; he leans and looks into the
turn), so a blend space between neighbours keeps the hands within a few millimetres of the rim.
For each pose it checks that Kai clears the boat and that his clothes clear each other, bakes the pose onto the
deform bones and exports it as AN_Kai_Boat_*.fbx (animation only, for SK_Kai_Skeleton). Saves boat/Kai_Boat.blend
with the boat, Kai and the five actions.
"""
import json, math, os, sys
import numpy as np
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kai_geometry as G
import boat_geometry as B

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
arg = lambda k, d: os.path.abspath(argv[argv.index(k) + 1]) if k in argv else os.path.abspath(d)
KAI, BOAT = arg("--kai", "kai"), arg("--boat", "boat")

# The pose, in cm and degrees (Kai's frame while seated: he faces the bow).
THIGH_DROP = 0.8       # thighs slope down this much toward the knees
SHIN_BACK = 2.5        # ankles this much behind the knees (feet tucked back from the console)
SOLE_LIFT = 0.1        # ankles raised this much from their standing height, so the soles sit on the floorboards
PELVIS_TILT = 11.0      # pelvis rolled back (relaxed sitting), so the hips bend less
SPINE_LEAN = 4.0       # each of spine_01..03 leans forward by this (plus a third of the tilt): keen, toward the wheel
FOOT_SPREAD = 2.0      # knees and feet this much wider than the hips
LEAN = 7.0             # the upper body leans into the turn at full lock
LOOK = 12.0            # and the head turns into it
TWIST = 12.0           # the chest turns into it too, bringing the far shoulder forward to keep that hand on the rim
GRIP_CURL = float(argv[argv.index("--curl") + 1]) if "--curl" in argv else 0.9   # how far the fingers close on the rim
STEER = {"L": -1.0, "LH": -0.5, "C": 0.0, "RH": 0.5, "R": 1.0}        # -1 full left .. 1 full right
POSE_NAMES = {"L": "AN_Kai_Boat_Steer_Left", "LH": "AN_Kai_Boat_Steer_Left_Half", "C": "AN_Kai_Boat_Drive",
              "RH": "AN_Kai_Boat_Steer_Right_Half", "R": "AN_Kai_Boat_Steer_Right"}

bpy.ops.wm.open_mainfile(filepath=os.path.join(KAI, "Kai.blend"))
sc = bpy.context.scene
rig = bpy.data.objects["Armature"]; arm = rig.data
PARTS = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("SK_Kai_")
         and o.users_collection[0].name.startswith("CHARACTER")]
for o in bpy.data.objects:
    if o.type == "MESH" and o.name.startswith("SK_Kai") and o not in PARTS:
        o.hide_set(True); o.hide_render = True

# the boat
with bpy.data.libraries.load(os.path.join(BOAT, "Boat.blend"), link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n.startswith(("SM_Boat", "SOCKET_"))]
BOATC = bpy.data.collections.new("BOAT"); sc.collection.children.link(BOATC)
for o in dst.objects: BOATC.objects.link(o)
for img in bpy.data.images:
    if img.name.startswith("T_Boat"): img.filepath = os.path.join(BOAT, img.name + ".png"); img.reload()
HULL, MOTOR = bpy.data.objects["SM_Boat_Hull"], bpy.data.objects["SM_Boat_Motor"]
WHEEL = bpy.data.objects["SM_Boat_Wheel"]
bpy.context.view_layer.update()
WHEEL_REST = WHEEL.matrix_basis.copy()
for o in dst.objects:
    if o.name.startswith("SOCKET_"): o.hide_set(True)

# Kai in the boat: root at Driver_Root, facing the bow (Kai faces -Y in his own frame)
rig.matrix_world = Matrix.Translation(Vector(B.KAI_ROOT)) @ Matrix.Rotation(math.radians(90), 4, "Z")
bpy.context.view_layer.update()
W2A = rig.matrix_world.inverted()            # boat (world) -> armature space
A2W = rig.matrix_world.copy()


def bone_rest(name):
    return arm.bones[name].matrix_local.copy()


def reset():
    for pb in rig.pose.bones: pb.matrix_basis = Matrix.Identity(4)
    for pb in rig.pose.bones:
        for c in pb.constraints: c.mute = False
    bpy.context.view_layer.update()


def turn(name, axis, deg, pivot=None):
    """Rotate a bone about an armature-space axis through its head (or pivot), on top of its current pose."""
    pb = rig.pose.bones[name]; h = pb.head.copy() if pivot is None else Vector(pivot)
    pb.matrix = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, Vector(axis)) @ Matrix.Translation(-h) @ pb.matrix
    bpy.context.view_layer.update()


def place(name, M_arm):
    rig.pose.bones[name].matrix = M_arm
    bpy.context.view_layer.update()


def frame(y, palm):
    """Rotation whose bone Y axis is y and whose palm side (-Z) faces palm (both armature space)."""
    y = Vector(y).normalized(); z = -Vector(palm); z = (z - y * z.dot(y)).normalized(); x = y.cross(z)
    return Matrix((x, y, z)).transposed()


def hand_points(side):
    """Arms-mesh vertices of one hand (within 10 cm of the wrist) in the hand bone's frame, fingers curled."""
    reset(); curl(side, GRIP_CURL)
    hb = rig.pose.bones[G.bn("hand", side)]
    M = (A2W @ hb.matrix).inverted()
    ob = bpy.data.objects["SK_Kai_Arms"]
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
    V = np.array([(M @ (ob.matrix_world @ v.co))[:] for v in me.vertices]); ev.to_mesh_clear()
    Mk = hb.matrix.inverted()
    kn = [np.array((Mk @ rig.pose.bones[G.bn(f"{f}_01", side)].head)[:]) for f in ("index", "pinky")]
    return V[np.linalg.norm(V, axis=1) < 10.0], 0.5 * (kn[0] + kn[1])


def grip_frame(side, turn=0.0):
    """Grip point on the rim, and the hand's rotation (armature space) before the diagonal: fingers over the top of
    the rim and forward, palm toward the wheel's centre."""
    g, radial = B.wheel_grip(side, turn)
    W = W2A.to_3x3()
    return g, frame(W @ Vector(B.WHEEL_FWD + 0.35 * radial), W @ Vector(-radial))


def fist_offset(side):
    """How the rim sits in the curled hand: the handle crosses the palm a little diagonally (angle beta about the palm
    normal) at an offset from the wrist (hand frame). Both are fitted against the real rim, so the fingers wrap round
    it with as little skin pressing into it as possible, while still closing most of the way round."""
    V, mid = hand_points(side)
    g, R0 = grip_frame(side)
    R0 = np.array(A2W.to_3x3() @ R0)                                  # hand rotation in the boat frame
    Wi = np.array(WHEEL.matrix_world.inverted())
    best = (1e9, None, 0.0)
    ys, zs = np.meshgrid(np.arange(0.5, 8.0, 0.15), np.arange(-4.0, 2.0, 0.15))
    for beta in np.arange(-32.0, 33.0, 4.0):
        Rb = R0 @ np.array(Matrix.Rotation(math.radians(-beta), 3, "Z"))
        for oy, oz in zip(ys.ravel(), zs.ravel()):
            o = np.array([mid[0], oy, oz])
            P = g + (V - o) @ Rb.T                                    # boat frame
            Q = P @ Wi[:3, :3].T + Wi[:3, 3]
            r = np.hypot(Q[:, 1], Q[:, 2])
            d = np.hypot(r - B.WHEEL_R, Q[:, 0]) - B.WHEEL_RIM
            depth = -d.min()
            if depth >= best[0]: continue
            near = d < 2.2
            ang = np.arctan2(Q[near, 0], r[near] - B.WHEEL_R)
            if len(np.unique(np.floor((ang + np.pi) / (np.pi / 12)))) / 24.0 < 0.6: continue
            best = (depth, o, beta)
    FIST_CLEAR[side] = -best[0]
    return Vector(best[1]), best[2]


FIST_CLEAR = {}


THUMB = [float(v) for v in argv[argv.index("--thumb") + 1].split(",")] if "--thumb" in argv else [0.0, 0.0, 0.0]


def curl(side, amount, thumb=0.6):
    for fn in ("index", "middle", "ring", "pinky"):
        for j in range(1, 4):
            pb = rig.pose.bones[G.bn(f"{fn}_0{j}", side)]
            pb.rotation_quaternion = Matrix.Rotation(math.radians(-amount * (55 if j == 1 else 70)), 4, "X").to_quaternion()
    for j in range(2, 4):
        rig.pose.bones[G.bn(f"thumb_0{j}", side)].rotation_quaternion = \
            Matrix.Rotation(math.radians(-thumb * 35), 4, "X").to_quaternion()
    s = 1.0 if side == "L" else -1.0
    rig.pose.bones[G.bn("thumb_01", side)].rotation_quaternion = (
        Matrix.Rotation(math.radians(THUMB[0]), 3, "X") @ Matrix.Rotation(math.radians(THUMB[1] * s), 3, "Y")
        @ Matrix.Rotation(math.radians(THUMB[2] * s), 3, "Z")).to_quaternion()
    bpy.context.view_layer.update()


FIST = {side: fist_offset(side) for side, _ in G.SIDES}
GRIP_OFFSET = {k: v[0] for k, v in FIST.items()}
GRIP_BETA = {k: v[1] for k, v in FIST.items()}
print("fist", {k: (np.round(v[0][:], 2).tolist(), v[1], round(FIST_CLEAR[k], 2)) for k, v in FIST.items()}, flush=True)
SK = {b[0]: b for b in G.skeleton()}
HIP = np.array(SK["thigh_l"][1]); KNEE = np.array(SK["calf_l"][1]); ANKLE = np.array(SK["foot_l"][1])
THIGH, CALF = np.linalg.norm(KNEE - HIP), np.linalg.norm(ANKLE - KNEE)
HIP_UP = ANKLE[2] + SOLE_LIFT + math.sqrt(CALF ** 2 - SHIN_BACK ** 2) + THIGH_DROP     # hip joints above the floor


def to_arm(p):
    return W2A @ Vector(p)


def set_boat(amount):
    """Wheel and outboard for a steering amount (-1 full left .. 1 full right)."""
    MOTOR.rotation_euler = (0, 0, math.radians(B.STEER_MAX * amount))
    WHEEL.matrix_world = WHEEL_REST @ Matrix.Rotation(math.radians(B.WHEEL_MAX * amount), 4, "X")
    bpy.context.view_layer.update()


def pose(key):
    reset()
    amount = STEER[key]
    set_boat(amount)
    # sit: drop the pelvis so the hips are HIP_UP above the floor, and roll it back a little
    drop = HIP[2] - HIP_UP
    place("pelvis", Matrix.Translation(Vector((0, 0, -drop))) @ bone_rest("pelvis"))
    turn("pelvis", (1, 0, 0), -PELVIS_TILT, pivot=(0, HIP[1], HIP_UP))
    for n in ("spine_01", "spine_02", "spine_03"):
        turn(n, (1, 0, 0), SPINE_LEAN + PELVIS_TILT / 3.0)
    # legs: thighs nearly level, shins straight down to the floorboards, feet flat
    for side, s in G.SIDES:
        hip = rig.pose.bones[G.bn("thigh", side)].head
        dy = math.sqrt(THIGH ** 2 - THIGH_DROP ** 2)
        knee = Vector((hip.x + s * FOOT_SPREAD, hip.y - dy, hip.z - THIGH_DROP))
        ank = Vector((knee.x + s * 0.5, knee.y + SHIN_BACK, ANKLE[2] + SOLE_LIFT))
        ctrl = G.bn("CTRL_foot", side)
        place(ctrl, Matrix.Translation(ank - Vector(ANKLE * np.array([s, 1, 1]))) @ bone_rest(ctrl))
        pole = G.bn("CTRL_knee", side)
        place(pole, Matrix.Translation(knee + Vector((s * 3.0, -20, 0)) - bone_rest(pole).translation) @ bone_rest(pole))
    # lean and look into the turn (+ about Kai's Y leans to his left; + about Z turns his head left)
    turn("spine_02", (0, 1, 0), -LEAN * amount)
    turn("spine_03", (0, 0, 1), -TWIST * amount)
    turn("neck_01", (0, 0, 1), -(LOOK - TWIST) * amount * 0.5)
    turn("head", (0, 0, 1), -LOOK * amount * 0.5)
    turn("head", (1, 0, 0), -4.0)
    # hands on the rim at ten to two, going round with the wheel: fingers over the top of the rim, palms inward
    grips = {}
    for side, s in G.SIDES:
        g, R = grip_frame(side, -B.WHEEL_MAX * amount)
        R = R @ Matrix.Rotation(math.radians(-GRIP_BETA[side]), 3, "Z")
        wrist = to_arm(g) - R @ GRIP_OFFSET[side]
        place(G.bn("CTRL_hand", side), Matrix.Translation(wrist) @ R.to_4x4())
        elbow = G.bn("CTRL_elbow", side)
        place(elbow, Matrix.Translation(Vector((s * 26.0, 12.0, 20.0)) - bone_rest(elbow).translation) @ bone_rest(elbow))
        curl(side, GRIP_CURL)
        grips[side] = g
    sync_ik_bones()
    return grips


def sync_ik_bones():
    """Mannequin IK goal bones follow the hands and feet."""
    for ik, src in (("ik_foot_l", "foot_l"), ("ik_foot_r", "foot_r"), ("ik_hand_gun", "hand_r"), ("ik_hand_l", "hand_l"),
                    ("ik_hand_r", "hand_r")):
        rig.pose.bones[ik].matrix = rig.pose.bones[src].matrix.copy()
        bpy.context.view_layer.update()


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def tree(ob):
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
    M = ob.matrix_world
    t = BVHTree.FromPolygons([M @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    V = np.array([(M @ v.co)[:] for v in me.vertices]); ev.to_mesh_clear()
    return t, V


OUTER = {}
reset()
for name, fn in (("SK_Kai_Tunic", G.tunic_sdf), ("SK_Kai_Pants", G.pants_sdf)):
    ob = bpy.data.objects[name]
    cen = np.array([(rig.matrix_world.inverted() @ ob.matrix_world @ p.center)[:] for p in ob.data.polygons])
    OUTER[name] = set(np.flatnonzero(fn(cen) > -0.15).tolist())


def checks(key, grips):
    T = {o.name: tree(o) for o in PARTS + [HULL, MOTOR, WHEEL]}
    r = {}
    for side, _ in G.SIDES:
        hand = A2W @ rig.pose.bones[G.bn("hand", side)].matrix @ GRIP_OFFSET[side]
        r[f"grip_{side}_error_cm"] = round((hand - Vector(grips[side])).length, 2)
    for side in ("l", "r"):
        f = rig.pose.bones["foot_" + side]; c = rig.pose.bones["CTRL_foot_" + side]
        r[f"foot_{side}_error_cm"] = round((f.head - c.head).length, 2)
    Vs = T["SK_Kai_Sandals"][1]
    r["sole_above_floor_cm"] = round(float(Vs[:, 2].min() - B.FLOOR_Z), 2)
    # seat contact: the lowest point of the pants over the driver's seat
    Vp = T["SK_Kai_Pants"][1]; x0, x1, top = B.SEAT["driver"]
    over = (Vp[:, 0] > x0) & (Vp[:, 0] < x1)
    r["seat_gap_cm"] = round(float(Vp[over, 2].min() - top), 2) if over.any() else None
    # Kai against the boat (the right hand is allowed to close round the grip)
    hits = {}
    pc = np.empty(len(HULL.data.polygons), np.int32); HULL.data.attributes["piece"].data.foreach_get("value", pc)
    import boat_textures as BT
    for o in PARTS:
        for b in (HULL, MOTOR, WHEEL):
            ov = T[o.name][0].overlap(T[b.name][0])
            if not ov: continue
            ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
            cen = np.array([(o.matrix_world @ me.polygons[i].center)[:] for i, j in ov]); ev.to_mesh_clear()
            if b is HULL:
                for piece in sorted({int(pc[j]) for i, j in ov}):
                    sel = [k for k, (i, j) in enumerate(ov) if pc[j] == piece]
                    hits[f"{o.name[7:]}/{BT.PIECES[piece]}"] = [len(sel), np.round(cen[sel].mean(0), 1).tolist(),
                                                               np.round(cen[sel].min(0), 1).tolist(), np.round(cen[sel].max(0), 1).tolist()]
            else:
                hits[f"{o.name[7:]}/{b.name[8:].lower()}"] = [len(ov), np.round(cen.mean(0), 1).tolist(), np.round(cen.min(0), 1).tolist(),
                                               np.round(cen.max(0), 1).tolist()]
    r["boat_overlaps"] = hits
    # how deep the fingers press into the wheel rim (the triangle count above includes skin just touching it)
    Wm = np.array(WHEEL.matrix_world.inverted())
    Va = T["SK_Kai_Arms"][1] @ Wm[:3, :3].T + Wm[:3, 3]
    dep = -B.wheel_sdf(Va)
    r["rim_depth_cm"] = round(float(max(0.0, dep.max())), 2)
    if "--why" in argv and (dep > 0.25).any():
        ob = bpy.data.objects["SK_Kai_Arms"]; gi = {g.index: g.name for g in ob.vertex_groups}
        deep = np.flatnonzero(dep > 0.25)
        from collections import Counter
        cnt = Counter()
        for i in deep:
            gs = ob.data.vertices[int(i)].groups
            if gs: cnt[gi[max(gs, key=lambda g: g.weight).group]] += 1
        ang = np.degrees(np.arctan2(-Va[deep, 1], Va[deep, 2]))
        r["deep_bones"] = dict(cnt.most_common(8)); r["deep_clock_deg"] = [round(float(ang.min()), 1), round(float(ang.max()), 1)]
        r["deep_radius"] = [round(float(np.hypot(Va[deep, 1], Va[deep, 2]).min()), 2), round(float(np.hypot(Va[deep, 1], Va[deep, 2]).max()), 2)]
    # clothes against each other (visible faces only, like kai_pose_check)
    cl = {}
    for a, b in (("SK_Kai_Tunic", "SK_Kai_Pants"), ("SK_Kai_Sash", "SK_Kai_Pants"), ("SK_Kai_Tunic", "SK_Kai_Legs")):
        ov = T[a][0].overlap(T[b][0])
        if a in OUTER: ov = [(i, j) for i, j in ov if i in OUTER[a]]
        if b in OUTER: ov = [(i, j) for i, j in ov if j in OUTER[b]]
        if ov:
            ob = bpy.data.objects[a]; ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
            cen = np.array([(ob.matrix_world @ me.polygons[i].center)[:] for i, j in ov]); ev.to_mesh_clear()
            cl[f"{a[7:]}/{b[7:]}"] = [len(ov), np.round(cen.mean(0), 1).tolist(), np.round(cen.min(0), 1).tolist(),
                                       np.round(cen.max(0), 1).tolist()]
        else:
            cl[f"{a[7:]}/{b[7:]}"] = 0
    r["cloth_overlaps"] = cl
    return r


if "--measure" in argv:
    for key in STEER:
        g = pose(key)
        print(key, json.dumps(checks(key, g)), flush=True)
    sys.exit(0)


def preview_setup():
    sc.render.engine = "CYCLES"; sc.cycles.samples = 8; sc.cycles.use_denoising = False
    sc.view_settings.view_transform = "Standard"; sc.cycles.max_bounces = 0; sc.cycles.transparent_max_bounces = 16
    for m in bpy.data.materials:
        if not m.node_tree or "CelPreview" not in m.node_tree.nodes: continue
        nt = m.node_tree; out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        nt.links.new(nt.nodes["CelPreview"].outputs[0], out.inputs["Surface"])
    w = bpy.data.worlds.new("Preview sky"); sc.world = w
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.43, 0.69, 0.85, 1)
    cam = bpy.data.objects.new("Preview camera", bpy.data.cameras.new("Preview camera")); sc.collection.objects.link(cam)
    sc.camera = cam; cam.data.type = "ORTHO"; cam.data.clip_start = 1; cam.data.clip_end = 5000
    return cam


def snap(cam, path, loc, target, scale, w=520, h=420):
    sc.render.resolution_x, sc.render.resolution_y = w, h
    cam.location = Vector(loc); cam.data.ortho_scale = scale
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = path; bpy.ops.render.render(write_still=True)


if "--closeup" in argv:
    out = argv[argv.index("--closeup") + 1]; os.makedirs(out, exist_ok=True)
    cam = preview_setup()
    pose("C")
    for k, (loc, tgt) in enumerate((((-30, 60, 65), (-64, 3, 45)), ((-30, -60, 65), (-64, -3, 45)),
                                    ((-64, 70, 46), (-64, 0, 45)), ((-20, 0, 75), (-66, 0, 44)))):
        snap(cam, os.path.join(out, f"close_{k}.png"), loc, tgt, 26, 600, 600)
    sys.exit(0)

if "--preview" in argv:
    out = argv[argv.index("--preview") + 1]; os.makedirs(out, exist_ok=True)
    cam = preview_setup()
    t = Vector((-82, 12, 40))
    t = Vector((-78, 0, 42))
    views = dict(side=((-78, 400, 42), 95), front=((300, 140, 140), 110), top=((-78, 0, 400), 100),
                 back=((-400, -150, 160), 110), hand=((-20, -70, 90), 40))
    for key in ("C", "L", "R"):
        g = pose(key)
        for v, (loc, scale) in views.items():
            if key != "C" and v not in ("top", "back"): continue
            tgt = Vector(B.WHEEL_C) if v == "hand" else t
            snap(cam, os.path.join(out, f"{key}_{v}.png"), loc, tgt, scale)
    sys.exit(0)


# ---------------------------------------------------------------------------
# Bake each pose onto the deform bones, export it, save the scene
# ---------------------------------------------------------------------------
def visual_to_basis(M):
    """matrix_basis for every bone from armature-space matrices M (name -> Matrix), parents first."""
    out = {}
    for b in arm.bones:
        rest = b.matrix_local
        if b.parent:
            rel = b.parent.matrix_local.inverted() @ rest
            out[b.name] = rel.inverted() @ M[b.parent.name].inverted() @ M[b.name]
        else:
            out[b.name] = rest.inverted() @ M[b.name]
    return out


DEFORM = [b.name for b in arm.bones if b.use_deform]


def bake(key):
    grips = pose(key)
    report = checks(key, grips)
    M = {pb.name: pb.matrix.copy() for pb in rig.pose.bones}
    heads = {n: list(np.round((rig.pose.bones[n].head)[:], 4)) for n in DEFORM}
    for pb in rig.pose.bones:
        for c in pb.constraints: c.mute = True
    basis = visual_to_basis(M)
    act = bpy.data.actions.new(POSE_NAMES[key]); act.use_fake_user = True
    rig.animation_data_create(); rig.animation_data.action = act
    for n in DEFORM:
        pb = rig.pose.bones[n]
        loc, rot, scl = basis[n].decompose()
        pb.location, pb.rotation_quaternion, pb.scale = loc, rot, scl
        for f in (1, 2):
            for path in ("location", "rotation_quaternion", "scale"):
                pb.keyframe_insert(path, frame=f, group=n)
    for pb in rig.pose.bones:
        if pb.name not in DEFORM: pb.matrix_basis = Matrix.Identity(4)
    sc.frame_set(1)
    err = max((rig.pose.bones[n].head - Vector(heads[n])).length for n in DEFORM)
    report["bake_error_cm"] = round(err, 5)
    return act, heads, report


def export_anim(act, path):
    keep = rig.matrix_world.copy()
    rig.matrix_world = Matrix.Identity(4)
    rig.animation_data.action = act
    sc.frame_start, sc.frame_end = 1, 2
    bpy.ops.object.select_all(action="DESELECT")
    rig.hide_set(False); rig.select_set(True); bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"ARMATURE"}, global_scale=1, apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_UNITS", axis_forward="X", axis_up="Z", use_space_transform=True,
        bake_space_transform=False, add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X",
        use_armature_deform_only=True, bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True, bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0)
    rig.matrix_world = keep


if not any(f in argv for f in ("--measure", "--preview", "--closeup")):
    poses, reports = {}, {}
    for key in ("L", "LH", "C", "RH", "R"):
        act, heads, rep = bake(key)
        export_anim(act, os.path.join(BOAT, POSE_NAMES[key] + ".fbx"))
        poses[POSE_NAMES[key]] = dict(steer=STEER[key], wheel_deg=-B.WHEEL_MAX * STEER[key], motor_deg=B.STEER_MAX * STEER[key],
                                      bone_heads_cm=heads)
        reports[POSE_NAMES[key]] = rep
        print(POSE_NAMES[key], json.dumps({k: v for k, v in rep.items() if k != "boat_overlaps"}), flush=True)
    # halfway between neighbouring poses (what a blend space plays): hands stay on the rim?
    order = ["L", "LH", "C", "RH", "R"]
    blends = {}
    for a, b in zip(order[:-1], order[1:]):
        A, Bp = bpy.data.actions[POSE_NAMES[a]], bpy.data.actions[POSE_NAMES[b]]
        poseA, poseB = {}, {}
        for act, store in ((A, poseA), (Bp, poseB)):
            rig.animation_data.action = act; sc.frame_set(1)
            store.update({n: rig.pose.bones[n].matrix_basis.copy() for n in DEFORM})
        rig.animation_data.action = None
        for n in DEFORM:
            la, ra, _ = poseA[n].decompose(); lb, rb, _ = poseB[n].decompose()
            if ra.dot(rb) < 0: rb = -rb
            pb = rig.pose.bones[n]
            pb.location = la.lerp(lb, 0.5); pb.rotation_quaternion = (ra * 0.5 + rb * 0.5).normalized(); pb.scale = (1, 1, 1)
        bpy.context.view_layer.update()
        mid = 0.5 * (STEER[a] + STEER[b]); set_boat(mid)
        errs = []
        for side, _ in G.SIDES:
            g, R = grip_frame(side, -B.WHEEL_MAX * mid)
            hand = A2W @ rig.pose.bones[G.bn("hand", side)].matrix @ GRIP_OFFSET[side]
            errs.append((hand - Vector(g)).length)
        Wm = np.array(WHEEL.matrix_world.inverted())
        Va = tree(bpy.data.objects["SK_Kai_Arms"])[1] @ Wm[:3, :3].T + Wm[:3, 3]
        blends[f"{POSE_NAMES[a]} + {POSE_NAMES[b]}"] = dict(grip_error_cm=round(max(errs), 2),
                                                            rim_depth_cm=round(float(max(0.0, -B.wheel_sdf(Va).min())), 2))
        print("blend", a, b, blends[f"{POSE_NAMES[a]} + {POSE_NAMES[b]}"], flush=True)
    # leave the scene in the straight-ahead pose
    rig.animation_data.action = bpy.data.actions[POSE_NAMES["C"]]; set_boat(0.0); sc.frame_set(1)
    json.dump(dict(kai_root_cm=B.KAI_ROOT.tolist(), seat_driver_cm=B.sockets()["Seat_Driver"][0].tolist(),
                   capsule_half_height_cm=B.CAPSULE_HALF, poses=poses),
              open(os.path.join(BOAT, "driving_poses.json"), "w"), indent=1)
    bad = []
    for name, rep in reports.items():
        for side in ("L", "R"):
            if rep[f"grip_{side}_error_cm"] > 0.05: bad.append(f"{name}: {side} hand misses the rim")
        if rep["rim_depth_cm"] > 0.4: bad.append(f"{name}: fingers {rep['rim_depth_cm']} cm into the rim")
        if any(v for v in rep["cloth_overlaps"].values()): bad.append(f"{name}: clothes cut through {rep['cloth_overlaps']}")
        hits = {k for k in rep["boat_overlaps"] if k not in ("Arms/wheel", "Tunic/seats")}
        if hits: bad.append(f"{name}: Kai cuts into the boat: {sorted(hits)}")
        if abs(rep["sole_above_floor_cm"]) > 0.3: bad.append(f"{name}: feet {rep['sole_above_floor_cm']} cm off the floor")
        if rep["bake_error_cm"] > 0.01: bad.append(f"{name}: bake drifted {rep['bake_error_cm']} cm")
    for name, rep in blends.items():
        if rep["grip_error_cm"] > 0.6 or rep["rim_depth_cm"] > 0.6: bad.append(f"{name} blended: hands drift off the rim {rep}")
    json.dump(dict(ok=not bad, problems=bad, poses=reports, blends=blends), open(os.path.join(BOAT, "driving_check.json"), "w"), indent=1)
    # the scene: Kai's textures packed in, the boat's next to the file
    for img in bpy.data.images:
        if img.name.startswith("T_Kai") and img.filepath: img.pack()
        elif img.name.startswith("T_Boat"): img.filepath = "//" + img.name + ".png"
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(BOAT, "Kai_Boat.blend"), relative_remap=False)
    print("\n".join(bad) if bad else "", "DRIVING_OK" if not bad else f"DRIVING_FAIL {len(bad)}")
    sys.exit(1 if bad else 0)
