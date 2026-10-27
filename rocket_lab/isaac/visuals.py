"""Native USD materials, RTX lighting, kerolox exhaust plume and launch-site environment.

Visual targets follow real launch photography: kerolox plumes are compact
white-hot cores with orange sheaths (not uniform glowing rods), pads throw
white deluge steam at liftoff, recovered boosters carry irregular soot, and
the horizon is terrain — not an infinite gray plane.
"""
from pathlib import Path
import math
import os
import numpy as np
from pxr import Gf,Sdf,UsdGeom,UsdLux,UsdShade
import carb
import omni.kit.app
import omni.usd


def attribute(prim,name,kind,value):
    prim.CreateAttribute(name,kind,custom=False).Set(value)


def smoothstep(edge0,edge1,x):
    t=float(np.clip((x-edge0)/max(edge1-edge0,1e-9),0.,1.));return t*t*(3.-2.*t)


def instancer(stage,path,prototypes,positions,scales=None,rng=None):
    """USD PointInstancer: one draw call for hundreds of placements."""
    if len(positions)==0:return None
    inst=UsdGeom.PointInstancer.Define(stage,path)
    inst.CreatePrototypesRel().SetTargets([proto.GetPath() for proto in prototypes])
    if rng is not None:inst.CreateProtoIndicesAttr(rng.integers(0,len(prototypes),len(positions)).tolist())
    inst.CreatePositionsAttr([Gf.Vec3f(*(float(v) for v in pos)) for pos in positions])
    if scales is not None:inst.CreateScalesAttr([Gf.Vec3f(*(float(v) for v in s)) for s in scales])
    # orientations default to identity; authoring half-precision quats is noise
    return inst


class NativeVisuals:
    def __init__(self,flow=False,follow=False):
        self.flow=flow;self.follow=follow;self.mode='follow' if follow else 'free'
        self.stage=omni.usd.get_context().get_stage()
        self.flow_emitters=[];self.last_camera=0
        self.cam_climb=0.
        self.landing_legs=[];self.grid_fins=[]
        self.leg_deployment=0.;self.fin_tilt=84.
        self.camp_az=2.4

    def material(self,path,color,metallic=0.,roughness=.5,emission=None,opacity=1.):
        material=UsdShade.Material.Define(self.stage,path);shader=UsdShade.Shader.Define(self.stage,path+'/Surface')
        shader.CreateIdAttr('UsdPreviewSurface')
        shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        shader.CreateInput('metallic',Sdf.ValueTypeNames.Float).Set(metallic)
        shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(roughness)
        if opacity<1.:shader.CreateInput('opacity',Sdf.ValueTypeNames.Float).Set(opacity)
        if emission:shader.CreateInput('emissiveColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emission))
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
        return material

    def painted_sign(self,path,text,material,azimuth_deg,size=4.2,z_base=5.2):
        """Vertical rim sign at the pad edge, rotated to face its coverage camera.
        Glyphs stay upright by construction; single-sided so a wrong-facing
        plane is invisible instead of mirrored."""
        from matplotlib.textpath import TextPath
        from matplotlib.path import Path as Outline
        from scipy.spatial import Delaunay
        contours=TextPath((0,0),text,size=size).to_polygons()
        if not contours:return
        vertices=np.unique(np.vstack(contours),axis=0);triangles=Delaunay(vertices).simplices
        candidates=vertices[triangles]
        samples=np.stack([candidates.mean(axis=1),*(.5*(candidates[:,index]+candidates[:,(index+1)%3]) for index in range(3))],axis=1)
        samples=.999*samples+.001*candidates.mean(axis=1)[:,None,:]
        inside=np.zeros(samples.shape[:2],dtype=bool)
        for contour in contours:inside^=Outline(contour).contains_points(samples.reshape(-1,2)).reshape(inside.shape)
        triangles=triangles[inside.all(axis=1)]
        vertices[:,0]-=(vertices[:,0].min()+vertices[:,0].max())*.5
        theta=np.deg2rad(azimuth_deg)
        rim_pos=15.*np.array([np.cos(np.deg2rad(azimuth_deg+90.)),np.sin(np.deg2rad(azimuth_deg+90.))])
        sign=UsdGeom.Mesh.Define(self.stage,path)
        sign.CreatePointsAttr([Gf.Vec3f(float(x),0.,float(y)+z_base) for x,y in vertices])
        sign.CreateFaceVertexCountsAttr([3]*len(triangles));sign.CreateFaceVertexIndicesAttr(triangles.ravel().tolist())
        sign.CreateDoubleSidedAttr(False);sign.CreateSubdivisionSchemeAttr('none')
        sign.AddTranslateOp().Set(Gf.Vec3d(float(rim_pos[0]),float(rim_pos[1]),0))
        sign.AddRotateZOp().Set(float(azimuth_deg))
        UsdShade.MaterialBindingAPI.Apply(sign.GetPrim()).Bind(material)

    def painted_label(self,path,text,material,y_offset=-17.,size=2.4,rot_deg=135.):
        """Triangulated font outlines on the pad surface; aligned with camera viewing angle."""
        from matplotlib.textpath import TextPath
        from matplotlib.path import Path as Outline
        from scipy.spatial import Delaunay
        contours=TextPath((0,0),text,size=size).to_polygons()
        if not contours:return
        vertices=np.unique(np.vstack(contours),axis=0);triangles=Delaunay(vertices).simplices
        candidates=vertices[triangles]
        samples=np.stack([candidates.mean(axis=1),*(.5*(candidates[:,index]+candidates[:,(index+1)%3]) for index in range(3))],axis=1)
        samples=.999*samples+.001*candidates.mean(axis=1)[:,None,:]
        inside=np.zeros(samples.shape[:2],dtype=bool)
        for contour in contours:inside^=Outline(contour).contains_points(samples.reshape(-1,2)).reshape(inside.shape)
        triangles=triangles[inside.all(axis=1)]
        vertices[:,0]-=(vertices[:,0].min()+vertices[:,0].max())*.5;vertices[:,1]+=y_offset
        if rot_deg!=0.:
            theta=np.deg2rad(rot_deg);c,s=np.cos(theta),np.sin(theta)
            rx=vertices[:,0]*c-vertices[:,1]*s;ry=vertices[:,0]*s+vertices[:,1]*c
            vertices[:,0]=rx;vertices[:,1]=ry
        label=UsdGeom.Mesh.Define(self.stage,path)
        label.CreatePointsAttr([Gf.Vec3f(float(x),float(y),.022) for x,y in vertices])
        label.CreateFaceVertexCountsAttr([3]*len(triangles));label.CreateFaceVertexIndicesAttr(triangles.ravel().tolist())
        label.CreateDoubleSidedAttr(True);label.CreateSubdivisionSchemeAttr('none')
        UsdShade.MaterialBindingAPI.Apply(label.GetPrim()).Bind(material)

    def setup(self,physics):
        self.physics=physics
        # ====== PBR AEROSPACE MATERIALS ======
        white=self.material('/World/Looks/Booster',(.86,.88,.90),.12,.28)
        dark=self.material('/World/Looks/CarbonComposite',(.06,.065,.075),.05,.55)
        inconel=self.material('/World/Looks/InconelAlloy',(.16,.17,.19),.90,.22)
        chrome=self.material('/World/Looks/ChromePiston',(.92,.94,.96),.98,.06)
        titanium=self.material('/World/Looks/TitaniumGrid',(.24,.25,.27),.92,.24)
        satellite=self.material('/World/Looks/GoldKapton',(.85,.65,.12),.88,.18)
        trim=self.material('/World/Looks/Trim',(.045,.055,.075),.45,.3)
        concrete=self.material('/World/Looks/Concrete',(.14,.16,.18),.02,.88)
        hazard_yellow=self.material('/World/Looks/HazardYellow',(1.0,.82,.0),.0,.35)
        hazard_black=self.material('/World/Looks/HazardBlack',(.02,.02,.02),.0,.85)
        landing_green=self.material('/World/Looks/LandingGreen',(.42,.92,.68),.0,.4)
        markings=self.material('/World/Looks/Markings',(.94,.95,.96),0.,.6)
        scorch_mat=self.material('/World/Looks/Scorch',(.08,.09,.10),.02,.95)
        # Recovered-booster soot: irregular dark deposits on the light composite
        soot=self.material('/World/Looks/BoosterSoot',(.05,.05,.06),0.,.85)

        # Terrain, vegetation and horizon tones
        grass=self.material('/World/Looks/TerrainGrass',(.10,.145,.085),0.,.95)
        grass_dark=self.material('/World/Looks/TerrainGrassDark',(.075,.11,.065),0.,.95)
        grass_dry=self.material('/World/Looks/TerrainGrassDry',(.20,.17,.115),0.,.92)
        soil=self.material('/World/Looks/TerrainSoil',(.16,.13,.10),0.,.92)
        grass_mix=(grass_dark,grass_dry,soil,grass_dark)
        foliage=self.material('/World/Looks/Foliage',(.09,.13,.07),0.,.9)
        foliage_dark=self.material('/World/Looks/FoliageDark',(.065,.095,.055),0.,.9)
        trunk=self.material('/World/Looks/Trunk',(.16,.12,.09),0.,.9)
        rock=self.material('/World/Looks/Rock',(.22,.22,.21),.02,.85)
        hill=self.material('/World/Looks/DistantHill',(.115,.15,.13),0.,.95)
        # Aerial perspective: far ridges shift toward the sky color.
        hill_distant=self.material('/World/Looks/DistantHillBlue',(.22,.28,.34),0.,.95)
        sea=self.material('/World/Looks/Ocean',(.04,.09,.11),.35,.14)
        cloud=self.material('/World/Looks/CloudPuff',(.93,.95,.98),0.,1.,opacity=.92)
        steam=self.material('/World/Looks/DelugeSteam',(.86,.88,.92),0.,1.,opacity=.08)
        road=self.material('/World/Looks/AsphaltRoad',(.09,.09,.095),0.,.95)

        # Kerolox plume: bright compact white core, transparent orange sheath,
        # wide faint veil for altitude overexpansion (real-time RTX emission
        # is in HDR units; the previous 75..55 values washed every surface
        # toward white-gold and needed a three-order magnitude reduction).
        # Emission levels are tuned against RTX bloom: the white-hot core at
        # the previous 16 HDR units flooded close-up shots with a bloom halo.
        flame_core=self.material('/World/Looks/PlumeCore',(1.,.97,.9),.0,.4,emission=(7.,6.2,4.6))
        flame_sheath=self.material('/World/Looks/PlumeSheath',(.98,.5,.12),.0,.5,emission=(2.2,.8,.12),opacity=.55)
        flame_veil=self.material('/World/Looks/PlumeVeil',(1.,.66,.28),.0,.7,emission=(.5,.18,.03),opacity=.16)
        flame_diamond=self.material('/World/Looks/PlumeDiamond',(1.,.93,.75),.0,.4,emission=(4.2,3.4,2.4),opacity=.6)
        ground_glow_mat=self.material('/World/Looks/GroundFlameGlow',(1.,.42,.06),.0,.6,emission=(1.8,.6,.07),opacity=.32)

        # Vehicle bindings
        UsdShade.MaterialBindingAPI.Apply(self.stage.GetPrimAtPath('/World/Booster')).Bind(white)
        UsdShade.MaterialBindingAPI.Apply(self.stage.GetPrimAtPath('/World/Payload')).Bind(satellite)
        payload_hull=UsdGeom.Cylinder(self.stage.GetPrimAtPath('/World/Payload/Hull'))
        payload_hull.CreateVisibilityAttr('invisible')

        # Physics-only foot colliders: hide from RTX, the leg footpads render.
        for foot_index in range(4):
            foot_prim=self.stage.GetPrimAtPath(f'/World/Booster/Foot{foot_index}')
            if foot_prim and foot_prim.IsValid():UsdGeom.Imageable(foot_prim).GetVisibilityAttr().Set('invisible')

        # Upper Stage Fairing & Satellite
        fairing=UsdGeom.Cylinder.Define(self.stage,'/World/Payload/Fairing')
        fairing.CreateAxisAttr('Z');fairing.CreateRadiusAttr(1.8);fairing.CreateHeightAttr(7.)
        fairing.AddTranslateOp().Set(Gf.Vec3d(0,0,-1.))
        tip=UsdGeom.Cone.Define(self.stage,'/World/Payload/Nose')
        tip.CreateAxisAttr('Z');tip.CreateRadiusAttr(1.8);tip.CreateHeightAttr(2.4)
        tip.AddTranslateOp().Set(Gf.Vec3d(0,0,3.7))
        UsdShade.MaterialBindingAPI.Apply(fairing.GetPrim()).Bind(white)
        UsdShade.MaterialBindingAPI.Apply(tip.GetPrim()).Bind(white)

        # Upper stage vacuum engine bell
        vac_nozzle=UsdGeom.Cone.Define(self.stage,'/World/Payload/VacEngine')
        vac_nozzle.CreateAxisAttr('Z');vac_nozzle.CreateRadiusAttr(1.1);vac_nozzle.CreateHeightAttr(1.6)
        vac_nozzle.AddTranslateOp().Set(Gf.Vec3d(0,0,-5.2));vac_nozzle.AddRotateXOp().Set(180.)
        UsdShade.MaterialBindingAPI.Apply(vac_nozzle.GetPrim()).Bind(inconel)

        # Cold-gas RCS roll & attitude thrusters (8 nozzles)
        for index,(x,y,z) in enumerate(((1.8,.25,8.),(1.8,-.25,8.),(-1.8,.25,8.),(-1.8,-.25,8.),
                                       (1.8,.25,-12.),(1.8,-.25,-12.),(-1.8,.25,-12.),(-1.8,-.25,-12.))):
            jet=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/RollJet{index}')
            jet.CreateAxisAttr('Y');jet.CreateRadiusAttr(.12);jet.CreateHeightAttr(.38)
            jet.AddTranslateOp().Set(Gf.Vec3d(x,y,z))
            UsdShade.MaterialBindingAPI.Apply(jet.GetPrim()).Bind(dark)

        # Interstage section with hot-staging lattice vent panels
        collar=UsdGeom.Cylinder.Define(self.stage,'/World/Booster/Interstage')
        collar.CreateAxisAttr('Z');collar.CreateRadiusAttr(physics.v['radius']+.008);collar.CreateHeightAttr(3.2)
        collar.AddTranslateOp().Set(Gf.Vec3d(0,0,physics.half-1.6))
        UsdShade.MaterialBindingAPI.Apply(collar.GetPrim()).Bind(dark)

        for vent_idx in range(8):
            vent_angle=vent_idx*np.pi/4
            vent=UsdGeom.Cube.Define(self.stage,f'/World/Booster/Interstage/Vent{vent_idx}')
            vent.AddTranslateOp().Set(Gf.Vec3d(float(np.cos(vent_angle)*1.81),float(np.sin(vent_angle)*1.81),0.))
            vent.AddRotateZOp().Set(float(np.rad2deg(vent_angle)))
            vent.AddScaleOp().Set(Gf.Vec3f(.06,.4,.55))
            UsdShade.MaterialBindingAPI.Apply(vent.GetPrim()).Bind(trim)

        # Structural circumferential weld rings along the fuselage
        for z in (-16.,-10.,-4.,2.,8.,14.):
            band=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/Band{int(z+20)}')
            band.CreateAxisAttr('Z');band.CreateRadiusAttr(physics.v['radius']+.015);band.CreateHeightAttr(.045)
            band.AddTranslateOp().Set(Gf.Vec3d(0,0,z));UsdShade.MaterialBindingAPI.Apply(band.GetPrim()).Bind(trim)

        # Dual aerodynamic raceways / avionics conduits along opposite sides
        for idx,x_sign in enumerate((1,-1)):
            side='Right' if x_sign>0 else 'Left'
            raceway=UsdGeom.Cube.Define(self.stage,f'/World/Booster/Raceway_{side}')
            raceway.AddTranslateOp().Set(Gf.Vec3d(float(x_sign*(physics.v['radius']+.06)),0,0))
            raceway.AddScaleOp().Set(Gf.Vec3f(.08,.16,14.5))
            UsdShade.MaterialBindingAPI.Apply(raceway.GetPrim()).Bind(white)
            cap_top=UsdGeom.Cone.Define(self.stage,f'/World/Booster/Raceway_{side}_CapTop')
            cap_top.CreateAxisAttr('Z');cap_top.CreateRadiusAttr(.12);cap_top.CreateHeightAttr(.7)
            cap_top.AddTranslateOp().Set(Gf.Vec3d(float(x_sign*(physics.v['radius']+.06)),0,14.8))
            UsdShade.MaterialBindingAPI.Apply(cap_top.GetPrim()).Bind(dark)

        # Recovered-booster soot: engine scorch around the base and irregular
        # vertical plume staining that reaches partway up the light body, like
        # real kerolox boosters returning from a mission — never a full repaint.
        soot_band=UsdGeom.Cylinder.Define(self.stage,'/World/Booster/SootBase')
        soot_band.CreateAxisAttr('Z');soot_band.CreateRadiusAttr(physics.v['radius']+.006);soot_band.CreateHeightAttr(9.)
        soot_band.AddTranslateOp().Set(Gf.Vec3d(0,0,-physics.half+4.5))
        UsdShade.MaterialBindingAPI.Apply(soot_band.GetPrim()).Bind(soot)
        streak_rng=np.random.default_rng(11)
        for streak in range(7):
            angle=streak*2*np.pi/7+.22
            height=float(streak_rng.uniform(3.,9.5))
            mark=UsdGeom.Cube.Define(self.stage,f'/World/Booster/SootStreak{streak}')
            mark.AddTranslateOp().Set(Gf.Vec3d(float(np.cos(angle)*(physics.v['radius']+.012)),
                                               float(np.sin(angle)*(physics.v['radius']+.012)),
                                               -physics.half+height/2+.8))
            mark.AddRotateZOp().Set(float(np.rad2deg(angle)))
            mark.AddScaleOp().Set(Gf.Vec3f(.14,.5,height))
            UsdShade.MaterialBindingAPI.Apply(mark.GetPrim()).Bind(soot)

        # ====== 4 HYPERSONIC TITANIUM GRID FINS (folded on ascent) ======
        self.grid_fins=[]
        for fin_idx in range(4):
            fin_angle=fin_idx*np.pi/2
            fin_xform=UsdGeom.Xform.Define(self.stage,f'/World/Booster/GridFin{fin_idx}')
            fin_xform.AddTranslateOp().Set(Gf.Vec3d(float(np.cos(fin_angle)*(physics.v['radius']+.15)),
                                                   float(np.sin(fin_angle)*(physics.v['radius']+.15)),
                                                   physics.half-3.2))
            fin_xform.AddRotateZOp().Set(float(np.rad2deg(fin_angle)))
            fin_tilt=fin_xform.AddRotateXOp();fin_tilt.Set(84.) # folded flush against the hull
            self.grid_fins.append(fin_tilt)

            hinge=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/GridFin{fin_idx}/Hinge')
            hinge.CreateAxisAttr('X');hinge.CreateRadiusAttr(.16);hinge.CreateHeightAttr(.45)
            UsdShade.MaterialBindingAPI.Apply(hinge.GetPrim()).Bind(dark)

            blade=UsdGeom.Cube.Define(self.stage,f'/World/Booster/GridFin{fin_idx}/Blade')
            blade.AddTranslateOp().Set(Gf.Vec3d(.65,0,0));blade.AddScaleOp().Set(Gf.Vec3f(.65,.45,.05))
            UsdShade.MaterialBindingAPI.Apply(blade.GetPrim()).Bind(titanium)
            for sub_i in range(3):
                rib=UsdGeom.Cube.Define(self.stage,f'/World/Booster/GridFin{fin_idx}/Rib{sub_i}')
                rib.AddTranslateOp().Set(Gf.Vec3d(.35+sub_i*.28,0,0));rib.AddScaleOp().Set(Gf.Vec3f(.02,.42,.06))
                UsdShade.MaterialBindingAPI.Apply(rib.GetPrim()).Bind(dark)

        # ====== DEPLOYABLE ARTICULATED LANDING LEGS (4X) ======
        self.landing_legs=[]
        for i,angle_deg in enumerate((45,135,225,315)):
            rad=np.deg2rad(angle_deg)
            leg_root=UsdGeom.Xform.Define(self.stage,f'/World/Booster/LegAssembly{i}')
            # Base pivot point on the booster skirt
            leg_root.AddTranslateOp().Set(Gf.Vec3d(float(np.cos(rad)*1.8),float(np.sin(rad)*1.8),-physics.half+7.0))
            leg_root.AddRotateZOp().Set(float(angle_deg))
            leg_deploy=leg_root.AddRotateYOp();leg_deploy.Set(0.) # 0 = folded against hull, 32 deg = deployed
            self.landing_legs.append(leg_deploy)

            strut=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/LegAssembly{i}/MainStrut')
            strut.CreateAxisAttr('Z');strut.CreateRadiusAttr(.14);strut.CreateHeightAttr(7.5)
            strut.AddTranslateOp().Set(Gf.Vec3d(0,0,-3.75))
            UsdShade.MaterialBindingAPI.Apply(strut.GetPrim()).Bind(dark)

            piston=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/LegAssembly{i}/Piston')
            piston.CreateAxisAttr('Z');piston.CreateRadiusAttr(.09);piston.CreateHeightAttr(4.5)
            piston.AddTranslateOp().Set(Gf.Vec3d(.18,0,-4.5))
            UsdShade.MaterialBindingAPI.Apply(piston.GetPrim()).Bind(chrome)

            foot=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/LegAssembly{i}/Footpad')
            foot.CreateAxisAttr('Z');foot.CreateRadiusAttr(.45);foot.CreateHeightAttr(.08)
            foot.AddTranslateOp().Set(Gf.Vec3d(0,0,-7.4))
            UsdShade.MaterialBindingAPI.Apply(foot.GetPrim()).Bind(dark)

        # ====== OCTAWEB 9-ENGINE CLUSTER & HEAT SHIELD ======
        heatshield=UsdGeom.Cone.Define(self.stage,'/World/Booster/HeatShield')
        heatshield.CreateAxisAttr('Z');heatshield.CreateRadiusAttr(physics.v['radius']+.05);heatshield.CreateHeightAttr(.65)
        heatshield.AddTranslateOp().Set(Gf.Vec3d(0,0,-physics.half+.32));heatshield.AddRotateXOp().Set(180.)
        UsdShade.MaterialBindingAPI.Apply(heatshield.GetPrim()).Bind(dark)

        # Center gimbaling engine
        nozzle=UsdGeom.Xform.Define(self.stage,'/World/Booster/Nozzle')
        nozzle.AddTranslateOp().Set(Gf.Vec3d(0,0,-physics.engine_lever));self.nozzle_rotation=nozzle.AddOrientOp()
        UsdShade.MaterialBindingAPI.Apply(nozzle.GetPrim()).Bind(inconel)

        chamber=UsdGeom.Cylinder.Define(self.stage,'/World/Booster/Nozzle/ThrustChamber')
        chamber.CreateAxisAttr('Z');chamber.CreateRadiusAttr(.36);chamber.CreateHeightAttr(1.4)
        chamber.AddTranslateOp().Set(Gf.Vec3d(0,0,.7))
        UsdShade.MaterialBindingAPI.Apply(chamber.GetPrim()).Bind(inconel)

        # Axisymmetric contoured bell nozzle
        profile=[(.36,0),(.40,-.3),(.52,-.75),(.72,-1.2),(.92,-1.65)]
        points=[];indices=[];counts=[];segments=48
        for radius,z in profile:
            for i in range(segments):
                angle=2*np.pi*i/segments;points.append(Gf.Vec3f(float(radius*np.cos(angle)),float(radius*np.sin(angle)),z))
        for row in range(len(profile)-1):
            for i in range(segments):
                indices.extend([row*segments+i,row*segments+(i+1)%segments,(row+1)*segments+(i+1)%segments,(row+1)*segments+i]);counts.append(4)
        mesh=UsdGeom.Mesh.Define(self.stage,'/World/Booster/Nozzle/Bell')
        mesh.CreatePointsAttr(points);mesh.CreateFaceVertexIndicesAttr(indices);mesh.CreateFaceVertexCountsAttr(counts)
        mesh.CreateDoubleSidedAttr(True);UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(inconel)

        # Outer ring of 8 auxiliary engine bells (Octaweb layout)
        for aux_i in range(8):
            aux_angle=aux_i*np.pi/4
            aux_x=float(np.cos(aux_angle)*1.18);aux_y=float(np.sin(aux_angle)*1.18)
            aux_bell=UsdGeom.Cone.Define(self.stage,f'/World/Booster/AuxEngine{aux_i}')
            aux_bell.CreateAxisAttr('Z');aux_bell.CreateRadiusAttr(.42);aux_bell.CreateHeightAttr(1.25)
            aux_bell.AddTranslateOp().Set(Gf.Vec3d(aux_x,aux_y,-physics.half+.15));aux_bell.AddRotateXOp().Set(180.)
            UsdShade.MaterialBindingAPI.Apply(aux_bell.GetPrim()).Bind(inconel)

        # ====== KEROLOX PLUME: CORE / SHEATH / VEIL + SHOCK CELLS ======
        plume_root=UsdGeom.Xform.Define(self.stage,'/World/Booster/Nozzle/Plume')
        plume_root.AddTranslateOp().Set(Gf.Vec3d(0,0,-1.65))
        self.plume_scale=plume_root.AddScaleOp();self.plume_scale.Set(Gf.Vec3f(.001,.001,.001))

        # White-hot core
        core=UsdGeom.Cone.Define(self.stage,'/World/Booster/Nozzle/Plume/Core')
        core.CreateAxisAttr('Z');core.CreateRadiusAttr(.52);core.CreateHeightAttr(7.5)
        core.AddTranslateOp().Set(Gf.Vec3d(0,0,-3.75));core.AddRotateXOp().Set(180.)
        UsdShade.MaterialBindingAPI.Apply(core.GetPrim()).Bind(flame_core)
        # Orange sheath (layered under the core, transparent per frame)
        sheath=UsdGeom.Cone.Define(self.stage,'/World/Booster/Nozzle/Plume/Sheath')
        sheath.CreateAxisAttr('Z');sheath.CreateRadiusAttr(1.05);sheath.CreateHeightAttr(11.)
        sheath.AddTranslateOp().Set(Gf.Vec3d(0,0,-5.5));sheath.AddRotateXOp().Set(180.)
        UsdShade.MaterialBindingAPI.Apply(sheath.GetPrim()).Bind(flame_sheath)
        # Veil: altitude-dependent overexpansion envelope driven by xform scale
        # (a sibling of plume_root so it never inherits the plume scale twice)
        veil_root=UsdGeom.Xform.Define(self.stage,'/World/Booster/Nozzle/PlumeVeil')
        veil_root.AddTranslateOp().Set(Gf.Vec3d(0,0,-1.65))
        self.veil_scale=veil_root.AddScaleOp();self.veil_scale.Set(Gf.Vec3f(.001,.001,.001))
        veil=UsdGeom.Cone.Define(self.stage,'/World/Booster/Nozzle/PlumeVeil/Shape')
        veil.CreateAxisAttr('Z');veil.CreateRadiusAttr(2.4);veil.CreateHeightAttr(16.)
        veil.AddTranslateOp().Set(Gf.Vec3d(0,0,-8.));veil.AddRotateXOp().Set(180.)
        self.sheath_shader=UsdShade.Shader(self.stage.GetPrimAtPath('/World/Looks/PlumeSheath/Surface'))
        self.veil_shader=UsdShade.Shader(self.stage.GetPrimAtPath('/World/Looks/PlumeVeil/Surface'))
        self.diamond_shader=UsdShade.Shader(self.stage.GetPrimAtPath('/World/Looks/PlumeDiamond/Surface'))
        UsdShade.MaterialBindingAPI.Apply(veil.GetPrim()).Bind(flame_veil)

        # Shock diamond cells with fading down-stream brightness
        self.diamonds=[]
        for d_idx,d_z in enumerate((-1.,-2.3,-3.7,-5.2,-6.7)):
            dia=UsdGeom.Cone.Define(self.stage,f'/World/Booster/Nozzle/Plume/Diamond{d_idx}')
            dia.CreateAxisAttr('Z');dia.CreateRadiusAttr(.34-d_idx*.05);dia.CreateHeightAttr(.75)
            dia.AddTranslateOp().Set(Gf.Vec3d(0,0,d_z));dia.AddRotateXOp().Set(180.)
            UsdShade.MaterialBindingAPI.Apply(dia.GetPrim()).Bind(flame_diamond)
            self.diamonds.append((dia,1.-d_idx*.14))

        # Dynamic RTX lighting from the plume (bounded so ground colors survive)
        self.flame_light=UsdLux.SphereLight.Define(self.stage,'/World/Booster/Nozzle/Glow')
        self.flame_light.CreateRadiusAttr(3.5);self.flame_light.CreateColorAttr(Gf.Vec3f(1.,.56,.2));self.flame_light.CreateIntensityAttr(0.)
        self.flame_light.AddTranslateOp().Set(Gf.Vec3d(0,0,-6.))

        # ====== TERRAIN: DISPLACED COASTAL PLAIN, OCEAN, RIDGE LINES ======
        # PhysX keeps its 20 km ground plane collider everywhere; /World/Terrain
        # is display-only. The plain is three displaced annulus meshes (inner
        # grass, midland mix, dry outland) that blend to dead flat around the
        # pads, then an ocean horizon and two ridge lines for depth.
        def displaced_ring(path,inner,outer,rows,columns,mat,roughness_amplitude,flat_radius):
            ring=UsdGeom.Mesh.Define(self.stage,path)
            points=[];counts=[];indices=[]
            rng=np.random.default_rng(4200+int(inner))
            phase=rng.uniform(0,2*np.pi,columns);frequency=rng.uniform(1.5,3.5,3)
            for row in range(rows+1):
                radius=inner+(outer-inner)*row/rows
                blend=smoothstep(flat_radius,flat_radius+1400.,radius)
                for column in range(columns):
                    angle=2*np.pi*column/columns
                    bump=(np.sin(angle*frequency[0]+phase[0])+np.sin(angle*frequency[1]+phase[1])
                          +.6*np.sin(angle*frequency[2]+phase[2]))/2.6
                    height=roughness_amplitude*blend*(bump+.35*rng.uniform(-1,1)*blend)
                    points.append(Gf.Vec3f(float(radius*np.cos(angle)),float(radius*np.sin(angle)),float(height)))
            for row in range(rows):
                for column in range(columns):
                    a=row*columns+column;b=row*columns+(column+1)%columns
                    c=(row+1)*columns+(column+1)%columns;d=(row+1)*columns+column
                    indices.extend([a,b,c,d]);counts.append(4)
            ring.CreatePointsAttr(points);ring.CreateFaceVertexIndicesAttr(indices);ring.CreateFaceVertexCountsAttr(counts)
            ring.CreateDoubleSidedAttr(False);ring.CreateSubdivisionSchemeAttr('none')
            UsdShade.MaterialBindingAPI.Apply(ring.GetPrim()).Bind(mat)
            return ring
        displaced_ring('/World/Terrain/PlainInner',60.,2400.,10,96,grass,2.2,260.)
        displaced_ring('/World/Terrain/PlainMid',2400.,6200.,8,96,grass_mix[1],7.5,260.)
        displaced_ring('/World/Terrain/PlainOuter',6200.,10500.,6,96,grass_mix[2],16.,260.)

        # Distant ridges: two noise-profiled triangle-fan rings past the plain,
        # blue-shifted with distance so aerial perspective reads correctly.
        def ridge_ring(path,radius_start,radius_end,height_lo,height_high,mat,seed):
            rng=np.random.default_rng(seed)
            points=[];counts=[];indices=[];segments=120
            crest=rng.uniform(height_lo,height_high,segments)
            crest=np.convolve(np.r_[crest[-6:],crest,crest[:6]],np.ones(9)/9.,mode='same')[6:-6]
            for segment in range(segments):
                angle0=2*np.pi*segment/segments;angle1=2*np.pi*(segment+1)/segments
                base0=radius_start+rng.uniform(0.,radius_end-radius_start)
                base1=radius_start+rng.uniform(0.,radius_end-radius_start)
                peak0=base0+520.+crest[segment];peak1=base1+520.+crest[(segment+1)%segments]
                anchor=segment*4
                points.extend([Gf.Vec3f(float(base0*np.cos(angle0)),float(base0*np.sin(angle0)),0.),
                               Gf.Vec3f(float(peak0*np.cos(angle0)),float(peak0*np.sin(angle0)),float(crest[segment])),
                               Gf.Vec3f(float(peak1*np.cos(angle1)),float(peak1*np.sin(angle1)),float(crest[(segment+1)%segments])),
                               Gf.Vec3f(float(base1*np.cos(angle1)),float(base1*np.sin(angle1)),0.)])
                counts.append(4);indices.extend([anchor,anchor+1,anchor+2,anchor+3])
            ridge=UsdGeom.Mesh.Define(self.stage,path)
            ridge.CreatePointsAttr(points);ridge.CreateFaceVertexCountsAttr(counts);ridge.CreateFaceVertexIndicesAttr(indices)
            ridge.CreateDoubleSidedAttr(True);ridge.CreateSubdivisionSchemeAttr('none')
            UsdShade.MaterialBindingAPI.Apply(ridge.GetPrim()).Bind(mat)
        ridge_ring('/World/Terrain/RidgeNear',10200.,11000.,140.,380.,hill,77)
        ridge_ring('/World/Terrain/RidgeFar',11400.,12300.,260.,620.,hill_distant,78)

        # Ocean horizon beyond the ridges: one dark disc to the world edge.
        ocean=UsdGeom.Cylinder.Define(self.stage,'/World/Terrain/Ocean')
        ocean.CreateAxisAttr('Z');ocean.CreateRadiusAttr(38000.);ocean.CreateHeightAttr(.1)
        ocean.AddTranslateOp().Set(Gf.Vec3d(0,0,-.45))
        UsdShade.MaterialBindingAPI.Apply(ocean.GetPrim()).Bind(sea)

        # Vegetation: layered fir, broadleaf and boulder prototypes instanced
        # across the coastal plain, 160 m clear of each pad.
        UsdGeom.Xform.Define(self.stage,'/World/Terrain/TreeProto1');UsdGeom.Xform.Define(self.stage,'/World/Terrain/TreeProto2')
        UsdGeom.Xform.Define(self.stage,'/World/Terrain/ScrubProto')
        trunk1=UsdGeom.Cylinder.Define(self.stage,'/World/Terrain/TreeProto1/Trunk')
        trunk1.CreateAxisAttr('Z');trunk1.CreateRadiusAttr(.4);trunk1.CreateHeightAttr(5.)
        trunk1.AddTranslateOp().Set(Gf.Vec3d(0,0,2.5))
        UsdShade.MaterialBindingAPI.Apply(trunk1.GetPrim()).Bind(trunk)
        for tier,(tier_radius,tier_z,tier_height) in enumerate(((2.1,5.9,3.4),(1.6,7.6,3.),(1.05,9.1,2.8))):
            tier_cone=UsdGeom.Cone.Define(self.stage,f'/World/Terrain/TreeProto1/Tier{tier}')
            tier_cone.CreateAxisAttr('Z');tier_cone.CreateRadiusAttr(tier_radius);tier_cone.CreateHeightAttr(tier_height)
            tier_cone.AddTranslateOp().Set(Gf.Vec3d(0,0,tier_z))
            UsdShade.MaterialBindingAPI.Apply(tier_cone.GetPrim()).Bind(foliage if tier%2==0 else foliage_dark)
        trunk2=UsdGeom.Cylinder.Define(self.stage,'/World/Terrain/TreeProto2/Trunk')
        trunk2.CreateAxisAttr('Z');trunk2.CreateRadiusAttr(.28);trunk2.CreateHeightAttr(5.)
        trunk2.AddTranslateOp().Set(Gf.Vec3d(0,0,2.5))
        UsdShade.MaterialBindingAPI.Apply(trunk2.GetPrim()).Bind(trunk)
        canopy2=UsdGeom.Sphere.Define(self.stage,'/World/Terrain/TreeProto2/Canopy')
        canopy2.CreateRadiusAttr(1.6)
        canopy2.AddTranslateOp().Set(Gf.Vec3d(0,0,6.1))
        canopy2.AddScaleOp().Set(Gf.Vec3f(1.,1.,.62))
        UsdShade.MaterialBindingAPI.Apply(canopy2.GetPrim()).Bind(foliage_dark)
        scrub=UsdGeom.Sphere.Define(self.stage,'/World/Terrain/ScrubProto/Bush')
        scrub.CreateRadiusAttr(1.)
        scrub.AddTranslateOp().Set(Gf.Vec3d(0,0,.35));scrub.AddScaleOp().Set(Gf.Vec3f(1.,1.,.55))
        UsdShade.MaterialBindingAPI.Apply(scrub.GetPrim()).Bind(grass_dry)
        rock_proto=UsdGeom.Sphere.Define(self.stage,'/World/Terrain/RockProto')
        rock_proto.CreateRadiusAttr(1.)
        rock_proto.AddScaleOp().Set(Gf.Vec3f(1.,1.,.6))
        UsdShade.MaterialBindingAPI.Apply(rock_proto.GetPrim()).Bind(rock)

        launch_xy=physics.cfg['mission'].get('launch',[0,0])[:2]
        landing_xy=physics.cfg['mission']['pad'][:2]

        scatter=np.random.default_rng(17)
        positions=[]
        corridor=.5*(np.asarray(launch_xy)+np.asarray(landing_xy))
        while len(positions)<1500:
            # Denser vegetation along the pad corridor, sparse elsewhere.
            if scatter.random()<.4:
                around=corridor+scatter.uniform(-900.,900.,2)
                x,y=float(around[0]),float(around[1])
                if not 110.<math.hypot(x,y)<8300.:continue
            else:
                angle=scatter.uniform(0,2*np.pi);dist=scatter.uniform(110.,8300.)
                x,y=dist*np.cos(angle),dist*np.sin(angle)
            if math.hypot(x-launch_xy[0],y-launch_xy[1])<=160.:continue
            if math.hypot(x-landing_xy[0],y-landing_xy[1])<=160.:continue
            positions.append((x,y,0.))
        scales=[]
        for index in range(len(positions)):
            kind=scatter.random()
            span=scatter.uniform(.7,2.3)
            scales.append((span,span,span) if kind<.45 else (scatter.uniform(.5,2.),scatter.uniform(.5,2.),scatter.uniform(.25,.9)))
        instancer(self.stage,'/World/Terrain/Vegetation',
            [UsdGeom.Xform(self.stage.GetPrimAtPath('/World/Terrain/TreeProto1')),
             UsdGeom.Xform(self.stage.GetPrimAtPath('/World/Terrain/TreeProto2')),
             rock_proto],positions,scales,rng=scatter)
        scrub_positions=[]
        while len(scrub_positions)<2600:
            angle=scatter.uniform(0,2*np.pi);dist=scatter.uniform(150.,6500.)
            x,y=dist*np.cos(angle),dist*np.sin(angle)
            if math.hypot(x-launch_xy[0],y-launch_xy[1])<=150.:continue
            if math.hypot(x-landing_xy[0],y-landing_xy[1])<=150.:continue
            scrub_positions.append((x,y,0.))
        scrub_scales=[(scatter.uniform(.8,2.6),scatter.uniform(.8,2.6),scatter.uniform(.5,1.4)) for _ in scrub_positions]
        instancer(self.stage,'/World/Terrain/Scrub',
            [UsdGeom.Xform(self.stage.GetPrimAtPath('/World/Terrain/ScrubProto'))],
            scrub_positions,scrub_scales,rng=scatter)

        # Dust access roads between the pads (visual only)
        road_center=.5*(np.asarray(launch_xy)+np.asarray(landing_xy))
        length=float(np.linalg.norm(np.asarray(landing_xy)-np.asarray(launch_xy)))+80.
        road_dir=np.asarray(landing_xy)-np.asarray(launch_xy)
        road=UsdGeom.Cube.Define(self.stage,'/World/Terrain/AccessRoad')
        road.AddTranslateOp().Set(Gf.Vec3d(float(road_center[0]),float(road_center[1]),.004))
        road.AddRotateZOp().Set(float(np.rad2deg(np.arctan2(road_dir[1],road_dir[0]))))
        road.AddScaleOp().Set(Gf.Vec3f(length/2,4.,0.006))
        UsdShade.MaterialBindingAPI.Apply(road.GetPrim()).Bind(soil)

        # ====== CLOUD DECK: flattened cumulus clumps between 1,150 and 1,900 m ======
        puff=UsdGeom.Sphere.Define(self.stage,'/World/Clouds/PuffProto');puff.CreateRadiusAttr(1.)
        UsdShade.MaterialBindingAPI.Apply(puff.GetPrim()).Bind(cloud)
        cloud_positions=[];cloud_scales=[]
        for clump in range(46):
            clump_rng=np.random.default_rng(60+clump)
            angle=clump_rng.uniform(0,2*np.pi);dist=clump_rng.uniform(900.,7800.)
            cx,cy=dist*np.cos(angle),dist*np.sin(angle)
            cz=clump_rng.uniform(1150.,1900.)
            for puff_idx in range(int(clump_rng.integers(7,14))):
                puff_rng=np.random.default_rng(70+clump*20+puff_idx)
                radius=float(puff_rng.uniform(26.,58.))
                cloud_positions.append((cx+puff_rng.uniform(-70.,70.),cy+puff_rng.uniform(-70.,70.),cz+puff_rng.uniform(-14.,10.)))
                cloud_scales.append((radius,radius*.82,radius*.55))
        instancer(self.stage,'/World/Clouds/Deck',[puff],cloud_positions,cloud_scales)

        # Sun & Sky
        light=UsdLux.DistantLight.Define(self.stage,'/World/Sun');light.CreateIntensityAttr(2600.);light.CreateAngleAttr(.53)
        light.CreateColorAttr(Gf.Vec3f(1.,.95,.87))
        light.AddRotateXYZOp().Set(Gf.Vec3f(35,-30,25))
        self.sky=UsdLux.DomeLight.Define(self.stage,'/World/Sky')
        default_sky=Path(os.environ['ISAAC_PATH']).parent/'assets/kloofendal_48d_partly_cloudy_puresky_2k.hdr'
        sky_file=Path(os.environ.get('ROCKET_SKY_HDRI',str(default_sky)))
        self.sky_asset=sky_file.as_posix() if sky_file.is_file() and sky_file.stat().st_size>100000 else None
        self.sky_intensity=1000. if self.sky_asset else 650.
        self.sky.CreateIntensityAttr(self.sky_intensity)
        self.sky.CreateColorAttr(Gf.Vec3f(1.) if self.sky_asset else Gf.Vec3f(.62,.76,1.))
        if self.sky_asset:
            self.sky.CreateTextureFileAttr(Sdf.AssetPath(self.sky_asset));self.sky.CreateTextureFormatAttr('latlong')
        # RTX height fog is left OFF: it fogs the sky dome toward flat gray and
        # erases the HDRI. Aerial perspective comes from the blue-shifted ridge
        # materials, the ocean horizon and the dry outland tones instead.
        # Bloom off as well: the emissive plume halo otherwise whites out any
        # close-up shot that frames the core.
        bloom_settings=carb.settings.get_settings()
        bloom_settings.set('/rtx/post/bloom/enabled',False)
        bloom_settings.set('/rtx/post/glare/enabled',False)

        # ====== PADS: TAKEOFF PAD 01 & LANDING PAD 01 (> 1 KM SEPARATION) ======
        self.landing_marker=None
        if np.linalg.norm(np.array(landing_xy)-np.array(launch_xy))<100.:
            landing_xy=[1050.,250.]

        for name,site in (('Launch',launch_xy),('Landing',landing_xy)):
            root='/World/'+name+'Site';site_root=UsdGeom.Xform.Define(self.stage,root)
            translate=site_root.AddTranslateOp();translate.Set(Gf.Vec3d(float(site[0]),float(site[1]),0))
            if name=='Landing':self.landing_marker=translate

            # Heavy concrete base pad
            pad=UsdGeom.Cylinder.Define(self.stage,root+'/Pad');pad.CreateAxisAttr('Z');pad.CreateRadiusAttr(26.);pad.CreateHeightAttr(.2)
            pad.AddTranslateOp().Set(Gf.Vec3d(0,0,-.1))
            UsdShade.MaterialBindingAPI.Apply(pad.GetPrim()).Bind(concrete)

            if name=='Launch':
                # Alternating safety yellow/black hazard perimeter ring (32 segments)
                for seg in range(32):
                    seg_start=seg*2*np.pi/32;seg_end=(seg+1)*2*np.pi/32
                    seg_pts=[];seg_idx=[]
                    for r_sub in range(4):
                        cur_a=seg_start+r_sub*(seg_end-seg_start)/3
                        seg_pts.extend([Gf.Vec3f(float(23.2*np.cos(cur_a)),float(23.2*np.sin(cur_a)),.016),
                                        Gf.Vec3f(float(24.8*np.cos(cur_a)),float(24.8*np.sin(cur_a)),.016)])
                    for quad in range(3):
                        seg_idx.extend([2*quad,2*quad+1,2*quad+3,2*quad+2])
                    hazard_mesh=UsdGeom.Mesh.Define(self.stage,f'{root}/HazardStrip_{seg}')
                    hazard_mesh.CreatePointsAttr(seg_pts);hazard_mesh.CreateFaceVertexCountsAttr([4]*3);hazard_mesh.CreateFaceVertexIndicesAttr(seg_idx)
                    hazard_mesh.CreateDoubleSidedAttr(True);hazard_mesh.CreateSubdivisionSchemeAttr('none')
                    UsdShade.MaterialBindingAPI.Apply(hazard_mesh.GetPrim()).Bind(hazard_yellow if seg%2==0 else hazard_black)

                # Central blast hole and flame deflector aperture
                blast_aperture=UsdGeom.Cylinder.Define(self.stage,root+'/BlastTrench')
                blast_aperture.CreateAxisAttr('Z');blast_aperture.CreateRadiusAttr(4.5);blast_aperture.CreateHeightAttr(.3)
                blast_aperture.AddTranslateOp().Set(Gf.Vec3d(0,0,-.15))
                UsdShade.MaterialBindingAPI.Apply(blast_aperture.GetPrim()).Bind(dark)

                # Ground flame-duct glow at the launch pad (was wrongly parked at world origin)
                ground_glow=UsdGeom.Cylinder.Define(self.stage,root+'/BlastGlow')
                ground_glow.CreateAxisAttr('Z');ground_glow.CreateRadiusAttr(9.);ground_glow.CreateHeightAttr(.02)
                ground_glow.AddTranslateOp().Set(Gf.Vec3d(0,0,.025))
                self.ground_glow_scale=ground_glow.AddScaleOp();self.ground_glow_scale.Set(Gf.Vec3f(.001,.001,.001))
                UsdShade.MaterialBindingAPI.Apply(ground_glow.GetPrim()).Bind(ground_glow_mat)

                # Pad deluge steam: fourteen modest white vapor puffs ringing
                # the trench, invisible until ignition, drifting on the wind
                # below 40 m. Oversized puffs read as soap bubbles on camera.
                self.steam_root=steam_root=UsdGeom.Xform.Define(self.stage,root+'/DelugeSteam')
                self.steam_scale=steam_root.AddScaleOp();self.steam_scale.Set(Gf.Vec3f(.001,.001,.001))
                steam_rng=np.random.default_rng(31)
                self.steam_translate=steam_root.AddTranslateOp();self.steam_translate.Set(Gf.Vec3d(0,0,0))
                # Eight flattened billows biased to the far side of the pad so
                # the launch coverage camera never has one in front of the lens;
                # the wide establishing shot sees them backlit behind the stack.
                for puff_idx in range(8):
                    site_puff=UsdGeom.Sphere.Define(self.stage,f'{root}/DelugeSteam/Puff{puff_idx}')
                    puff_angle=3.4+puff_idx*.38+steam_rng.uniform(-.15,.15)
                    puff_dist=steam_rng.uniform(30.,55.)
                    site_puff.AddTranslateOp().Set(Gf.Vec3d(float(puff_dist*np.cos(puff_angle)),
                                                            float(puff_dist*np.sin(puff_angle)),
                                                            float(steam_rng.uniform(1.5,4.5))))
                    # Strongly flattened ellipsoids: ground-hugging vapor sheets,
                    # never overhead spheres that read as soap bubbles.
                    site_puff.AddScaleOp().Set(Gf.Vec3f(float(steam_rng.uniform(6.,10.)),float(steam_rng.uniform(5.,9.)),float(steam_rng.uniform(1.2,2.2))))
                    UsdShade.MaterialBindingAPI.Apply(site_puff.GetPrim()).Bind(steam)

                # Vertical rim signs face the launch coverage camera (bearing -57.9°).
                # Normal = azimuth+90, rim = 15 m toward the camera at azimuth+90.
                self.painted_sign(root+'/SignName','TAKEOFF PAD 01',hazard_yellow,azimuth_deg=32.1,size=4.6,z_base=5.6)
                self.painted_sign(root+'/SignBrand','MERIDIAN 9 - ISS ORBITAL SYSTEMS',markings,azimuth_deg=32.1,size=1.5,z_base=2.6)
                # North compass marker
                north=UsdGeom.Cube.Define(self.stage,root+'/NorthMarker')
                north.AddTranslateOp().Set(Gf.Vec3d(0,21.5,.02));north.AddScaleOp().Set(Gf.Vec3f(.4,1.8,.02))
                UsdShade.MaterialBindingAPI.Apply(north.GetPrim()).Bind(hazard_yellow)
            else:
                # Reflective recovery perimeter ring
                points=[];indices=[]
                for index in range(128):
                    angle=index*2*np.pi/128
                    for radius in (23.2,24.5):points.append(Gf.Vec3f(float(radius*np.cos(angle)),float(radius*np.sin(angle)),.016))
                    indices.extend([2*index,2*index+1,(2*((index+1)%128))+1,2*((index+1)%128)])
                ring=UsdGeom.Mesh.Define(self.stage,root+'/Perimeter');ring.CreatePointsAttr(points)
                ring.CreateFaceVertexCountsAttr([4]*128);ring.CreateFaceVertexIndicesAttr(indices);ring.CreateDoubleSidedAttr(True)
                ring.CreateSubdivisionSchemeAttr('none');UsdShade.MaterialBindingAPI.Apply(ring.GetPrim()).Bind(landing_green)

                # Concentric distance rings: 16m, 10m, 5m
                for r_circ in (5.,10.,16.):
                    c_pts=[];c_idx=[]
                    for idx in range(64):
                        a=idx*2*np.pi/64
                        for r_edge in (r_circ-.08,r_circ+.08):c_pts.append(Gf.Vec3f(float(r_edge*np.cos(a)),float(r_edge*np.sin(a)),.016))
                        c_idx.extend([2*idx,2*idx+1,(2*((idx+1)%64))+1,2*((idx+1)%64)])
                    c_mesh=UsdGeom.Mesh.Define(self.stage,f'{root}/GuideRing_{int(r_circ)}')
                    c_mesh.CreatePointsAttr(c_pts);c_mesh.CreateFaceVertexCountsAttr([4]*64);c_mesh.CreateFaceVertexIndicesAttr(c_idx)
                    c_mesh.CreateDoubleSidedAttr(True);c_mesh.CreateSubdivisionSchemeAttr('none')
                    UsdShade.MaterialBindingAPI.Apply(c_mesh.GetPrim()).Bind(markings)

                # Central touchdown target bullseye cross
                for axis in range(2):
                    cross=UsdGeom.Cube.Define(self.stage,f'{root}/Cross{axis}');cross.CreateSizeAttr(1.)
                    cross.AddTranslateOp().Set(Gf.Vec3d(0,0,.018));cross.AddScaleOp().Set(Gf.Vec3f(12. if axis==0 else .4,.4 if axis==0 else 12.,.02))
                    UsdShade.MaterialBindingAPI.Apply(cross.GetPrim()).Bind(markings)

                # Scorch mark decal from hoverslam burn
                scorch_disc=UsdGeom.Cylinder.Define(self.stage,root+'/ScorchMark')
                scorch_disc.CreateAxisAttr('Z');scorch_disc.CreateRadiusAttr(7.5);scorch_disc.CreateHeightAttr(.008)
                scorch_disc.AddTranslateOp().Set(Gf.Vec3d(0,0,.012))
                UsdShade.MaterialBindingAPI.Apply(scorch_disc.GetPrim()).Bind(scorch_mat)

                # Landing coverage camera bearing -52.3°: normal points at camera
                # when azimuth = bearing+90 (empirically verified facing).
                self.painted_sign(root+'/SignName','LANDING PAD 01',landing_green,azimuth_deg=37.7,size=4.6,z_base=5.6)
                self.painted_sign(root+'/SignBrand','MERIDIAN 9 - ISS ORBITAL SYSTEMS',markings,azimuth_deg=37.7,size=1.5,z_base=2.6)

        # ====== LAUNCH COMPLEX & SERVICE TOWER ======
        launch=launch_xy;self.clamps=[]
        for index in range(4):
            angle=index*np.pi/2
            clamp=UsdGeom.Xform.Define(self.stage,f'/World/LaunchClamp{index}')
            clamp.AddTranslateOp().Set(Gf.Vec3d(float(launch[0]+np.cos(angle)*2.4),float(launch[1]+np.sin(angle)*2.4),2.5))
            orient=clamp.AddRotateXYZOp();self.clamps.append((orient,angle))
            beam=UsdGeom.Cube.Define(self.stage,f'/World/LaunchClamp{index}/Arm');beam.AddScaleOp().Set(Gf.Vec3f(.3,.3,2.6))
            UsdShade.MaterialBindingAPI.Apply(beam.GetPrim()).Bind(dark)
            jaw=UsdGeom.Cube.Define(self.stage,f'/World/LaunchClamp{index}/Jaw')
            jaw.AddTranslateOp().Set(Gf.Vec3d(float(-np.cos(angle)*.35),float(-np.sin(angle)*.35),1.7))
            jaw.AddRotateZOp().Set(float(np.rad2deg(angle)));jaw.AddScaleOp().Set(Gf.Vec3f(.6,.25,.22))
            UsdShade.MaterialBindingAPI.Apply(jaw.GetPrim()).Bind(dark)

        # 10-level structural steel lattice gantry tower with diagonal X-braces
        tower_x,tower_y=float(launch[0]+14),float(launch[1])
        for index,(dx,dy) in enumerate(((-2.2,-2.2),(-2.2,2.2),(2.2,-2.2),(2.2,2.2))):
            column=UsdGeom.Cube.Define(self.stage,f'/World/ServiceTower/Column{index}')
            column.AddTranslateOp().Set(Gf.Vec3d(tower_x+dx,tower_y+dy,27.5));column.AddScaleOp().Set(Gf.Vec3f(.35,.35,27.5))
            UsdShade.MaterialBindingAPI.Apply(column.GetPrim()).Bind(dark)

        for level in range(1,11):
            lvl_z=float(level*5.2)
            deck=UsdGeom.Cube.Define(self.stage,f'/World/ServiceTower/Deck{level}')
            deck.AddTranslateOp().Set(Gf.Vec3d(tower_x,tower_y,lvl_z))
            deck.AddScaleOp().Set(Gf.Vec3f(2.6,2.6,.12));UsdShade.MaterialBindingAPI.Apply(deck.GetPrim()).Bind(dark)
            # Diagonal structural X-trusses across tower bays
            if level<10:
                for face,(fx,fy,fz_rot) in enumerate(((0,-2.2,0),(0,2.2,0),(-2.2,0,90),(2.2,0,90))):
                    diag1=UsdGeom.Cube.Define(self.stage,f'/World/ServiceTower/Truss_{level}_{face}_A')
                    diag1.AddTranslateOp().Set(Gf.Vec3d(tower_x+fx,tower_y+fy,lvl_z+2.6))
                    diag1.AddRotateZOp().Set(fz_rot);diag1.AddRotateYOp().Set(45.)
                    diag1.AddScaleOp().Set(Gf.Vec3f(3.2,.08,.08))
                    UsdShade.MaterialBindingAPI.Apply(diag1.GetPrim()).Bind(dark)

        # Cryogenic propellant supply pipes running up the tower
        pipe=UsdGeom.Cylinder.Define(self.stage,'/World/ServiceTower/CryoPipe')
        pipe.CreateAxisAttr('Z');pipe.CreateRadiusAttr(.22);pipe.CreateHeightAttr(52.)
        pipe.AddTranslateOp().Set(Gf.Vec3d(tower_x-2.6,tower_y,26.))
        UsdShade.MaterialBindingAPI.Apply(pipe.GetPrim()).Bind(white)

        # Interstage umbilical swing arm at level 7
        arm=UsdGeom.Cube.Define(self.stage,'/World/ServiceTower/UmbilicalArm')
        arm.AddTranslateOp().Set(Gf.Vec3d(tower_x-5.5,tower_y,36.4));arm.AddScaleOp().Set(Gf.Vec3f(5.5,.45,.45))
        UsdShade.MaterialBindingAPI.Apply(arm.GetPrim()).Bind(dark)

        # Lightning protection mast at pinnacle
        mast=UsdGeom.Cylinder.Define(self.stage,'/World/ServiceTower/LightningMast')
        mast.CreateAxisAttr('Z');mast.CreateRadiusAttr(.12);mast.CreateHeightAttr(14.)
        mast.AddTranslateOp().Set(Gf.Vec3d(tower_x,tower_y,61.))
        UsdShade.MaterialBindingAPI.Apply(mast.GetPrim()).Bind(chrome)

        if self.flow:self._flow_setup()

        # Hero framing: low press-site angle holding rocket, tower and pad.
        from isaacsim.core.utils.viewports import set_camera_view
        set_camera_view(eye=np.array([64.,-78.,13.]),target=np.array([6.,0.,19.]))

    def set_landing_target(self,target):
        if self.landing_marker:
            self.landing_marker.Set(Gf.Vec3d(float(target[0]),float(target[1]),0))

    def camera(self,mode):
        self.follow=mode=='follow'
        self.mode=mode
        if mode in ('free',):return
        from isaacsim.core.utils.viewports import set_camera_view
        if mode=='vehicle':
            target=self.physics.position+np.array([0.,0.,4.])
            set_camera_view(eye=target+np.array([22.,-28.,10.]),target=target)
        elif mode in ('launch','landing'):
            site=np.array([*(self.physics.cfg['mission'].get('launch',[0,0])[:2] if mode=='launch' else self.physics.cfg['mission']['pad'][:2]),0.])
            offset=np.array([74.,-94.,9.]) if mode=='launch' else np.array([52.,-66.,9.])
            set_camera_view(eye=site+offset,target=site+np.array([0.,0.,16.]))
        else:self.follow=True

    def _flow_setup(self):
        manager=omni.kit.app.get_app().get_extension_manager();manager.set_extension_enabled_immediate('omni.flowusd',True)
        extension_id=manager.get_enabled_extension_id('omni.flowusd')
        if not extension_id:raise RuntimeError('Requested Flow volumes but omni.flowusd is unavailable; no mesh-flame substitute was enabled')
        root=Path(manager.get_extension_path(extension_id))
        preferred=root/'data/presets/Fire/Fire.usda'
        presets=[preferred] if preferred.exists() else sorted([*root.rglob('*[Ff]ire*.usd'),*root.rglob('*[Ff]ire*.usda')],key=lambda path:len(str(path)))
        if not presets:raise RuntimeError('Flow extension has no bundled fire preset. Supply a validated Flow asset before requesting volumetric exhaust.')
        from pxr import Usd
        source=Usd.Stage.Open(str(presets[0]));default=source.GetDefaultPrim()
        if not default:raise RuntimeError('Flow fire preset has no default prim')
        plume=UsdGeom.Xform.Define(self.stage,'/World/ExhaustVolume')
        plume.GetPrim().GetReferences().AddReference(str(presets[0]),default.GetPath())
        self.flow_emitters=[prim for prim in Usd.PrimRange(plume.GetPrim()) if 'Emitter' in prim.GetTypeName()]
        self.flow_simulates=[]
        if not self.flow_emitters:raise RuntimeError('Flow fire asset has no volume emitters')
        for emitter in self.flow_emitters:
            attribute(emitter,'enabled',Sdf.ValueTypeNames.Bool,False)
            attribute(emitter,'radius',Sdf.ValueTypeNames.Float,.85)
            attribute(emitter,'coupleRateVelocity',Sdf.ValueTypeNames.Float,120.)
            attribute(emitter,'coupleRateFuel',Sdf.ValueTypeNames.Float,120.)
            attribute(emitter,'coupleRateTemperature',Sdf.ValueTypeNames.Float,120.)
        for prim in Usd.PrimRange(plume.GetPrim()):
            if prim.GetTypeName()=='FlowSimulate':
                self.flow_simulates.append(prim)
                attribute(prim,'densityCellSize',Sdf.ValueTypeNames.Float,.25)
                attribute(prim,'stepsPerSecond',Sdf.ValueTypeNames.Float,30.)
                attribute(prim,'simulateWhenPaused',Sdf.ValueTypeNames.Bool,True)
                attribute(prim,'forceSimulate',Sdf.ValueTypeNames.Bool,True)
            if prim.GetTypeName()=='FlowAdvectionCombustionParams':
                attribute(prim,'gravity',Sdf.ValueTypeNames.Float3,Gf.Vec3f(0,0,-9.80665))
        settings=carb.settings.get_settings()
        settings.set('/rtx/flow/enabled',True)
        settings.set('/rtx/flow/pathTracingEnabled',True)
        self.flow_asset=str(presets[0])
        from omni.flowusd import _flowusd
        self.flow_interface=_flowusd.acquire_flowusd_interface()

    def pause_effects(self,paused):
        if self.flow:
            for prim in self.flow_simulates:attribute(prim,'timeScale',Sdf.ValueTypeNames.Float,0. if paused else 1.)

    def update(self,physics):
        self.pause_effects(False)
        self.record_tick()
        # Real seconds between visuals updates: every eased quantity below is
        # rate-based so 60 Hz live view and offline replay animate identically.
        previous_clock=getattr(self,'_update_clock',None)
        self._update_clock=physics.data.time
        render_dt=float(np.clip(physics.data.time-(previous_clock if previous_clock is not None
            else physics.data.time-.0167),1/240,.25))
        def ease(current,target,per_second):
            return current+(target-current)*min(1.,1.-math.exp(-per_second*render_dt))
        if self.sky_asset:
            observer_height=max(0.,physics.position[2]) if self.follow else 60.
            self.sky.GetIntensityAttr().Set(float(self.sky_intensity*np.exp(-max(0.,observer_height-12000.)/8500.)))

        # Launch clamp hydraulic release
        release=min(1.,max(0.,(physics.data.time-(physics.release_time or physics.data.time))/.5)) if physics.release_time is not None else 0.
        for orient,angle in self.clamps:orient.Set(Gf.Vec3f(float(-np.sin(angle)*release*70),float(np.cos(angle)*release*70),0))

        # Gimbal vector alignment
        direction=np.array([np.tan(physics.gimbal[0]),np.tan(physics.gimbal[1]),1.]);direction/=np.linalg.norm(direction)
        rotation=Gf.Rotation(Gf.Vec3d(0,0,1),Gf.Vec3d(*direction)).GetQuat()
        self.nozzle_rotation.Set(Gf.Quatf(float(rotation.GetReal()),Gf.Vec3f(*rotation.GetImaginary())))

        # Kerolox plume: throttle length with combustion flicker; the veil
        # overexpands with altitude like a real low-pressure exhaust plume.
        # Flicker is correlated smooth noise (1-13 Hz band from flame studies):
        # slow envelope + fast chop, never strobing.
        throttle=float(physics.throttle)
        alt_agl=max(0.,physics.position[2]-physics.rest)
        t=physics.data.time
        slow=1.+.09*np.sin(2.1*t)+.05*np.sin(3.7*t+2.1)          # breathing envelope
        fast=1.+.06*np.sin(21.*t)+.04*np.sin(47.*t+1.3)+.03*np.sin(83.*t+.6)  # fine chop
        flicker=slow*fast
        if throttle>.01:
            plume_len=float(np.clip(throttle*flicker*(13.5+.55*min(alt_agl/220.,2.2)),.1,17.))
            # Never tunnel through the ground: at pad height the plume stops
            # just above the surface (the ground flare sells the splash).
            plume_len=min(plume_len,max(.35*alt_agl,1.2))
            plume_width=max(.1,throttle*flicker*1.35)
            self.plume_scale.Set(Gf.Vec3f(plume_width,plume_width,plume_len))
            veil_width=float(np.clip(.75*throttle*(1.+alt_agl/420.),.1,9.))
            self.veil_scale.Set(Gf.Vec3f(veil_width,veil_width,plume_len*1.28))
            self.sheath_shader.GetInput('opacity').Set(float(np.clip(.55*throttle*slow,0.,.7)))
            self.veil_shader.GetInput('opacity').Set(float(np.clip(.16*throttle*(1.+alt_agl/900.)*fast,0.,.45)))
            # Shock cells: out-of-phase brightness noise; fade along the plume
            fade=1.-.06*np.sin(29.*t)
            self.diamond_shader.GetInput('opacity').Set(float(np.clip(.65*throttle*fade*fast,0.,.75)))
        else:
            self.plume_scale.Set(Gf.Vec3f(.001,.001,.001))
            self.veil_scale.Set(Gf.Vec3f(.001,.001,.001))
            self.diamond_shader.GetInput('opacity').Set(0.)

        # Pad deluge steam blooms while the engine holds near the pad
        steam_visible='invisible' if not (throttle>.04 and alt_agl<12.) else 'inherited'
        UsdGeom.Imageable(self.steam_root.GetPrim()).GetVisibilityAttr().Set(steam_visible)
        if steam_visible=='inherited':
            amount=float(np.clip((1.-alt_agl/12.)*throttle,0.,1.))
            steam_pad=max(.55+.55*amount*flicker,.6)
            self.steam_scale.Set(Gf.Vec3f(steam_pad,steam_pad,1.))
            drift=float(physics.data.time*2.4)%10.
            self.steam_translate.Set(Gf.Vec3d(-float(physics.wind[0])*drift*2.,-float(physics.wind[1])*drift*2.,0.))

        # Ground blast flare when near pad/ground
        if throttle>.02 and alt_agl<6.0:
            ground_scale=float((1.0-alt_agl/6.0)*throttle*throttle*3.0)
            self.ground_glow_scale.Set(Gf.Vec3f(ground_scale,ground_scale,1.0))
        else:
            self.ground_glow_scale.Set(Gf.Vec3f(.001,.001,.001))

        # Plume RTX light: warm kerolox wash, bounded so surfaces keep color
        self.flame_light.GetIntensityAttr().Set(float(throttle*7000.))

        # Landing legs deploy smoothly when the vehicle settles below 65 m
        is_landing=getattr(physics,'phase','landing')=='landing' or alt_agl<65.
        target_deploy=32.0 if (is_landing and alt_agl<65.0 and physics.velocity[2]<2.0) else 0.0
        self.leg_deployment=ease(self.leg_deployment,target_deploy,3.8)
        for leg in self.landing_legs:
            leg.Set(float(self.leg_deployment))

        # Grid fins: folded flush against the hull while climbing, deployed
        # with a rate wobble during terminal descent steering (folded on ascent,
        # out at the pad — like the recovered vehicle itself).
        descending=is_landing and physics.velocity[2]<3.
        deploy_target=84. if descending else 0.
        self.fin_tilt=ease(self.fin_tilt,deploy_target,2.5)
        # Body-frame rates come straight from PhysX so fins articulate with the
        # vehicle (the physics object carries omega_world, not .angular_velocity).
        # ponytail: no deployed-angle table; a single eased tilt reads fine at RTX.
        ang_vel=physics.rotation().T@np.asarray(getattr(physics,'omega_world',np.zeros(3)),dtype=float)
        for i,fin in enumerate(self.grid_fins):
            wobble=float(np.clip(ang_vel[i%2]*18.,-18.,18.))
            fin.Set(float(np.clip(self.fin_tilt+wobble*(1. if descending else 0.),-88.,88.)))

        # NVIDIA Flow Volumetric simulation
        if self.flow:
            axis=physics.rotation()@direction
            exit_position=physics.position+physics.rotation()@np.array([0,0,-physics.engine_lever])-axis*1.65
            for emitter in self.flow_emitters:
                attribute(emitter,'position',Sdf.ValueTypeNames.Float3,Gf.Vec3f(*exit_position))
                enabled=emitter.GetAttribute('enabled')
                if enabled:enabled.Set(bool(throttle>.02))
                velocity=emitter.GetAttribute('velocity')
                if velocity:velocity.Set(Gf.Vec3f(*(-axis*(45+120*throttle))))

        # Cinematic camera: SpaceX-style close coverage. Every shot lives
        # within ~60 m of the vehicle so the render stays fast; the old
        # far flyaway orbit was costing frames and nobody could see detail.
        if physics.data.time-self.last_camera<.02:return
        from isaacsim.core.utils.viewports import set_camera_view
        self.last_camera=physics.data.time
        if self.follow or self.mode=='follow':
            p=physics.position
            if alt_agl<60.:
                # Liftoff press shot: low, near the tower, craning up as the
                # vehicle clears the mount.
                site=np.array([*self.physics.cfg['mission'].get('launch',[0,0])[:2],0.])
                eye=site+np.array([34.,-42.,8.]);target=p+np.array([0.,0.,2.])
            else:
                # Tight chase that never drifts away: 22-60 m, slightly below
                # the stack so it looks up like the onboard chase view.
                az=physics.data.time*.035+self.camp_az
                d=float(np.clip(22.+alt_agl*.10,22.,60.))
                eye=p+np.array([np.cos(az)*d,np.sin(az)*d*.85,max(p[2]-d*.28,4.)])-np.array([0.,0.,d*.18])
                target=p+np.array([0.,0.,-2.])
        elif self.mode in ('launch','landing'):
            site=np.array([*(self.physics.cfg['mission'].get('launch',[0,0])[:2] if self.mode=='launch' else self.physics.cfg['mission']['pad'][:2]),0.])
            # Press tripods sit close to the pad and track the vehicle itself.
            base=site+(np.array([44.,-52.,10.]) if self.mode=='launch' else np.array([46.,-56.,11.]))
            eye=base
            target=np.array([*physics.position[:2],max(6.,physics.position[2]*.4)])
        else:
            return
        if not hasattr(self,'cam_eye'):
            self.cam_eye,self.cam_target=eye.copy(),target.copy()
        blend=min(1.,1.-math.exp(-18.*render_dt))
        self.cam_eye+=(eye-self.cam_eye)*blend
        self.cam_target+=(target-self.cam_target)*blend
        set_camera_view(eye=tuple(map(float,self.cam_eye)),target=tuple(map(float,self.cam_target)))

    def start_record(self,filename,fps=30,size=(1280,720)):
        """Encode one frame per visuals update (the 30 sim-Hz render gate)
        straight into an MP4 via Isaac's own video encoder.
        Frames-per-sim-second equals the writer fps, so playback is real time."""
        import omni.kit.app
        import omni.replicator.core as rep
        manager=omni.kit.app.get_app().get_extension_manager()
        if not manager.is_extension_enabled('omni.videoencoding'):manager.set_extension_enabled_immediate('omni.videoencoding')
        from video_encoding.impl import get_video_encoding_interface
        self._encoder=get_video_encoding_interface()
        path=Path(filename);path.parent.mkdir(parents=True,exist_ok=True)
        path.unlink(missing_ok=True)
        if not self._encoder or not self._encoder.start_encoding(str(path),float(fps),0,True):
            raise RuntimeError('Native video encoder unavailable in this Isaac installation')
        self._record_file=path
        self._record_product=rep.create.render_product('/OmniverseKit_Persp',(int(size[0]),int(size[1])))
        self._record_annotator=rep.AnnotatorRegistry.get_annotator('rgb')
        self._record_annotator.attach(self._record_product)
        return path

    def record_tick(self):
        """Encode the latest viewport frame; no-op while inactive."""
        if getattr(self,'_record_annotator',None) is None:return
        # The annotator graph only dispatches an explicit orchestrator step;
        # without it get_data() returns an empty buffer forever (verified by
        # scripts/probe_annotator.py on this kit experience).
        import omni.replicator.core as rep
        try:rep.orchestrator.step(rt_subframes=0,pause_timeline=False)
        except Exception:
            pass
        data=self._record_annotator.get_data()
        if data is None or data is False or getattr(data,'size',0)==0:return
        if data.dtype!=np.uint8:data=np.clip(data,0,255).astype(np.uint8)
        data=np.ascontiguousarray(data)
        self._encoder.encode_next_frame_from_buffer(memoryview(data),int(data.shape[1]),int(data.shape[0]))

    def stop_record(self):
        if getattr(self,'_record_annotator',None) is None:return None
        self._encoder.finalize_encoding()
        self._record_annotator.detach();self._record_product.destroy()
        self._record_annotator=None
        return Path(self._record_file)

    def capture(self,app,path,view='vehicle'):
        """Export a native render artifact; does not capture the user's desktop."""
        import asyncio
        import time
        from isaacsim.core.utils.viewports import set_camera_view
        from omni.kit.viewport.utility import capture_viewport_to_file,get_active_viewport
        if view=='engine':
            target=self.physics.position+np.array([0.,0.,-self.physics.engine_lever-2.5])
            eye=target+np.array([12.,12.,-1.2])
        elif view=='launch':
            site=np.array([*self.physics.cfg['mission'].get('launch',[0,0])[:2],0.])
            target=site+np.array([0.,0.,16.]);eye=site+np.array([74.,-118.,13.])
        elif view=='landing':
            site=np.array([*self.physics.cfg['mission']['pad'][:2],0.])
            target=site+np.array([0.,0.,8.]);eye=site+np.array([54.,-70.,11.])
        else:
            target=self.physics.position+np.array([0.,0.,5.])
            eye=self.physics.position+np.array([34.,-44.,11.])
        set_camera_view(eye=eye,target=target)
        for _ in range(40):self.physics.world.render()
        if self.flow:
            active_blocks=self.flow_interface.get_active_block_count()
            self.flow_active_blocks=max(getattr(self,'flow_active_blocks',0),active_blocks)
            print(f'FLOW: active simulation blocks {active_blocks}',flush=True)
            if self.physics.throttle>.02 and active_blocks<=0:
                raise RuntimeError('Engine firing with Flow enabled but no active volume blocks were simulated')
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        path.unlink(missing_ok=True)
        capture=capture_viewport_to_file(get_active_viewport(),str(path))
        task=asyncio.ensure_future(capture.wait_for_result());deadline=time.monotonic()+60
        stable=0;previous_size=0
        while time.monotonic()<deadline:
            self.physics.world.render()
            size=path.stat().st_size if path.exists() else 0
            stable=stable+1 if size>0 and size==previous_size else 0
            previous_size=size
            if task.done() and stable>=3:break
            time.sleep(.01)
        if not task.done() or stable<3:raise RuntimeError('Native render capture did not finish')
        task.result();return str(path)
