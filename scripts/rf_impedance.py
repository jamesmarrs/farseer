#!/usr/bin/env python3
"""Field-solve the GNSS_RF_IN launch and line so the 50 ohm claim is reproducible.

Two electrostatic solvers, both plain finite-volume Laplace on a uniform grid
with a scipy sparse direct solve:

  line    2D cross-section of the grounded coplanar waveguide (CPWG) on F.Cu.
          Z0 = 1 / (c * sqrt(C * C_air)), eps_eff = C / C_air. Copper thickness
          and the soldermask are modelled explicitly; both matter (~4 ohm for
          the mask on this stack). The open-region answer is bracketed by
          solving twice, with Dirichlet (electric-wall) and Neumann (magnetic-
          wall) outer boundaries. Report both: a single number would imply a
          precision the model does not have.

  launch  Axisymmetric (r, z) solve of the J3 pin-1 through-hole launch:
          plated barrel through the full board, top and bottom annular pads,
          the In1/In2 antipads, and the F.Cu/B.Cu pour clearance. Returns the
          total capacitance of the signal conductor to ground. The square pad
          is approximated as a disc of the same half-width; the four ground
          barrels and the feed trace are not axisymmetric and are omitted, so
          treat the absolute value as +/-20% and the trends as solid.

Stackup defaults are JLCPCB JLC04161H-7628 as recorded in farseer.kicad_pcb.
Change the fab or the stack and re-run before touching the layout.

Usage:
  python3 scripts/rf_impedance.py line                # current board geometry
  python3 scripts/rf_impedance.py line --w 0.36       # what-if
  python3 scripts/rf_impedance.py line --sweep        # tolerance table
  python3 scripts/rf_impedance.py launch              # today vs planned launch
  python3 scripts/rf_impedance.py validate            # 1.6 mm FR4 microstrip check

Requires numpy and scipy (scripts/requirements.txt).
"""
import argparse
import math
import sys

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

C_LIGHT = 299792458.0
EPS0 = 8.854187817e-12

# JLC04161H-7628, from the (stackup ...) block in farseer.kicad_pcb.
STACK = {
    "t_cu_outer": 0.035,   # F.Cu / B.Cu
    "t_cu_inner": 0.0152,  # In1.Cu / In2.Cu
    "h_prepreg": 0.2104,   # 7628 prepreg, F.Cu -> In1.Cu and In2.Cu -> B.Cu
    "er_prepreg": 4.4,
    "h_core": 1.065,
    "er_core": 4.6,
    "t_mask": 0.020,       # nominal LPI mask over copper
    "er_mask": 3.6,
}

# Current board geometry.
LINE = {"w": 0.34, "s": 0.45}                    # RF_IN netclass / GNSS_RF_CPW rule
LAUNCH = {"r_hole": 0.75, "r_pour_gap": 0.45}    # J3 pin 1 drill 1.5, rule clearance


def _assemble(eps, cond, wx, wz, dx, bc):
    """Build the sparse Laplace operator for a cell-centred finite-volume grid.

    eps  : cell permittivity (nx, ny)
    cond : 0 free, 1 signal (V=1), 2 ground (V=0)
    wx   : weight on x-faces (nx-1, ny) - 1 for Cartesian, r for axisymmetric
    wz   : weight on z-faces (nx, ny-1)
    bc   : 'dirichlet' or 'neumann' on the far x and top y walls; y=0 is always
           a ground plane (Dirichlet) for the line solver, handled by caller via
           cond, or a Dirichlet wall via aS.
    """
    nx, ny = eps.shape
    exf = 2 * eps[:-1, :] * eps[1:, :] / (eps[:-1, :] + eps[1:, :]) * wx
    ezf = 2 * eps[:, :-1] * eps[:, 1:] / (eps[:, :-1] + eps[:, 1:]) * wz

    aE = np.zeros((nx, ny)); aW = np.zeros((nx, ny))
    aN = np.zeros((nx, ny)); aS = np.zeros((nx, ny))
    aE[:-1, :] = exf; aW[1:, :] = exf
    aN[:, :-1] = ezf; aS[:, 1:] = ezf
    if bc == "dirichlet":
        aE[-1, :] = 2 * eps[-1, :] * (wx[-1, :] if wx.ndim == 2 else 1)
        aN[:, -1] = 2 * eps[:, -1] * (wz[:, -1] if wz.ndim == 2 else 1)
    # bottom wall: always V=0 (the reference plane, or far ground below)
    aS[:, 0] = 2 * eps[:, 0] * (wz[:, 0] if wz.ndim == 2 else 1)
    diag = -(aE + aW + aN + aS)

    N = nx * ny
    ci = np.arange(N)
    rows = [ci]; cols = [ci]; vals = [diag.ravel()]
    for arr, off, sl in ((aE, ny, np.s_[:-1, :]), (aW, -ny, np.s_[1:, :]),
                         (aN, 1, np.s_[:, :-1]), (aS, -1, np.s_[:, 1:])):
        m = np.zeros((nx, ny), bool); m[sl] = True
        rows.append(ci[m.ravel()]); cols.append(ci[m.ravel()] + off); vals.append(arr[m])
    A = sp.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                      shape=(N, N)).tolil()
    cf = cond.ravel()
    fixed = np.where(cf != 0)[0]
    for r in fixed:
        A.rows[r] = [r]; A.data[r] = [1.0]
    rhs = np.zeros(N); rhs[fixed] = (cf[fixed] == 1).astype(float)
    V = spla.spsolve(A.tocsr(), rhs).reshape(nx, ny)
    return V, exf, ezf


# --------------------------------------------------------------------------- line

def line_capacitance(w, s, h, t, er_sub, er_mask, t_mask, hd, ht, dx, air, cpw, mask, bc):
    """Capacitance per metre of a CPWG (or microstrip if cpw=False) cross-section."""
    nx = int(round(2 * hd / dx)); ny = int(round(ht / dx))
    xc = (np.arange(nx) + 0.5) * dx - hd
    yc = (np.arange(ny) + 0.5) * dx
    X, Y = np.meshgrid(xc, yc, indexing="ij")

    eps = np.ones((nx, ny))
    if not air:
        eps[Y < h] = er_sub
        if mask:
            eps[(Y >= h) & (Y < h + t + t_mask)] = er_mask
    cond = np.zeros((nx, ny), np.int8)
    layer = (Y >= h) & (Y < h + t)
    cond[layer & (np.abs(X) <= w / 2)] = 1
    if cpw:
        cond[layer & (np.abs(X) >= w / 2 + s)] = 2

    V, exf, ezf = _assemble(eps, cond, np.ones((nx - 1, ny)), np.ones((nx, ny - 1)), dx, bc)
    dm = dx * 1e-3
    Ex = (V[:-1, :] - V[1:, :]) / dm
    Ey = (V[:, :-1] - V[:, 1:]) / dm
    W = 0.5 * EPS0 * ((exf * Ex ** 2).sum() + (ezf * Ey ** 2).sum()) * dm * dm
    return 2 * W


def line_z0(w, s, h=STACK["h_prepreg"], t=STACK["t_cu_outer"], er_sub=STACK["er_prepreg"],
            er_mask=STACK["er_mask"], t_mask=STACK["t_mask"], hd=2.0, ht=1.2, dx=0.005,
            cpw=True, mask=True, bc="neumann"):
    C = line_capacitance(w, s, h, t, er_sub, er_mask, t_mask, hd, ht, dx, False, cpw, mask, bc)
    Ca = line_capacitance(w, s, h, t, er_sub, er_mask, t_mask, hd, ht, dx, True, cpw, mask, bc)
    return 1.0 / (C_LIGHT * math.sqrt(C * Ca)), C / Ca


def line_both(**kw):
    zd, ed = line_z0(bc="dirichlet", **kw)
    zn, en = line_z0(bc="neumann", **kw)
    return zd, zn, ed, en


def cmd_line(a):
    print(f"CPWG on JLC04161H-7628: w={a.w} mm, gap={a.s} mm, h={a.h} mm, er={a.er}, "
          f"t_cu={STACK['t_cu_outer']} mm, mask={'on' if not a.no_mask else 'off'}")
    zd, zn, ed, en = line_both(w=a.w, s=a.s, h=a.h, er_sub=a.er, mask=not a.no_mask)
    print(f"  Z0 = {zd:.2f} .. {zn:.2f} ohm   (Dirichlet .. Neumann walls bracket the open answer)")
    print(f"  eps_eff = {ed:.3f} .. {en:.3f}")
    if a.sweep:
        print("\nSensitivity (Neumann walls; use the spread, not the absolute):")
        base, _ = line_z0(w=a.w, s=a.s)
        for lbl, kw in (("prepreg h -10%", dict(h=a.h * 0.9)), ("prepreg h +10%", dict(h=a.h * 1.1)),
                        ("width -0.02 mm", dict(w=a.w - 0.02)), ("width +0.02 mm", dict(w=a.w + 0.02)),
                        ("er 4.2", dict(er_sub=4.2)), ("er 4.6", dict(er_sub=4.6)),
                        ("gap 0.30 mm", dict(s=0.30)), ("gap 0.70 mm", dict(s=0.70))):
            args = dict(w=a.w, s=a.s, h=a.h, er_sub=a.er); args.update(kw)
            z, _ = line_z0(**args)
            print(f"  {lbl:16s} Z0 = {z:.2f} ohm  ({z - base:+.2f})")


def cmd_validate(_a):
    # Reference: 3.0 mm trace on 1.6 mm FR4 (er 4.4), 35 um copper, no mask.
    # Hammerstad with thickness correction gives ~49.6 ohm, eps_eff ~3.29.
    zd, zn, ed, en = line_both(w=3.0, s=0.0, h=1.6, cpw=False, mask=False, hd=16.0, ht=12.0, dx=0.02)
    print("Validation: microstrip w=3.0 mm, h=1.6 mm, er=4.4, t=35 um, no mask")
    print(f"  solver  Z0 = {zd:.1f} .. {zn:.1f} ohm, eps_eff = {ed:.2f} .. {en:.2f}")
    print("  expect  Z0 ~ 49.6 ohm, eps_eff ~ 3.29 (Hammerstad/Jensen with thickness)")
    ok = zd - 2.5 < 49.6 < zn + 2.5
    print("  PASS" if ok else "  FAIL")
    return 0 if ok else 1


# ------------------------------------------------------------------------- launch

def launch_capacitance(r_pad, r_void, r_pour_gap=LAUNCH["r_pour_gap"], r_hole=LAUNCH["r_hole"],
                       rmax=3.0, zlo=-0.6, zhi=2.2, d=0.01):
    """Total capacitance (F) of the J3 pin-1 signal conductor to ground."""
    # Layer z-extents from the bottom of B.Cu, snapped to the grid. Thin inner
    # planes are widened to two cells so they are resolved at all.
    t_o = STACK["t_cu_outer"]; t_i = max(STACK["t_cu_inner"], 2 * d)
    hp = STACK["h_prepreg"]; hc = STACK["h_core"]
    z = 0.0
    BCU = (z, z + t_o); z += t_o
    PP3 = (z, z + hp); z += hp
    IN2 = (z, z + t_i); z += t_i
    CORE = (z, z + hc); z += hc
    IN1 = (z, z + t_i); z += t_i
    PP1 = (z, z + hp); z += hp
    FCU = (z, z + t_o); z += t_o

    nr = int(round(rmax / d)); nz = int(round((zhi - zlo) / d))
    rc = (np.arange(nr) + 0.5) * d
    zc = zlo + (np.arange(nz) + 0.5) * d
    R, Z = np.meshgrid(rc, zc, indexing="ij")
    inlay = lambda L: (Z >= L[0]) & (Z < L[1])

    eps = np.ones((nr, nz))
    for L, e in ((PP3, STACK["er_prepreg"]), (CORE, STACK["er_core"]), (PP1, STACK["er_prepreg"]),
                 (BCU, STACK["er_prepreg"]), (IN2, STACK["er_prepreg"]),
                 (IN1, STACK["er_prepreg"]), (FCU, STACK["er_prepreg"])):
        eps[inlay(L)] = e

    cond = np.zeros((nr, nz), np.int8)
    cond[(R <= r_hole) & (Z >= BCU[0]) & (Z < FCU[1])] = 1           # plated barrel
    cond[inlay(FCU) & (R <= r_pad)] = 1                               # top pad
    cond[inlay(BCU) & (R <= r_pad)] = 1                               # bottom pad
    cond[(inlay(IN1) | inlay(IN2)) & (R >= r_void)] = 2               # planes outside antipad
    cond[(inlay(FCU) | inlay(BCU)) & (R >= r_pad + r_pour_gap)] = 2   # outer pours

    rf = 0.5 * (rc[:-1] + rc[1:])
    wx = np.repeat(rf[:, None], nz, axis=1)
    wz = np.repeat(rc[:, None], nz - 1, axis=1)
    V, exf, ezf = _assemble(eps, cond, wx, wz, d, "dirichlet")
    dm = d * 1e-3
    Er = (V[:-1, :] - V[1:, :]) / dm
    Ez = (V[:, :-1] - V[:, 1:]) / dm
    # exf/ezf already carry the r weight; volume element is 2*pi*r*dr*dz
    W = 0.5 * EPS0 * ((exf * Er ** 2).sum() + (ezf * Ez ** 2).sum()) * 2 * math.pi * 1e-3 * dm * dm
    return 2 * W


def return_loss_db(c_farads, f_hz=1575.42e6, z0=50.0, c_line=0.25e-12):
    """Return loss of a shunt C at the launch, net of the C a 50 ohm line would carry anyway."""
    b = 2 * math.pi * f_hz * max(c_farads - c_line, 0) * z0
    g = b / math.sqrt(4 + b * b)
    return float("inf") if g == 0 else -20 * math.log10(g)


def cmd_launch(_a):
    print("J3 pin-1 launch, axisymmetric solve (1.5 mm drill, 0.45 mm pour clearance):")
    cases = (("today: 2.3 mm square pad, 2.406 mm antipad", 1.15, 1.203),
             ("2.05 mm round pad, 2.406 mm antipad", 1.025, 1.203),
             ("2.05 mm round pad, 3.0 mm antipad  <- plan", 1.025, 1.50),
             ("2.05 mm round pad, 4.0 mm antipad", 1.025, 2.00),
             ("2.05 mm round pad, 5.0 mm antipad", 1.025, 2.50))
    for lbl, rp, rv in cases:
        c = launch_capacitance(rp, rv)
        print(f"  {lbl:46s} C = {c * 1e12:.3f} pF   RL ~ {return_loss_db(c):.1f} dB")
    print("  (RL nets out 0.25 pF of legitimate line capacitance; connector spec is VSWR 1.3 = 17.7 dB)")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("line", help="CPWG Z0 of the RF_IN trace")
    pl.add_argument("--w", type=float, default=LINE["w"], help="trace width, mm")
    pl.add_argument("--s", type=float, default=LINE["s"], help="gap to coplanar ground, mm")
    pl.add_argument("--h", type=float, default=STACK["h_prepreg"], help="prepreg height, mm")
    pl.add_argument("--er", type=float, default=STACK["er_prepreg"], help="prepreg er")
    pl.add_argument("--no-mask", action="store_true", help="bare copper (no soldermask)")
    pl.add_argument("--sweep", action="store_true", help="print the tolerance table")
    pl.set_defaults(fn=cmd_line)
    sub.add_parser("launch", help="J3 launch capacitance vs pad/antipad size").set_defaults(fn=cmd_launch)
    sub.add_parser("validate", help="check the solver against a textbook microstrip").set_defaults(fn=cmd_validate)
    a = p.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
