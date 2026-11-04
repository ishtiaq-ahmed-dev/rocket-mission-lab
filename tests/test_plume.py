import math
import pytest
from rocket_lab.atmosphere import pressure_at
from rocket_lab.plume import GAMMA, SEA_LEVEL_PRESSURE, exit_pressure, expansion, flame_length

WORLD = dict(atmosphere_model='layered', density_sea_level=1.225,
             scale_height=8500., gravity=9.80665)


def test_sea_level_full_throttle_is_the_authored_geometry():
    diameter, length = expansion(1., SEA_LEVEL_PRESSURE)
    assert diameter == pytest.approx(1.)
    assert length == pytest.approx(1.)


def test_overexpanded_plume_does_not_shrink_below_the_nozzle():
    # Half throttle on the pad: exit pressure is half an atmosphere, so the
    # plume contracts. The visible flame stays at the authored geometry.
    assert expansion(.5, SEA_LEVEL_PRESSURE) == pytest.approx((1., 1.))


def test_engine_off_has_no_plume():
    assert expansion(0., SEA_LEVEL_PRESSURE) == (0., 0.)


def test_diameter_follows_the_isentropic_area_ratio():
    for altitude in (5000., 11000., 20000., 40000.):
        ambient = pressure_at(WORLD, altitude)
        diameter, length = expansion(1., ambient)
        ratio = SEA_LEVEL_PRESSURE / ambient
        assert diameter ** (2. * GAMMA) == pytest.approx(ratio)
        # Shock-cell spacing, hence visible length, gains sqrt(p_e / p_a).
        assert length == pytest.approx(math.sqrt(ratio))


def test_plume_grows_monotonically_as_air_thins():
    gains = [expansion(1., pressure_at(WORLD, h))[0] for h in (0., 1000., 5000., 11000., 20000., 40000.)]
    assert gains[0] == pytest.approx(1.)
    assert all(later > earlier for earlier, later in zip(gains, gains[1:]))
    assert gains[4] > 2.  # ~20 km: the plume has clearly bloomed


def test_flame_length_never_passes_through_the_pad():
    # On the pad and just above it the flame is cut to the clearance floor.
    assert flame_length(1., SEA_LEVEL_PRESSURE, 0.) == pytest.approx(1.2)
    assert flame_length(1., SEA_LEVEL_PRESSURE, 3.) == pytest.approx(1.2)
    assert flame_length(1., SEA_LEVEL_PRESSURE, 200.) == pytest.approx(13.5)
    assert flame_length(0., SEA_LEVEL_PRESSURE, 200.) == 0.


def test_flame_length_grows_in_vacuum_but_is_bounded():
    assert flame_length(1., pressure_at(WORLD, 40000.), 40000.) == pytest.approx(17.)
    # Flicker modulates the render; the framing solver uses the steady length.
    assert flame_length(1., SEA_LEVEL_PRESSURE, 200., modulation=1.1) == pytest.approx(14.85)


def test_throttle_scales_exit_pressure():
    assert exit_pressure(.7) == pytest.approx(.7 * SEA_LEVEL_PRESSURE)
    # A throttled engine at altitude expands less than the same engine at full power.
    high = pressure_at(WORLD, 20000.)
    assert expansion(.7, high)[0] < expansion(1., high)[0]
