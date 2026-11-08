"""Build the replay's ground imagery from public-domain USGS orthoimagery.

Source: The National Map "USGS Imagery Only" map service (NAIP 1 m aerial imagery
over land, Landsat / Blue Marble at small scales). U.S. Government work, public
domain. Each layer is one MapServer `export` request in Web Mercator.

Writes to frontend/public/assets/geo/:
  globe.jpg / wide.jpg / region.jpg / local.jpg / slc40.jpg / lz1.jpg   nested mosaics
  *-mask.png                                                land (white) / water (black)
  geo.json                                                 lon/lat bounds of every layer

The page converts world positions to latitude/longitude and samples the finest
layer that covers each point.

    python scripts/fetch_imagery.py        # raw exports are cached in data/geo-cache
    CURL=/path/to/curl python scripts/fetch_imagery.py
"""
import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'frontend' / 'public' / 'assets' / 'geo'
CACHE = ROOT / 'data' / 'geo-cache'
SERVICE = 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer'
UA = 'rocket-mission-lab-imagery/1.0 (educational replay; public-domain USGS imagery)'

SLC40 = (28.5619, -80.5773)          # launch site (LAT_S in the simulator)
LZ1 = (28.48583, -80.54444)          # centre of the lz1 tile (pad itself: 28.485727, -80.542961, inside it)
MID = ((SLC40[0] + LZ1[0]) / 2, (SLC40[1] + LZ1[1]) / 2)


def export(name, lat0, lat1, lon0, lon1, w, h):
    """One export request; cached. Returns RGBA float array (alpha 0 = no data)."""
    path = CACHE / f'{name}-{w}x{h}.png'
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        url = (f'{SERVICE}/export?bbox={lon0},{lat0},{lon1},{lat1}&bboxSR=4326&imageSR=3857'
               f'&size={w},{h}&format=png32&transparent=true&f=image')
        for attempt in range(30):            # the public service resets many connections
            r = subprocess.run([os.environ.get('CURL', 'curl'), '-sf', '-m', '180', '-A', UA, '-o', str(path), url])
            if r.returncode == 0 and path.exists() and path.stat().st_size > 1000:
                try:
                    Image.open(path).verify()
                    break
                except Exception:
                    pass
            path.unlink(missing_ok=True)
            if attempt == 29:
                raise RuntimeError(f'{name}: export failed (curl exit {r.returncode})')
            time.sleep(4 + attempt)
    return np.asarray(Image.open(path).convert('RGBA')).astype(np.float32)


def layer(name, lat0, lat1, lon0, lon1, w, h, quality, mask=None, coarse=False, support=None):
    rgba = export(name, lat0, lat1, lon0, lon1, w, h)
    alpha = rgba[..., 3] / 255.0
    sea = np.array([16, 48, 70], np.float32)            # no-data is open ocean
    rgb = rgba[..., :3] * alpha[..., None] + sea * (1 - alpha[..., None])
    Image.fromarray(rgb.clip(0, 255).astype(np.uint8)).save(OUT / f'{name}.jpg', quality=quality, optimize=True, progressive=True)
    entry = {'file': f'{name}.jpg', 'lat': [lat0, lat1], 'lon': [lon0, lon1], 'size': [w, h]}
    if mask:
        entry['mask'], land = water_mask(name, rgb, alpha, mask, coarse, support, ((lat0, lat1), (lon0, lon1)))
        entry['_land'] = land
    return entry


def water_mask(name, rgb, alpha, width, coarse=False, support=None, bounds=None):
    """Land = 255, water = 0. Water in NAIP / Landsat is blue- or teal-dominant and darker than
    sand or concrete; vegetation is green-dominant. Open ocean has no data (alpha 0)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    if coarse:
        # Blue Marble / Landsat mosaics: forest is dark but green-dominant, so only blue-leaning,
        # very dark (deep-water shading) or neutral-grey lake pixels count as water
        water = ((alpha < 0.5) | ((b > r + 10) & (b >= g - 6) & (lum < 170)) | (lum < 22)
                 | ((b >= r) & (b >= g - 4) & (lum < 60)) | ((b >= g + 2) & (abs(r - b) < 8) & (lum < 105)))
        if support is not None:
            near, raw = support_land(support, rgb.shape, bounds)
            water |= ~near
            water = np.where(alpha < 0.5, ~raw, water)       # outside NAIP coverage: the mosaic's coast
        return save_mask(name, water, rgb.shape, width), ~water
    water = (alpha < 0.5) | ((b > r + 8) & (b > g - 10) & (lum < 150)) | ((lum < 55) & (b >= r - 2) & (g < r + 25))
    # lagoons that read olive-green (algae, shallows) are flat and very uniform: low local variance
    lumi = Image.fromarray(lum.clip(0, 255).astype(np.uint8))
    mean = np.asarray(lumi.filter(ImageFilter.BoxBlur(6))).astype(np.float32)
    sq = np.asarray(Image.fromarray((lum ** 2 / 255).clip(0, 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(6))).astype(np.float32) * 255
    var = np.maximum(sq - mean ** 2, 0)
    water |= (var < 18) & (g > r) & (lum < 140) & (lum > 40)
    return save_mask(name, water, rgb.shape, width), ~water


def mercy(lat):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def support_land(support, shape, bounds):
    """NAIP coverage ends in square tiles over turbid shallows that read as land. Keep coarse land
    only where the continental Blue Marble mosaic (support) also has land within ~2 km.
    Returns (land within ~2 km, land) sampled on the coarse layer's grid."""
    land, (glat, glon) = support
    near = np.asarray(Image.fromarray(land.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(3))) > 0
    (lat0, lat1), (lon0, lon1) = bounds
    h, w = shape[:2]
    lon = lon0 + (np.arange(w) + 0.5) / w * (lon1 - lon0)
    my = mercy(lat1) - (np.arange(h) + 0.5) / h * (mercy(lat1) - mercy(lat0))
    gx = ((lon - glon[0]) / (glon[1] - glon[0]) * land.shape[1]).astype(int).clip(0, land.shape[1] - 1)
    gy = ((mercy(glat[1]) - my) / (mercy(glat[1]) - mercy(glat[0])) * land.shape[0]).astype(int).clip(0, land.shape[0] - 1)
    return near[gy[:, None], gx[None, :]], land[gy[:, None], gx[None, :]]


def save_mask(name, water, shape, width):
    m = Image.fromarray(np.where(water, 0, 255).astype(np.uint8))
    m = m.filter(ImageFilter.MedianFilter(9)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    m = m.resize((width, width * shape[0] // shape[1]), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2))
    file = f'{name}-mask.png'
    m.save(OUT / file, optimize=True)
    return file


def box(center, dlat, dlon):
    return center[0] - dlat, center[0] + dlat, center[1] - dlon, center[1] + dlon


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {
        'source': 'USGS The National Map, USGS Imagery Only (NAIP / Landsat / Blue Marble). Public domain.',
        'service': SERVICE,
        'projection': 'Web Mercator image; bounds are geographic (WGS-84) degrees, rows linear in Mercator y',
        'site': {'lat': SLC40[0], 'lon': SLC40[1]},
        'layers': {}
    }
    L = meta['layers']
    L['globe'] = layer('globe', *box(MID, 16.0, 18.0), 2048, 2048, 82, mask=1024, coarse=True)
    G = L['globe']
    L['wide'] = layer('wide', *box(MID, 2.6, 3.0), 2048, 2048, 82, mask=1024, coarse=True,
                      support=(G['_land'], (G['lat'], G['lon'])))
    L['region'] = layer('region', *box(MID, 0.40, 0.45), 2048, 2048, 82, mask=1024)
    L['local'] = layer('local', *box((MID[0] + 0.004, MID[1] - 0.010), 0.066, 0.062), 3072, 3584, 80, mask=1536)
    L['slc40'] = layer('slc40', *box(SLC40, 0.0062, 0.0071), 1536, 1536, 86)
    L['lz1'] = layer('lz1', *box(LZ1, 0.0062, 0.0071), 1536, 1536, 86)
    for v in L.values():
        v.pop('_land', None)
    (OUT / 'geo.json').write_text(json.dumps(meta, indent=1) + '\n')
    for p in sorted(OUT.iterdir()):
        print(f'{p.name:18s} {p.stat().st_size / 1024:8.0f} KB')


if __name__ == '__main__':
    main()
