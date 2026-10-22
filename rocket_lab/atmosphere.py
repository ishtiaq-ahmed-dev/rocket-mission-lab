"""Dry-air hydrostatic layers through 84.852 km geopotential altitude.

1976 standard-atmosphere lapse rates; a continuous exponential tail above
the last layer is an explicit approximation, not a thermosphere model.
"""
import bisect
import math

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


def air_density(world,altitude):
    h=max(0.,float(altitude))
    if world.get('atmosphere_model')!='layered':
        return world['density_sea_level']*math.exp(-h/world['scale_height'])
    geopotential=6356766.*h/(6356766.+h)
    if geopotential>=HEIGHTS[-1]:
        density=PRESSURES[-1]/(R*TEMPERATURES[-1])*math.exp(-(geopotential-HEIGHTS[-1])/7000.)
    else:
        index=bisect.bisect_right(HEIGHTS,geopotential)-1
        base=TEMPERATURES[index];delta=geopotential-HEIGHTS[index];rate=LAPSE[index]
        temperature=base+rate*delta
        pressure=PRESSURES[index]*(math.exp(-G0*delta/(R*base)) if rate==0 else (base/temperature)**(G0/(R*rate)))
        density=pressure/(R*temperature)
    return density*world['density_sea_level']/1.225
