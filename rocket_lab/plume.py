"""Visible exhaust geometry from nozzle exit pressure and ambient pressure.

A booster engine is a sea-level-optimised nozzle: at full throttle its exit
pressure is one standard atmosphere, and chamber pressure — hence exit
pressure — falls in proportion to throttle. For an isentropic, axisymmetric
expansion from the nozzle exit (p_e) to ambient pressure (p_a):

    A / A_e = (p_e / p_a) ** (1 / gamma)        gamma = 1.2 (LOX/RP-1 exhaust)

so the jet diameter that has expanded to ambient pressure is

    D / D_e = (p_e / p_a) ** (1 / (2 * gamma))

The first shock cell of an underexpanded jet spans roughly D_e * sqrt(p_e / p_a)
(one exit diameter per unit of square-root pressure ratio), so the visible
length gains sqrt(p_e / p_a). Both multipliers are 1.0 for a full-throttle sea-level plume,
which is the geometry the vehicle is authored against; an overexpanded plume
(p_e < p_a) contracts instead, and the multiplier stays at 1.0 rather than
shrinking the visible flame below the nozzle.

This is a geometric approximation, not a combustion model. Turbulence, the
afterburning of fuel-rich exhaust and radiative opacity are not solved.
"""
import math

GAMMA=1.2
SEA_LEVEL_PRESSURE=101325.


def exit_pressure(throttle,sea_level_pressure=SEA_LEVEL_PRESSURE):
    """Nozzle exit pressure in pascals; throttling lowers chamber pressure."""
    return max(0.,float(throttle))*float(sea_level_pressure)


def expansion(throttle,ambient_pressure,sea_level_pressure=SEA_LEVEL_PRESSURE,gamma=GAMMA):
    """(diameter, length) multipliers relative to a sea-level plume.

    Both are 1.0 on the pad at full throttle and grow as ambient pressure
    falls. An engine that is off returns (0., 0.).
    """
    exit_pa=exit_pressure(throttle,sea_level_pressure)
    if exit_pa<=0.:
        return 0.,0.
    ratio=max(exit_pa/max(1e-3,float(ambient_pressure)),1.)
    return math.pow(ratio,1./(2.*float(gamma))),math.sqrt(ratio)


def flame_length(throttle,ambient_pressure,clearance,base=13.5,ceiling=17.,modulation=1.):
    """Metres of visible flame below the nozzle, shared by render and framing.

    `clearance` is the height of the nozzle above the ground: the flame is
    cut short there so it never tunnels through the pad. `modulation` is the
    combustion flicker, so the camera solver can frame the steady length.
    """
    tau=max(0.,float(throttle))*max(0.,float(modulation))
    if tau<=0.:
        return 0.
    _,length_gain=expansion(throttle,ambient_pressure)
    return min(max(min(tau*float(base)*length_gain,float(ceiling)),.1),
               max(.35*float(clearance),1.2))
