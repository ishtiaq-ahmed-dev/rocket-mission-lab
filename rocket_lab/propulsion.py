"""Engine performance from vacuum thrust, nozzle exit area and Isp.

The same ambient-pressure model is used by the MuJoCo body, the Isaac mirror
and the controller feedforward. ``max_thrust`` remains the normalization
reference and the legacy fallback.
"""
from .atmosphere import pressure_at

P0 = 101325.


def engine_performance(world, vehicle, throttle, altitude, scale=1.):
    throttle = max(0., min(1., float(throttle)))
    pressure = pressure_at(world, altitude)
    vacuum = float(vehicle.get('thrust_vacuum', vehicle['max_thrust']))
    exit_area = float(vehicle.get('nozzle_exit_area', 0.))
    thrust = max(0., vacuum - pressure * exit_area) * throttle * float(scale)
    isp_sea = float(vehicle.get('isp_sea_level', vehicle['isp']))
    isp_vac = float(vehicle.get('isp_vacuum', vehicle['isp']))
    fraction = min(1., max(0., 1. - pressure / P0))
    isp = isp_sea + (isp_vac - isp_sea) * fraction
    return thrust, isp


def specific_impulse(world, vehicle, altitude):
    pressure = pressure_at(world, altitude)
    isp_sea = float(vehicle.get('isp_sea_level', vehicle['isp']))
    isp_vac = float(vehicle.get('isp_vacuum', vehicle['isp']))
    fraction = min(1., max(0., 1. - pressure / P0))
    return isp_sea + (isp_vac - isp_sea) * fraction
