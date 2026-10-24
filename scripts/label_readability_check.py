"""Rasterize painted pad labels through the real capture camera to check readability.

Reproduces visuals.painted_label geometry and the landing capture camera
(eye at site+(54,-70,11), target site+(0,0,8)), renders masks of the glyph
triangles at several rotation angles, and saves a comparison PNG.
"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.textpath import TextPath
from matplotlib.path import Path as Outline
from scipy.spatial import Delaunay


def label_mesh(text, y_offset, size, rot_deg):
    contours = TextPath((0, 0), text, size=size).to_polygons()
    vertices = np.unique(np.vstack(contours), axis=0)
    triangles = Delaunay(vertices).simplices
    candidates = vertices[triangles]
    samples = np.stack([candidates.mean(axis=1),
                        *(.5*(candidates[:, i]+candidates[:, (i+1) % 3]) for i in range(3))], axis=1)
    samples = .999*samples+.001*candidates.mean(axis=1)[:, None, :]
    inside = np.zeros(samples.shape[:2], dtype=bool)
    for c in contours:
        inside ^= Outline(c).contains_points(samples.reshape(-1, 2)).reshape(inside.shape)
    triangles = triangles[inside.all(axis=1)]
    vertices[:, 0] -= (vertices[:, 0].min()+vertices[:, 0].max())*.5
    vertices[:, 1] += y_offset
    theta = np.deg2rad(rot_deg)
    c, s = np.cos(theta), np.sin(theta)
    x, y = vertices[:, 0]*c-vertices[:, 1]*s, vertices[:, 0]*s+vertices[:, 1]*c
    pts = np.stack([x, y, np.full_like(x, .022)], axis=1)
    return pts, triangles


def project(pts, eye, target):
    f = target-eye
    fwd = f/np.linalg.norm(f)
    right = np.cross(fwd, [0, 0, 1.])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    rel = pts-eye
    x = rel@right
    y = rel@up
    z = rel@fwd
    # perspective divide with an fov-ish scale; near-plane clip the pad drop
    return x/z, y/z, z


def render(pts, tris, eye, target, ax=None):
    px, py, pz = project(pts, eye, target)
    keep = pz > 1.
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=110)
    ax.set_facecolor('#202020')
    tri_keep = keep[tris].all(axis=1)
    idx = np.argsort(pz[tris].min(axis=1))
    flat = tris[tri_keep][idx[tri_keep]]
    polys = np.stack([np.stack([px[t], py[t]], axis=1) for t in flat])
    from matplotlib.collections import PolyCollection
    ax.add_collection(PolyCollection(polys, facecolors='black', edgecolors='black'))
    ax.set_xlim(np.nanmin(px)-.02, np.nanmax(px)+.02)
    ax.set_ylim(np.nanmin(py)-.02, np.nanmax(py)+.02)
    ax.set_aspect('auto')
    ax.set_axis_off()


eye = np.array([54., -70., 11.])
target = np.array([0., 0., 8.])
angles = [135., 142., 118., 37., 222., 322.]
fig, axes = plt.subplots(2, len(angles)//2, figsize=(5.2*4, 9), dpi=100)
for i, ang in enumerate(angles):
    pts, tris = label_mesh('LANDING PAD 01', 15., 2.2, ang)
    ax = axes[i//3][i % 3]
    plt.sca(ax)
    render(pts, tris, eye, target, ax=ax)
    ax.set_title(f'rot {ang:g} deg')
fig.tight_layout()
fig.savefig('data/isaac/label-readability.png')
print('saved data/isaac/label-readability.png')
