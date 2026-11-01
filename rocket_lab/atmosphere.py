"""Dry-air hydrostatic layers through 84.852 km geopotential altitude.

1976 standard-atmosphere lapse rates; a continuous exponential tail above
the last layer is an explicit approximation, not a thermosphere model.
"""
import bisect
import math
import numpy as np

HEIGHTS=(0.,11000.,20000.,32000.,47000.,51000.,71000.,84852.)
LAPSE=(-.0065,0.,.001,.0028,0.,-.0028,-.002)
G0,R=9.80665,287.05287
TEMPERATURES=[288.15]
PRESSURES=[101325.]
for index,rate in enumerate(LAPSE):
    lower=TEMPERATURES[-1];height=HEIGHTS[index+1]-HEIGHTS[index]
    upper=lower+rate*height
    ratio=math.exp(-G0*height/(R*lower)) if rate==0 else (lower/upper)**(G0/(R*rate))
    TEMPERATURES.append(upper);PRESSURES.append(PRESSURES[-1]*ratio)


def _layer(world, altitude):
    geopotential=6356766.*max(0.,float(altitude))/(6356766.+max(0.,float(altitude)))
    if geopotential>=HEIGHTS[-1]:
        return None,geopotential
    index=bisect.bisect_right(HEIGHTS,geopotential)-1
    return index,geopotential


def temperature_at(world,altitude):
    h=max(0.,float(altitude))
    if world.get('atmosphere_model')!='layered':
        return 288.15-.0065*h
    index,geopotential=_layer(world,h)
    if index is None:return TEMPERATURES[-1]
    return TEMPERATURES[index]+LAPSE[index]*(geopotential-HEIGHTS[index])


def pressure_at(world,altitude):
    h=max(0.,float(altitude))
    if world.get('atmosphere_model')!='layered':
        density=world['density_sea_level']*math.exp(-h/world['scale_height'])
        return density*R*temperature_at(world,h)
    index,geopotential=_layer(world,h)
    if index is None:
        # The last 1.148 km of the 1976 table is isothermal; continue that
        # layer above 84.852 km rather than inventing a thermosphere.
        return PRESSURES[-1]*math.exp(-G0*(geopotential-HEIGHTS[-1])/(R*TEMPERATURES[-1]))
    base=TEMPERATURES[index];delta=geopotential-HEIGHTS[index];rate=LAPSE[index]
    temperature=base+rate*delta
    return PRESSURES[index]*(math.exp(-G0*delta/(R*base)) if rate==0 else (base/temperature)**(G0/(R*rate)))


def air_density(world,altitude):
    h=max(0.,float(altitude))
    if world.get('atmosphere_model')!='layered':
        return world['density_sea_level']*math.exp(-h/world['scale_height'])
    return pressure_at(world,h)/(R*temperature_at(world,h))*world['density_sea_level']/1.225


def speed_of_sound(world,altitude):
    return math.sqrt(1.4*R*temperature_at(world,altitude))


def mach_number(world,altitude,speed):
    return abs(float(speed))/max(1e-9,speed_of_sound(world,altitude))


def drag_coefficient_at(vehicle,mach):
    """Piecewise-linear axial coefficient; a constant legacy model is unchanged."""
    table=vehicle.get('drag_coefficient_mach')
    if not table:return float(vehicle['drag_coefficient'])
    points=sorted((float(point[0]),float(point[1])) for point in table)
    value=max(0.,float(mach))
    if value<=points[0][0]:return points[0][1]
    for (left_m,left_c),(right_m,right_c) in zip(points,points[1:]):
        if value<=right_m:
            fraction=(value-left_m)/max(1e-12,right_m-left_m)
            return left_c+(right_c-left_c)*fraction
    return points[-1][1]


def wind_shear(world,altitude):
    """Power-law mean-wind profile, normalised at the reference height.

    A single mean wind vector describes the whole column in the legacy model.
    Real surface wind grows with height through the boundary layer, so the
    profile here multiplies that vector by ((h+z_ref)/z_ref)**alpha. The
    exponent and reference height are configuration, not fitted weather data.
    """
    exponent=float(world.get('wind_shear_exponent',0.) or 0.)
    reference=max(1e-9,float(world.get('wind_reference_height',10.) or 10.))
    if exponent<=0:return 1.
    return ((max(0.,float(altitude))+reference)/reference)**exponent


def wind_at(world,mean,altitude,scale=1.):
    """Mean wind vector at an altitude. Zero shear returns the legacy constant."""
    return np.asarray(mean,dtype=float)*float(scale)*wind_shear(world,altitude)


def aerodynamic_force(world,vehicle,rotation,velocity,wind,altitude):
    """Body-axis drag decomposition with a broadside (lateral) area.

    The axial coefficient follows the configured Mach table. The lateral term
    uses the broadside coefficient; a cylinder is not isotropic.
    """
    relative=np.asarray(velocity,dtype=float)-np.asarray(wind,dtype=float)
    rho=air_density(world,altitude)
    mach=mach_number(world,altitude,np.linalg.norm(relative))
    axial_cd=drag_coefficient_at(vehicle,mach)
    if vehicle.get('aero_model')!='axial-lateral':
        return -0.5*rho*axial_cd*vehicle['area']*np.linalg.norm(relative)*relative
    axis=np.asarray(rotation,dtype=float)[:,2]
    axial=float(np.dot(relative,axis))
    lateral=relative-axial*axis
    force=-0.5*rho*axial_cd*vehicle['area']*abs(axial)*axial*axis
    force=force-0.5*rho*vehicle.get('drag_coefficient_lateral',vehicle['drag_coefficient'])*vehicle.get('area_lateral',vehicle['area'])*np.linalg.norm(lateral)*lateral
    return force


def aerodynamic_torque(vehicle,rotation,force):
    """Moment of the aerodynamic force about the centre of mass.

    `aero_center` is the centre-of-pressure offset along the body axis in
    metres, positive toward the nose. With the offset above the centre of mass
    a tilted descending booster weathercocks engine-first, which is the
    passively stable direction for a grid-fin-first descent. Zero preserves
    the legacy centre-of-mass drag application.
    """
    center=float(vehicle.get('aero_center',0.) or 0.)
    if not center:return np.zeros(3)
    axis=np.asarray(rotation,dtype=float)[:,2]
    return np.cross(center*axis,np.asarray(force,dtype=float))
