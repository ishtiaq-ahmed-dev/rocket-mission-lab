"""Native USD materials, RTX lighting, supersonic exhaust plume and high-fidelity aerospace assets."""
from pathlib import Path
import os
import numpy as np
from pxr import Gf,Sdf,UsdGeom,UsdLux,UsdShade
import carb
import omni.kit.app
import omni.usd


def attribute(prim,name,kind,value):
    prim.CreateAttribute(name,kind,custom=False).Set(value)


class NativeVisuals:
    def __init__(self,flow=False,follow=False):
        self.flow=flow;self.follow=follow;self.stage=omni.usd.get_context().get_stage()
        self.flow_emitters=[];self.last_camera=0
        self.landing_legs=[];self.grid_fins=[]
        self.leg_deployment=0.0

    def material(self,path,color,metallic=0.,roughness=.5,emission=None):
        material=UsdShade.Material.Define(self.stage,path);shader=UsdShade.Shader.Define(self.stage,path+'/Surface')
        shader.CreateIdAttr('UsdPreviewSurface')
        shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        shader.CreateInput('metallic',Sdf.ValueTypeNames.Float).Set(metallic)
        shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(roughness)
        if emission:shader.CreateInput('emissiveColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emission))
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
        return material

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
        
        # Emissive supersonic rocket plume materials
        flame_core=self.material('/World/Looks/MachDiamondCore',(1.,1.,1.),.0,.1,emission=(75.,70.,55.))
        flame_sheath=self.material('/World/Looks/PlumeSheath',(1.,.52,.10),.0,.2,emission=(32.,14.,2.))
        ground_glow_mat=self.material('/World/Looks/GroundFlameGlow',(1.,.42,.06),.0,.2,emission=(20.,8.,1.))

        # Vehicle bindings
        UsdShade.MaterialBindingAPI.Apply(self.stage.GetPrimAtPath('/World/Booster')).Bind(white)
        UsdShade.MaterialBindingAPI.Apply(self.stage.GetPrimAtPath('/World/Payload')).Bind(satellite)
        payload_hull=UsdGeom.Cylinder(self.stage.GetPrimAtPath('/World/Payload/Hull'))
        payload_hull.CreateVisibilityAttr('invisible')

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
            vent.AddTranslateOp().Set(Gf.Vec3d(float(np.cos(vent_angle)*1.81),float(np.sin(vent_angle)*1.81),physics.half-1.6))
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

        # ====== 4 HYPERSONIC TITANIUM GRID FINS ======
        self.grid_fins=[]
        for fin_idx in range(4):
            fin_angle=fin_idx*np.pi/2
            fin_xform=UsdGeom.Xform.Define(self.stage,f'/World/Booster/GridFin{fin_idx}')
            fin_xform.AddTranslateOp().Set(Gf.Vec3d(float(np.cos(fin_angle)*(physics.v['radius']+.15)),
                                                   float(np.sin(fin_angle)*(physics.v['radius']+.15)),
                                                   physics.half-3.2))
            fin_rot_z=fin_xform.AddRotateZOp();fin_rot_z.Set(float(np.rad2deg(fin_angle)))
            fin_tilt=fin_xform.AddRotateXOp();fin_tilt.Set(0.)
            self.grid_fins.append(fin_tilt)

            # Actuator hinge housing
            hinge=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/GridFin{fin_idx}/Hinge')
            hinge.CreateAxisAttr('X');hinge.CreateRadiusAttr(.16);hinge.CreateHeightAttr(.45)
            UsdShade.MaterialBindingAPI.Apply(hinge.GetPrim()).Bind(dark)

            # Titanium waffle grid blade
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
            leg_rot_z=leg_root.AddRotateZOp();leg_rot_z.Set(float(angle_deg))
            leg_deploy=leg_root.AddRotateYOp();leg_deploy.Set(0.) # 0 = folded against hull, 35 deg = deployed
            self.landing_legs.append(leg_deploy)

            # Main carbon A-frame strut
            strut=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/LegAssembly{i}/MainStrut')
            strut.CreateAxisAttr('Z');strut.CreateRadiusAttr(.14);strut.CreateHeightAttr(7.5)
            strut.AddTranslateOp().Set(Gf.Vec3d(0,0,-3.75))
            UsdShade.MaterialBindingAPI.Apply(strut.GetPrim()).Bind(dark)

            # Telescoping hydraulic chrome piston
            piston=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/LegAssembly{i}/Piston')
            piston.CreateAxisAttr('Z');piston.CreateRadiusAttr(.09);piston.CreateHeightAttr(4.5)
            piston.AddTranslateOp().Set(Gf.Vec3d(.18,0,-4.5))
            UsdShade.MaterialBindingAPI.Apply(piston.GetPrim()).Bind(chrome)

            # Articulated footpad shoe
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

        # ====== SUPERSONIC PLUME & MACH DIAMONDS ======
        plume_root=UsdGeom.Xform.Define(self.stage,'/World/Booster/Nozzle/Plume')
        plume_root.AddTranslateOp().Set(Gf.Vec3d(0,0,-1.65))
        self.plume_scale=plume_root.AddScaleOp();self.plume_scale.Set(Gf.Vec3f(0.001,0.001,0.001))

        # Supersonic outer flame expansion sheath
        sheath=UsdGeom.Cone.Define(self.stage,'/World/Booster/Nozzle/Plume/Sheath')
        sheath.CreateAxisAttr('Z');sheath.CreateRadiusAttr(1.2);sheath.CreateHeightAttr(8.5)
        sheath.AddTranslateOp().Set(Gf.Vec3d(0,0,-4.25));sheath.AddRotateXOp().Set(180.)
        UsdShade.MaterialBindingAPI.Apply(sheath.GetPrim()).Bind(flame_sheath)

        # 4 Mach shock diamonds along supersonic core
        self.diamonds=[]
        for d_idx,d_z in enumerate((-1.2,-2.6,-4.2,-6.0)):
            dia=UsdGeom.Cone.Define(self.stage,f'/World/Booster/Nozzle/Plume/Diamond{d_idx}')
            dia.CreateAxisAttr('Z');dia.CreateRadiusAttr(.38-d_idx*.06);dia.CreateHeightAttr(.9)
            dia.AddTranslateOp().Set(Gf.Vec3d(0,0,d_z));dia.AddRotateXOp().Set(180.)
            UsdShade.MaterialBindingAPI.Apply(dia.GetPrim()).Bind(flame_core)
            self.diamonds.append(dia)

        # Ground blast flame deflection disk
        ground_glow=UsdGeom.Cylinder.Define(self.stage,'/World/GroundFlameGlow')
        ground_glow.CreateAxisAttr('Z');ground_glow.CreateRadiusAttr(9.0);ground_glow.CreateHeightAttr(.02)
        ground_glow.AddTranslateOp().Set(Gf.Vec3d(0,0,.025))
        self.ground_glow_scale=ground_glow.AddScaleOp();self.ground_glow_scale.Set(Gf.Vec3f(0.001,0.001,0.001))
        UsdShade.MaterialBindingAPI.Apply(ground_glow.GetPrim()).Bind(ground_glow_mat)

        # Dynamic RTX Lighting from Plume
        self.flame_light=UsdLux.SphereLight.Define(self.stage,'/World/Booster/Nozzle/Glow')
        self.flame_light.CreateRadiusAttr(1.2);self.flame_light.CreateColorAttr(Gf.Vec3f(1.,.48,.12));self.flame_light.CreateIntensityAttr(0.)
        self.flame_light.AddTranslateOp().Set(Gf.Vec3d(0,0,-2.5))

        # Sun & Sky
        light=UsdLux.DistantLight.Define(self.stage,'/World/Sun');light.CreateIntensityAttr(2600.);light.CreateAngleAttr(.53)
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

        # ====== PADS: TAKEOFF PAD 01 & LANDING PAD 01 (> 1 KM SEPARATION) ======
        self.landing_marker=None
        launch_xy=physics.cfg['mission'].get('launch',[0,0])[:2]
        landing_xy=physics.cfg['mission']['pad'][:2]
        # Guarantee physical separation exceeds 1 km for distinct pads
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
                # ====== TAKEOFF PAD 01 MARKINGS ======
                # Alternating safety yellow and black hazard perimeter ring (32 segments)
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

                # Explicit TAKEOFF wording — top and bottom
                self.painted_label(root+'/LabelTop','TAKEOFF PAD 01',markings,y_offset=16.5,size=2.2)
                self.painted_label(root+'/LabelBottom','TAKEOFF',hazard_yellow,y_offset=-16.5,size=3.6)
                # North compass marker
                north=UsdGeom.Cube.Define(self.stage,root+'/NorthMarker')
                north.AddTranslateOp().Set(Gf.Vec3d(0,21.5,.02));north.AddScaleOp().Set(Gf.Vec3f(.4,1.8,.02))
                UsdShade.MaterialBindingAPI.Apply(north.GetPrim()).Bind(hazard_yellow)
            else:
                # ====== LANDING PAD 01 MARKINGS ======
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

                # Explicit LANDING wording — top and bottom
                self.painted_label(root+'/LabelTop','LANDING PAD 01',markings,y_offset=16.5,size=2.2)
                self.painted_label(root+'/LabelBottom','LANDING ZONE',landing_green,y_offset=-16.5,size=3.4)

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

        # 10-Level structural steel lattice gantry tower with diagonal X-braces
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
        from isaacsim.core.utils.viewports import set_camera_view
        set_camera_view(eye=np.array([85.,85.,42.]),target=np.array([0.,0.,20.]))

    def set_landing_target(self,target):
        if self.landing_marker:
            self.landing_marker.Set(Gf.Vec3d(float(target[0]),float(target[1]),0))

    def camera(self,mode):
        self.follow=mode=='follow'
        if mode in ('free','follow'):return
        from isaacsim.core.utils.viewports import set_camera_view
        if mode=='vehicle':target=self.physics.position+np.array([0.,0.,4.])
        elif mode=='launch':target=np.array([*self.physics.cfg['mission'].get('launch',[0,0])[:2],20.])
        else:target=np.array([*list(self.landing_marker.Get())[:2],0.])
        set_camera_view(eye=target+np.array([80.,80.,35.]),target=target)

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

        # Dynamic supersonic plume scaling with throttle
        throttle=float(physics.throttle)
        if throttle>.01:
            plume_len=max(.1,throttle*14.0)
            plume_width=max(.1,throttle*1.8)
            self.plume_scale.Set(Gf.Vec3f(plume_width,plume_width,plume_len))
        else:
            self.plume_scale.Set(Gf.Vec3f(.001,.001,.001))

        # Ground blast flare when near pad/ground
        alt_agl=max(0.,physics.position[2]-physics.half)
        if throttle>.02 and alt_agl<16.0:
            ground_scale=float((1.0-alt_agl/16.0)*throttle*9.0)
            self.ground_glow_scale.Set(Gf.Vec3f(ground_scale,ground_scale,1.0))
        else:
            self.ground_glow_scale.Set(Gf.Vec3f(.001,.001,.001))

        # Plume RTX emissive light
        self.flame_light.GetIntensityAttr().Set(float(throttle*240000.))

        # Dynamic Landing Leg Deployment (smoothly extends when descending below 65m)
        is_landing=getattr(physics,'phase','landing')=='landing' or alt_agl<65.
        target_deploy=32.0 if (is_landing and alt_agl<65.0 and physics.velocity[2]<2.0) else 0.0
        self.leg_deployment+=(target_deploy-self.leg_deployment)*0.12
        for leg in self.landing_legs:
            leg.Set(float(self.leg_deployment))

        # Hypersonic Grid Fin articulation based on angular velocity
        ang_vel=getattr(physics,'angular_velocity',np.zeros(3))
        for i,fin in enumerate(self.grid_fins):
            tilt=float(np.clip(ang_vel[i%2]*18.0,-24.0,24.0))
            fin.Set(tilt)

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

        # Cinematic Follow Camera
        if self.follow and physics.data.time-self.last_camera>.06:
            from isaacsim.core.utils.viewports import set_camera_view
            self.last_camera=physics.data.time
            # Dynamic camera offset based on altitude and speed
            cam_dist=min(120.,65.+alt_agl*0.06)
            set_camera_view(eye=physics.position+np.array([cam_dist*.8,cam_dist*.8,cam_dist*.35]),target=physics.position)

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
            launch=self.physics.cfg['mission'].get('launch',[0,0])[:2];target=np.array([*launch,16.]);eye=target+np.array([78.,78.,36.])
        elif view=='landing':
            landing=self.physics.cfg['mission']['pad'][:2];target=np.array([*landing,4.]);eye=target+np.array([55.,55.,22.])
        else:target=self.physics.position+np.array([0.,0.,5.]);eye=self.physics.position+np.array([82.,82.,24.])
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
