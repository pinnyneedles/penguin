#!/usr/bin/env python3
"""Check that Kai's layered parts never poke through each other in the rest pose.

    python3 tools/kai_clearance.py

For every pair of parts that overlap, samples the inner part's surface and measures it against the outer part's
signed distance field. Prints the worst offenders; exits non-zero if anything shows through.
"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kai_geometry as G


def surface(fn, box, h=0.3):
    v, f = G.polygonize(fn, box, h)
    return v


def check(name, pts, outer_sdf, region, want_inside, margin):
    pts = pts[region(pts)]
    d = outer_sdf(pts)
    bad = d > -margin if want_inside else d < margin
    worst = (d.max() if want_inside else d.min()) if len(d) else 0.0
    print(f"{name:52s} samples {len(pts):6d}  through {int(bad.sum()):5d}  worst {worst:+.3f} cm", flush=True)
    return int(bad.sum())


arm_end = {}
for side, s in G.SIDES:
    S, E, W, d2 = G.arm_points(s); d1 = G.nrm(E - S); arm_end[s] = (S, d1, S + d1 * 6.6)


def under_sleeve(P):
    m = np.zeros(len(P), bool)
    for s in (1.0, -1.0):
        S, d1, end = arm_end[s]
        m |= ((P - end) @ d1 < -0.4) & (np.sign(P[:, 0]) == s)
    return m


def above_cuff(P):
    m = np.zeros(len(P), bool)
    for s in (1.0, -1.0):
        H, K, A, Bl, T = G.leg_points(s); C = G.cuff_point(s); ax = G.nrm(C - K)
        m |= ((P - C) @ ax < -0.6) & (np.sign(P[:, 0]) == s)
    return m


bad = 0
pants = surface(G.pants_sdf, G.PANTS_BOX)
bad += check("pants hidden under the tunic (above the hem)", pants, G.tunic_sdf, lambda P: P[:, 2] > G.HEM_Z + 0.4, True, 0.08)
legs = surface(G.legs_sdf, G.LEGS_BOX)
bad += check("calves hidden in the pants legs (above the cuff)", legs, G.pants_sdf, above_cuff, True, 0.08)
arms = surface(G.arms_sdf, G.part_box("arms"))
bad += check("upper arms hidden in the sleeves", arms, G.tunic_sdf, under_sleeve, True, 0.08)
head = surface(G.head_base_sdf, G.HEAD_BOX)
bad += check("neck hidden in the tunic and collar (below the collar)", head,
             lambda P: np.minimum(G.tunic_sdf(P), G.collar_sdf(P)), lambda P: P[:, 2] < G.Z["shoulder"] - 0.2, True, 0.05)
sash = surface(G.sash_sdf, G.SASH_BOX)
bad += check("sash band and tails sit on the tunic (knot excluded)", sash, G.tunic_sdf,
             lambda P: np.linalg.norm(P - G.sash_knot(), axis=1) > 2.6, False, 0.02)
kerch = surface(G.neckerchief_sdf, G.KERCHIEF_BOX)
bad += check("neckerchief sits on the tunic", kerch, G.tunic_sdf, lambda P: np.ones(len(P), bool), False, 0.02)
collar = surface(G.collar_sdf, G.TUNIC_BOX)
bad += check("collar sits on the tunic", collar, G.tunic_sdf, lambda P: np.ones(len(P), bool), False, 0.02)
# the calves meet the sandals (which own the feet) only under the ankle strap
z0, z1 = G.ankle_band(1.0)
bad += check("calves clear of the sandals outside the ankle strap", legs, G.sandal_sdf,
             lambda P: (P[:, 2] < z0 - 0.05) | (P[:, 2] > z1 + 0.25), False, 0.05)
bad += check("calf ends are hidden inside the ankle strap", legs, G.sandal_sdf, lambda P: P[:, 2] < z0 + 0.6, True, 0.02)
print("CLEARANCE_OK" if bad == 0 else f"CLEARANCE_FAIL {bad}")
sys.exit(1 if bad else 0)
