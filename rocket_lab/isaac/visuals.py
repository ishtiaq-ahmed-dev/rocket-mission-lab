"""Native USD materials, RTX lighting and optional NVIDIA Flow volumes."""
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

    def material(self,path,color,metallic=0.,roughness=.5,emission=None):
        material=UsdShade.Material.Define(self.stage,path);shader=UsdShade.Shader.Define(self.stage,path+'/Surface')
        shader.CreateIdAttr('UsdPreviewSurface')
        shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
        shader.CreateInput('metallic',Sdf.ValueTypeNames.Float).Set(metallic)
        shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(roughness)
        if emission:shader.CreateInput('emissiveColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emission))
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
        return material

    def painted_label(self,path,text,material):
        """Triangulated font outlines lie on the pad; labels never face the camera."""
        from matplotlib.textpath import TextPath
        from matplotlib.path import Path as Outline
        from scipy.spatial import Delaunay
        contours=TextPath((0,0),text,size=2.5).to_polygons()
        vertices=np.unique(np.vstack(contours),axis=0);triangles=Delaunay(vertices).simplices
        candidates=vertices[triangles]
        samples=np.stack([candidates.mean(axis=1),*(.5*(candidates[:,index]+candidates[:,(index+1)%3]) for index in range(3))],axis=1)
        samples=.999*samples+.001*candidates.mean(axis=1)[:,None,:]
        inside=np.zeros(samples.shape[:2],dtype=bool)
        for contour in contours:inside^=Outline(contour).contains_points(samples.reshape(-1,2)).reshape(inside.shape)
        triangles=triangles[inside.all(axis=1)]
        vertices[:,0]-=(vertices[:,0].min()+vertices[:,0].max())*.5;vertices[:,1]-=17.
        label=UsdGeom.Mesh.Define(self.stage,path)
        label.CreatePointsAttr([Gf.Vec3f(float(x),float(y),.019) for x,y in vertices])
        label.CreateFaceVertexCountsAttr([3]*len(triangles));label.CreateFaceVertexIndicesAttr(triangles.ravel().tolist())
        label.CreateDoubleSidedAttr(True);label.CreateSubdivisionSchemeAttr('none')
        UsdShade.MaterialBindingAPI.Apply(label.GetPrim()).Bind(material)

    def setup(self,physics):
        self.physics=physics
        white=self.material('/World/Looks/Booster',(.78,.79,.8),.08,.35)
        dark=self.material('/World/Looks/Engine',(.12,.13,.14),.85,.32)
        satellite=self.material('/World/Looks/Payload',(.68,.56,.24),.7,.3)
        trim=self.material('/World/Looks/Trim',(.045,.055,.075),.45,.3)
        concrete=self.material('/World/Looks/Concrete',(.12,.15,.18),.05,.85)
        markings=self.material('/World/Looks/Markings',(.9,.92,.94),0.,.8)
        UsdShade.MaterialBindingAPI.Apply(self.stage.GetPrimAtPath('/World/Booster')).Bind(white)
        UsdShade.MaterialBindingAPI.Apply(self.stage.GetPrimAtPath('/World/Payload')).Bind(satellite)
        payload_hull=UsdGeom.Cylinder(self.stage.GetPrimAtPath('/World/Payload/Hull'))
        payload_hull.CreateVisibilityAttr('invisible')
        fairing=UsdGeom.Cylinder.Define(self.stage,'/World/Payload/Fairing')
        fairing.CreateAxisAttr('Z');fairing.CreateRadiusAttr(1.8);fairing.CreateHeightAttr(7.)
        fairing.AddTranslateOp().Set(Gf.Vec3d(0,0,-1.))
        tip=UsdGeom.Cone.Define(self.stage,'/World/Payload/Nose')
        tip.CreateAxisAttr('Z');tip.CreateRadiusAttr(1.8);tip.CreateHeightAttr(2.)
        tip.AddTranslateOp().Set(Gf.Vec3d(0,0,3.5))
        UsdShade.MaterialBindingAPI.Apply(fairing.GetPrim()).Bind(white)
        UsdShade.MaterialBindingAPI.Apply(tip.GetPrim()).Bind(white)
        # Cold-gas roll jets, two opposite tangential pairs. No hot-fire effect.
        for index,(x,y) in enumerate(((1.8,.25),(1.8,-.25),(-1.8,.25),(-1.8,-.25))):
            jet=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/RollJet{index}')
            jet.CreateAxisAttr('Y');jet.CreateRadiusAttr(.12);jet.CreateHeightAttr(.4)
            jet.AddTranslateOp().Set(Gf.Vec3d(x,y,8.))
            UsdShade.MaterialBindingAPI.Apply(jet.GetPrim()).Bind(dark)
        # Close the interstage envelope and show the actual fixed foot positions.
        collar=UsdGeom.Cylinder.Define(self.stage,'/World/Booster/Interstage')
        collar.CreateAxisAttr('Z');collar.CreateRadiusAttr(physics.v['radius']);collar.CreateHeightAttr(3.)
        collar.AddTranslateOp().Set(Gf.Vec3d(0,0,physics.half-1.5))
        for z in (-16.,-8.,0.,8.,16.):
            band=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/Band{int(z+16)}')
            band.CreateAxisAttr('Z');band.CreateRadiusAttr(physics.v['radius']+.015);band.CreateHeightAttr(.045)
            band.AddTranslateOp().Set(Gf.Vec3d(0,0,z));UsdShade.MaterialBindingAPI.Apply(band.GetPrim()).Bind(trim)
        for i,(x,y) in enumerate(((6.2,0),(-6.2,0),(0,6.2),(0,-6.2))):
            a=np.array([x*.26,y*.26,-physics.half+7.]);b=np.array([x,y,-physics.half+.15])
            strut=UsdGeom.Cylinder.Define(self.stage,f'/World/Booster/Leg{i}')
            strut.CreateAxisAttr('Z');strut.CreateRadiusAttr(.14);strut.CreateHeightAttr(float(np.linalg.norm(b-a)))
            strut.AddTranslateOp().Set(Gf.Vec3d(*((a+b)/2)))
            r=Gf.Rotation(Gf.Vec3d(0,0,1),Gf.Vec3d(*(b-a))).GetQuat()
            strut.AddOrientOp().Set(Gf.Quatf(float(r.GetReal()),Gf.Vec3f(*r.GetImaginary())))
            UsdShade.MaterialBindingAPI.Apply(strut.GetPrim()).Bind(dark)
        nozzle=UsdGeom.Xform.Define(self.stage,'/World/Booster/Nozzle')
        nozzle.AddTranslateOp().Set(Gf.Vec3d(0,0,-physics.engine_lever));self.nozzle_rotation=nozzle.AddOrientOp()
        UsdShade.MaterialBindingAPI.Apply(nozzle.GetPrim()).Bind(dark)
        chamber=UsdGeom.Cylinder.Define(self.stage,'/World/Booster/Nozzle/ThrustChamber')
        chamber.CreateAxisAttr('Z');chamber.CreateRadiusAttr(.35);chamber.CreateHeightAttr(1.5)
        chamber.AddTranslateOp().Set(Gf.Vec3d(0,0,.75))
        # Axisymmetric open bell, physical nozzle exit is 1.5 m below pivot.
        profile=[(.35,0),(.38,-.25),(.46,-.65),(.66,-1.1),(.88,-1.5)]
        points=[];indices=[];counts=[];segments=48
        for radius,z in profile:
            for i in range(segments):
                angle=2*np.pi*i/segments;points.append(Gf.Vec3f(float(radius*np.cos(angle)),float(radius*np.sin(angle)),z))
        for row in range(len(profile)-1):
            for i in range(segments):
                indices.extend([row*segments+i,row*segments+(i+1)%segments,(row+1)*segments+(i+1)%segments,(row+1)*segments+i]);counts.append(4)
        mesh=UsdGeom.Mesh.Define(self.stage,'/World/Booster/Nozzle/Bell')
        mesh.CreatePointsAttr(points);mesh.CreateFaceVertexIndicesAttr(indices);mesh.CreateFaceVertexCountsAttr(counts)
        mesh.CreateDoubleSidedAttr(True);UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(dark)
        light=UsdLux.DistantLight.Define(self.stage,'/World/Sun');light.CreateIntensityAttr(2500.);light.CreateAngleAttr(.53)
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
        self.flame_light=UsdLux.SphereLight.Define(self.stage,'/World/Booster/Nozzle/Glow')
        self.flame_light.CreateRadiusAttr(.7);self.flame_light.CreateColorAttr(Gf.Vec3f(1.,.47,.12));self.flame_light.CreateIntensityAttr(0.)
        self.flame_light.AddTranslateOp().Set(Gf.Vec3d(0,0,-2.))
        self.landing_marker=None
        for name,site in (('Launch',physics.cfg['mission'].get('launch',[0,0])),('Landing',physics.cfg['mission']['pad'])):
            root='/World/'+name+'Site';site_root=UsdGeom.Xform.Define(self.stage,root)
            translate=site_root.AddTranslateOp();translate.Set(Gf.Vec3d(float(site[0]),float(site[1]),0))
            if name=='Landing':self.landing_marker=translate
            pad=UsdGeom.Cylinder.Define(self.stage,root+'/Pad');pad.CreateAxisAttr('Z');pad.CreateRadiusAttr(25.);pad.CreateHeightAttr(.1)
            pad.AddTranslateOp().Set(Gf.Vec3d(0,0,-.05))
            UsdShade.MaterialBindingAPI.Apply(pad.GetPrim()).Bind(concrete)
            points=[];indices=[]
            for index in range(128):
                angle=index*2*np.pi/128
                for radius in (23.2,23.5):points.append(Gf.Vec3f(float(radius*np.cos(angle)),float(radius*np.sin(angle)),.015))
                indices.extend([2*index,2*index+1,(2*((index+1)%128))+1,2*((index+1)%128)])
            ring=UsdGeom.Mesh.Define(self.stage,root+'/Perimeter');ring.CreatePointsAttr(points)
            ring.CreateFaceVertexCountsAttr([4]*128);ring.CreateFaceVertexIndicesAttr(indices);ring.CreateDoubleSidedAttr(True)
            ring.CreateSubdivisionSchemeAttr('none');UsdShade.MaterialBindingAPI.Apply(ring.GetPrim()).Bind(markings)
            self.painted_label(root+'/Label','LAUNCH LP-1' if name=='Launch' else 'LANDING LZ-1',markings)
            for axis in range(2):
                cross=UsdGeom.Cube.Define(self.stage,f'{root}/Cross{axis}');cross.CreateSizeAttr(1.)
                cross.AddTranslateOp().Set(Gf.Vec3d(0,0,.012));cross.AddScaleOp().Set(Gf.Vec3f(12. if axis==0 else .3,.3 if axis==0 else 12.,.02))
                UsdShade.MaterialBindingAPI.Apply(cross.GetPrim()).Bind(markings)
        launch=physics.cfg['mission'].get('launch',[0,0]);self.clamps=[]
        for index in range(4):
            angle=index*np.pi/2
            clamp=UsdGeom.Xform.Define(self.stage,f'/World/LaunchClamp{index}')
            clamp.AddTranslateOp().Set(Gf.Vec3d(float(launch[0]+np.cos(angle)*2.4),float(launch[1]+np.sin(angle)*2.4),2.5))
            orient=clamp.AddRotateXYZOp();self.clamps.append((orient,angle))
            beam=UsdGeom.Cube.Define(self.stage,f'/World/LaunchClamp{index}/Arm');beam.AddScaleOp().Set(Gf.Vec3f(.25,.25,2.5))
            UsdShade.MaterialBindingAPI.Apply(beam.GetPrim()).Bind(dark)
            jaw=UsdGeom.Cube.Define(self.stage,f'/World/LaunchClamp{index}/Jaw')
            jaw.AddTranslateOp().Set(Gf.Vec3d(float(-np.cos(angle)*.35),float(-np.sin(angle)*.35),1.7))
            jaw.AddRotateZOp().Set(float(np.rad2deg(angle)));jaw.AddScaleOp().Set(Gf.Vec3f(.55,.2,.18))
            UsdShade.MaterialBindingAPI.Apply(jaw.GetPrim()).Bind(dark)
        for index,(x,y) in enumerate(((12,-2),(12,2),(16,-2),(16,2))):
            column=UsdGeom.Cube.Define(self.stage,f'/World/ServiceTower/Column{index}')
            column.AddTranslateOp().Set(Gf.Vec3d(float(launch[0]+x),float(launch[1]+y),26));column.AddScaleOp().Set(Gf.Vec3f(.2,.2,26.))
            UsdShade.MaterialBindingAPI.Apply(column.GetPrim()).Bind(dark)
        for level in range(1,10):
            deck=UsdGeom.Cube.Define(self.stage,f'/World/ServiceTower/Deck{level}')
            deck.AddTranslateOp().Set(Gf.Vec3d(float(launch[0]+14),float(launch[1]),float(level*5.)))
            deck.AddScaleOp().Set(Gf.Vec3f(2.2,2.2,.08));UsdShade.MaterialBindingAPI.Apply(deck.GetPrim()).Bind(dark)
        if self.flow:self._flow_setup()
        from isaacsim.core.utils.viewports import set_camera_view
        set_camera_view(eye=np.array([90.,90.,60.]),target=np.array([0.,0.,25.]))

    def set_landing_target(self,target):
        self.landing_marker.Set(Gf.Vec3d(float(target[0]),float(target[1]),0))

    def camera(self,mode):
        self.follow=mode=='follow'
        if mode in ('free','follow'):return
        from isaacsim.core.utils.viewports import set_camera_view
        if mode=='vehicle':target=self.physics.position+np.array([0.,0.,4.])
        elif mode=='launch':target=np.array([*self.physics.cfg['mission'].get('launch',[0,0]),20.])
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
            attribute(emitter,'radius',Sdf.ValueTypeNames.Float,.7)
            attribute(emitter,'coupleRateVelocity',Sdf.ValueTypeNames.Float,100.)
            attribute(emitter,'coupleRateFuel',Sdf.ValueTypeNames.Float,100.)
            attribute(emitter,'coupleRateTemperature',Sdf.ValueTypeNames.Float,100.)
        for prim in Usd.PrimRange(plume.GetPrim()):
            if prim.GetTypeName()=='FlowSimulate':
                self.flow_simulates.append(prim)
                attribute(prim,'densityCellSize',Sdf.ValueTypeNames.Float,.3)
                attribute(prim,'stepsPerSecond',Sdf.ValueTypeNames.Float,30.)
                attribute(prim,'simulateWhenPaused',Sdf.ValueTypeNames.Bool,True)
                attribute(prim,'forceSimulate',Sdf.ValueTypeNames.Bool,True)
            if prim.GetTypeName()=='FlowAdvectionCombustionParams':
                attribute(prim,'gravity',Sdf.ValueTypeNames.Float3,Gf.Vec3f(0,0,-9.80665))
        settings=carb.settings.get_settings()
        settings.set('/rtx/flow/enabled',True)
        settings.set('/rtx/flow/pathTracingEnabled',True)
        # Actual temperature/density fields are supplied by NVIDIA Flow, not surface opacity.
        self.flow_asset=str(presets[0])
        from omni.flowusd import _flowusd
        self.flow_interface=_flowusd.acquire_flowusd_interface()

    def pause_effects(self,paused):
        if self.flow:
            for prim in self.flow_simulates:attribute(prim,'timeScale',Sdf.ValueTypeNames.Float,0. if paused else 1.)

    def update(self,physics):
        self.pause_effects(False)
        if self.sky_asset:
            # The local daylight environment is for an observer in atmosphere.
            # Fade it out for a camera following the high-altitude study.
            observer_height=max(0.,physics.position[2]) if self.follow else 60.
            self.sky.GetIntensityAttr().Set(float(self.sky_intensity*np.exp(-max(0.,observer_height-12000.)/8500.)))
        release=min(1.,max(0.,(physics.data.time-(physics.release_time or physics.data.time))/.5)) if physics.release_time is not None else 0.
        for orient,angle in self.clamps:orient.Set(Gf.Vec3f(float(-np.sin(angle)*release*70),float(np.cos(angle)*release*70),0))
        direction=np.array([np.tan(physics.gimbal[0]),np.tan(physics.gimbal[1]),1.]);direction/=np.linalg.norm(direction)
        rotation=Gf.Rotation(Gf.Vec3d(0,0,1),Gf.Vec3d(*direction)).GetQuat()
        self.nozzle_rotation.Set(Gf.Quatf(float(rotation.GetReal()),Gf.Vec3f(*rotation.GetImaginary())))
        self.flame_light.GetIntensityAttr().Set(float(physics.throttle*100000.))
        if self.flow:
            axis=physics.rotation()@direction
            exit_position=physics.position+physics.rotation()@np.array([0,0,-physics.engine_lever])-axis*1.5
            for emitter in self.flow_emitters:
                attribute(emitter,'position',Sdf.ValueTypeNames.Float3,Gf.Vec3f(*exit_position))
                enabled=emitter.GetAttribute('enabled')
                if enabled:enabled.Set(bool(physics.throttle>.02))
                velocity=emitter.GetAttribute('velocity')
                if velocity:velocity.Set(Gf.Vec3f(*(-axis*(40+100*physics.throttle))))
        if self.follow and physics.data.time-self.last_camera>.1:
            from isaacsim.core.utils.viewports import set_camera_view
            self.last_camera=physics.data.time
            set_camera_view(eye=physics.position+np.array([75.,75.,25.]),target=physics.position)

    def capture(self,app,path,view='vehicle'):
        """Export a native render artifact; does not capture the user's desktop."""
        import asyncio
        import time
        from isaacsim.core.utils.viewports import set_camera_view
        from omni.kit.viewport.utility import capture_viewport_to_file,get_active_viewport
        if view=='engine':
            target=self.physics.position+np.array([0.,0.,-self.physics.engine_lever-3.])
            eye=target+np.array([14.,14.,-1.])
        elif view=='launch':
            launch=self.physics.cfg['mission'].get('launch',[0,0]);target=np.array([*launch,15.]);eye=target+np.array([85.,85.,40.])
        else:target=self.physics.position+np.array([0.,0.,5.]);eye=self.physics.position+np.array([90.,90.,22.])
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
        # Kit completes GPU readback before the asynchronous image writer flushes.
        # Wait for both signals, and never accept an artifact from an earlier run.
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
