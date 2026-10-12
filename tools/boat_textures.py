"""Colours of Kai's boat, painted per texel from 3D position (see kai_textures.bake).

Palette matches Kai: cream topsides, red bottom, a navy boot stripe and rub rail, honey wood inside, and a retro
red-and-cream outboard with a yellow star on the cowl.
"""
import numpy as np

import boat_geometry as B
from kai_textures import mix, sstep, unpack


def rgb(*c):
    return np.array(c, float) / 255.0


PAL = dict(
    cream=rgb(248, 242, 226), cream_line=rgb(220, 210, 190), red=rgb(206, 58, 46), red_line=rgb(170, 44, 36),
    navy=rgb(38, 62, 130), wood=rgb(214, 160, 98), wood_line=rgb(170, 116, 66), wood_dark=rgb(186, 128, 76),
    deck=rgb(226, 178, 114), seat=rgb(224, 172, 106), seat_edge=rgb(188, 136, 82),
    cowl=rgb(212, 46, 40), band=rgb(246, 236, 214), metal=rgb(76, 80, 90), grip=rgb(44, 38, 36), clamp=rgb(152, 156, 164),
    star=rgb(252, 204, 64), brass=rgb(214, 170, 72), brass_dark=rgb(170, 128, 50),
    lamp_port=rgb(226, 52, 48), lamp_star=rgb(60, 196, 96),
)
if "cowl" in B.VARIANT:                       # a cream cowl over a red band, so the motor stands apart from Kai's shirt
    PAL.update(cowl=rgb(246, 236, 214), band=rgb(212, 46, 40), star=rgb(212, 46, 40))
PIECES = ["outer", "inner", "rim", "transom", "deck", "bulkhead", "floor", "seats", "rail", "pad", "clamp", "bow", "console"]
PID = {n: i for i, n in enumerate(PIECES)}


def _lines(t, pitch, width):
    """1 on thin lines spaced `pitch` apart along t (soft-edged), else 0."""
    f = np.abs(((t / pitch) + 0.5) % 1.0 - 0.5) * pitch
    return sstep(width, width * 0.4, f)


def _height_frac(P):
    P = B.unrake(P)
    zk, zs = B.keel_z(P[:, 0]), B.sheer_z(P[:, 0])
    return (P[:, 2] - zk) / np.maximum(zs - zk, 1e-6)


def _topsides(P):
    """Outside colours by height: red bottom, a bold navy boot stripe just above the waterline, cream topsides with
    plank seams."""
    z = P[:, 2]
    col = np.tile(PAL["cream"], (len(P), 1))
    hf = _height_frac(P)
    col = mix(col, PAL["cream_line"], _lines(hf - 0.08, 0.17, 0.012) * (z > B.WATERLINE + 11.5))
    col[z < B.WATERLINE + 10.5] = PAL["navy"]
    red = z < B.WATERLINE + 6.0
    col[red] = mix(np.tile(PAL["red"], (red.sum(), 1)), PAL["red_line"], _lines(hf[red] - 0.08, 0.17, 0.012))
    return col


def _ribs(P):
    """Frames inside the hull: darker strips every 24 cm along the boat."""
    x = B.unrake(P)[:, 0]
    if "interior" in B.VARIANT:
        return _lines(x - B.XS - 20.0, 36.0, 1.6)
    return _lines(x - B.XS - 14.0, 24.0, 1.0)


def paint_hull(a):
    P, Nn, piece, loc = unpack(a)
    col = np.tile(PAL["wood"], (len(P), 1))
    for name in ("outer",):
        m = piece == PID[name]; col[m] = _topsides(P[m])
    m = piece == PID["transom"]
    if m.any():
        outer_face = P[m, 0] < B.XS + B.T * 0.5
        c = np.tile(PAL["wood"], (m.sum(), 1))
        c[outer_face] = _topsides(P[m][outer_face])
        top = P[m, 2] > B.sheer_z(B.XS) - 0.05
        c[top] = PAL["wood_dark"]
        col[m] = c
    m = piece == PID["inner"]
    c = np.tile(PAL["wood"], (m.sum(), 1))
    if "interior" not in B.VARIANT:
        c = mix(c, PAL["wood_line"], _lines(_height_frac(P[m]) - 0.12, 0.2, 0.014))
    col[m] = mix(c, PAL["wood_dark"], _ribs(P[m]))
    col[piece == PID["rim"]] = PAL["wood_dark"]
    col[piece == PID["bulkhead"]] = mix(np.tile(PAL["wood"], ((piece == PID["bulkhead"]).sum(), 1)), PAL["wood_line"],
                                        _lines(P[piece == PID["bulkhead"], 2] - B.FLOOR_Z, 8.0, 0.35))
    m = piece == PID["deck"]
    col[m] = mix(np.tile(PAL["deck"], (m.sum(), 1)), PAL["wood_line"], _lines(P[m, 1] + 3.5, 7.0, 0.3))
    m = piece == PID["floor"]
    floor = PAL["deck"] if "interior" in B.VARIANT else PAL["wood"]
    c = mix(np.tile(floor, (m.sum(), 1)), PAL["wood_line"], _lines(P[m, 1] + 4.5, 9.0, 0.35))
    c[Nn[m, 2] < 0.5] = PAL["wood_dark"]
    col[m] = c
    m = piece == PID["seats"]
    c = np.tile(PAL["seat"], (m.sum(), 1))
    c = mix(c, PAL["wood_line"], _lines(P[m, 0] + 3.0, 14.0, 0.3) * (Nn[m, 2] > 0.5))
    c[Nn[m, 2] < 0.5] = PAL["seat_edge"]
    col[m] = c
    col[piece == PID["rail"]] = PAL["navy"]
    col[piece == PID["pad"]] = PAL["wood_dark"]
    m = piece == PID["clamp"]
    c = np.tile(PAL["clamp"], (m.sum(), 1))
    c[P[m, 0] > B.XS + B.T + 1.6] = PAL["metal"]                       # the screws
    col[m] = c
    m = piece == PID["bow"]
    Q = B.unrake(P[m])
    c = np.tile(PAL["clamp"], (m.sum(), 1))
    lamp = Q[:, 2] > B.BOW_LIGHT[2] - 2.0
    c[lamp & (Q[:, 1] >= 0)] = PAL["lamp_port"]
    c[lamp & (Q[:, 1] < 0)] = PAL["lamp_star"]
    col[m] = c
    m = piece == PID["console"]
    col[m] = _console(P[m], Nn[m])
    return col


def _console(P, Nn):
    """Honey wood box with plank lines, a navy trim round the top, a cream dash with a round gauge, a grey steering
    column and a throttle lever with a red knob."""
    c = B.CONSOLE
    col = mix(np.tile(PAL["wood"], (len(P), 1)), PAL["wood_line"], _lines(P[:, 2] - B.FLOOR_Z, 7.5, 0.3))
    slope = (c["top_front"] - c["top_back"]) / (c["x1"] - c["x0"])
    ztop = c["top_back"] + slope * (P[:, 0] - c["x0"])
    below = ztop - P[:, 2]                                                    # depth under the dash top
    col = mix(col, PAL["navy"], sstep(3.4, 3.0, below))                       # trim band, soft-edged
    col = mix(col, PAL["cream"], sstep(0.9, 0.6, below))                      # dash top
    q = P - B.WHEEL_C
    along = q @ B.WHEEL_FWD
    radial = np.linalg.norm(q - np.outer(along, B.WHEEL_FWD), axis=1)
    col[(radial < 2.3) & (along > -1.5) & (P[:, 0] < c["x0"] + 0.5)] = PAL["clamp"]   # steering column
    g = np.hypot(P[:, 1] - 5.4, P[:, 2] - B.GAUGE_Z)                          # gauge
    face = (g < 2.3) & (P[:, 0] < c["x0"] - 0.4)
    col[face & (g >= 1.7)] = PAL["navy"]
    col[face & (g < 1.7)] = PAL["cream"]
    needle = face & (g < 1.5) & (np.abs((P[:, 1] - 5.4) * 0.8 + (P[:, 2] - B.GAUGE_Z) * 0.6) < 0.22) & (P[:, 2] > B.GAUGE_Z - 0.4)
    col[needle] = PAL["red"]
    lever = (P[:, 1] < -c["half_w"] - 0.2) | ((P[:, 2] > c["top_front"] + 1.0) & (P[:, 1] < 0))
    col[lever] = PAL["metal"]
    col[np.linalg.norm(P - B.THROTTLE_KNOB, axis=1) < 2.0] = PAL["cowl"]
    return col


def paint_wheel(a):
    """The steering wheel, painted in its own frame: red rim, cream spokes, navy hub with a yellow star cap."""
    P, Nn, piece, loc = unpack(a)
    part = B.wheel_part(P)
    if "console" in B.VARIANT:                    # cream rim, wooden spokes, red hub with a yellow star
        col = np.array([PAL["band"], PAL["seat"], PAL["cowl"], PAL["star"]])[part]
    else:
        col = np.array([PAL["cowl"], PAL["band"], PAL["navy"], PAL["star"]])[part]
    ang = np.arctan2(P[:, 2], P[:, 1]); r = np.hypot(P[:, 1], P[:, 2])
    rim = part == 0
    line = PAL["cream_line"] if "console" in B.VARIANT else PAL["red_line"]
    col[rim] = mix(col[rim], line, _lines(ang[rim] * B.WHEEL_R, 2.2, 0.25) * (P[rim, 0] > 0))
    k = 0.5 + 0.5 * np.cos(5 * (ang - np.pi / 2))
    star = (part == 3) & (r < 0.55 + 0.75 * k ** 3)
    col[(part == 3) & ~star] = PAL["cowl"] if "console" in B.VARIANT else PAL["navy"]
    return col


def paint_motor(a):
    P, Nn, piece, loc = unpack(a)
    part = B.motor_part(P)
    col = np.array([PAL["cowl"], PAL["band"], PAL["metal"]])[part]
    # a yellow star on each side of the cowl
    for s in (1, -1):
        c = np.array([B.MOTOR_PIVOT[0] - 7.5, 11.0 * s, B.MOTOR_PIVOT[2] + 16.0])
        q = P - c
        on_side = (part == 0) & (P[:, 1] * s > 7.0)
        r = np.hypot(q[:, 0], q[:, 2]); ang = np.arctan2(q[:, 2], q[:, 0])
        k = 0.5 + 0.5 * np.cos(5 * (ang - np.pi / 2))
        star = r < 1.9 + 2.9 * k ** 3
        col[on_side & star] = PAL["star"]
    return col


def paint_prop(a):
    P, Nn, piece, loc = unpack(a)
    r = np.hypot(P[:, 1] - B.PROP_C[1], P[:, 2] - B.PROP_C[2])
    col = np.tile(PAL["brass"], (len(P), 1))
    col[r < 2.3] = PAL["brass_dark"]
    return col
