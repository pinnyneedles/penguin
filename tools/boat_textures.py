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
PIECES = ["outer", "inner", "rim", "transom", "deck", "bulkhead", "floor", "seats", "rail", "pad", "clamp", "bow"]
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
    c = mix(np.tile(PAL["wood"], (m.sum(), 1)), PAL["wood_line"], _lines(_height_frac(P[m]) - 0.12, 0.2, 0.014))
    col[m] = mix(c, PAL["wood_dark"], _ribs(P[m]))
    col[piece == PID["rim"]] = PAL["wood_dark"]
    col[piece == PID["bulkhead"]] = mix(np.tile(PAL["wood"], ((piece == PID["bulkhead"]).sum(), 1)), PAL["wood_line"],
                                        _lines(P[piece == PID["bulkhead"], 2] - B.FLOOR_Z, 8.0, 0.35))
    m = piece == PID["deck"]
    col[m] = mix(np.tile(PAL["deck"], (m.sum(), 1)), PAL["wood_line"], _lines(P[m, 1] + 3.5, 7.0, 0.3))
    m = piece == PID["floor"]
    c = mix(np.tile(PAL["wood"], (m.sum(), 1)), PAL["wood_line"], _lines(P[m, 1] + 4.5, 9.0, 0.35))
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
    return col


def paint_motor(a):
    P, Nn, piece, loc = unpack(a)
    part = B.motor_part(P)
    col = np.array([PAL["cowl"], PAL["band"], PAL["metal"], PAL["grip"], PAL["clamp"]])[part]
    # a yellow star on each side of the cowl
    for s in (1, -1):
        c = np.array([B.MOTOR_PIVOT[0] - 7.5, 11.0 * s, B.MOTOR_PIVOT[2] + 16.0])
        q = P - c
        on_side = (part == 0) & (P[:, 1] * s > 7.0)
        r = np.hypot(q[:, 0], q[:, 2]); ang = np.arctan2(q[:, 2], q[:, 0])
        k = 0.5 + 0.5 * np.cos(5 * (ang - np.pi / 2))
        star = r < 1.9 + 2.9 * k ** 3
        col[on_side & star] = PAL["star"]
    # grip ribs
    g = part == 3
    col[g] = mix(col[g], rgb(70, 62, 58), _lines(P[g, 0] - B.TILLER_GRIP[0], 1.6, 0.18))
    return col


def paint_prop(a):
    P, Nn, piece, loc = unpack(a)
    r = np.hypot(P[:, 1] - B.PROP_C[1], P[:, 2] - B.PROP_C[2])
    col = np.tile(PAL["brass"], (len(P), 1))
    col[r < 2.3] = PAL["brass_dark"]
    return col
