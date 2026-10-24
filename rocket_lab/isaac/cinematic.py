"""Two-pass cinematic capture: record the live flight, render the film offline.

Pass 1 runs during the mission: physics steps at full real-time speed with no
rendering-for-recording overhead while FlightTrack samples every physical
substep (120 Hz) — booster pose, upper-stage pose, engine state, wind.

Pass 2 runs after touchdown: the track is replayed frame-exactly at the output
frame rate through PlaybackPhysics (the same NativeVisuals.update consumes it),
a shot-list camera director frames each moment like launch coverage, and every
frame is rendered once through a Replicator render product into an ffmpeg
NVENC pipe. Because no wall clock is involved, playback is perfectly smooth at
any resolution and sample count the GPU can afford per frame.
"""
from pathlib import Path
import math
import os
import shutil
import subprocess
import time

import numpy as np
from scipy.spatial.transform import Rotation


class FlightTrack:
    """Uniformly sampled physical history of one flight, 120 Hz native."""

    KEYS=('t','position','quaternion','velocity','omega','throttle','gimbal',
          'wind','payload_position','payload_quaternion')

    def __init__(self):
        self._data={key:[] for key in self.KEYS}
        self._phase=[]      # 0 = combined/on pad, 1 = ascending, 2 = separated descent
        self.release_time=None
        self.outcome=None

    def capture(self,physics):
        payload_position=physics.position+physics.rotation()@np.array([0.,0.,physics.half+4.5])
        payload_quaternion=physics.quaternion
        if physics.detached:
            poses,quaternions=physics.payload.get_world_poses()
            payload_position=np.asarray(poses[0],dtype=float);payload_quaternion=np.asarray(quaternions[0],dtype=float)
        self._data['t'].append(float(physics.data.time))
        self._data['position'].append(np.asarray(physics.position,dtype=float))
        self._data['quaternion'].append(np.asarray(physics.quaternion,dtype=float))
        self._data['velocity'].append(np.asarray(physics.velocity,dtype=float))
        self._data['omega'].append(np.asarray(physics.omega_world,dtype=float))
        self._data['throttle'].append(float(physics.throttle))
        self._data['gimbal'].append(np.asarray(physics.gimbal,dtype=float))
        self._data['wind'].append(np.asarray(physics.wind,dtype=float))
        self._data['payload_position'].append(payload_position)
        self._data['payload_quaternion'].append(payload_quaternion)
        if physics.release_time is not None and self.release_time is None:
            self.release_time=float(physics.release_time)
        self._phase.append(2 if physics.detached else (1 if self.release_time is not None else 0))

    def finalize(self,outcome=None):
        self.outcome=outcome
        self.t=np.asarray(self._data['t'],dtype=float)
        self.position=np.stack(self._data['position'])
        self.quaternion=np.stack(self._data['quaternion'])
        self.velocity=np.stack(self._data['velocity'])
        self.omega=np.stack(self._data['omega'])
        self.throttle=np.asarray(self._data['throttle'],dtype=float)
        self.gimbal=np.stack(self._data['gimbal'])
        self.wind=np.stack(self._data['wind'])
        self.payload_position=np.stack(self._data['payload_position'])
        self.payload_quaternion=np.stack(self._data['payload_quaternion'])
        self.phase=np.asarray(self._phase,dtype=np.int32)
        self._data=None
        return self

    @property
    def duration(self):return float(self.t[-1]-self.t[0])

    def save(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(path,t=self.t,position=self.position,quaternion=self.quaternion,
            velocity=self.velocity,omega=self.omega,throttle=self.throttle,gimbal=self.gimbal,
            wind=self.wind,payload_position=self.payload_position,
            payload_quaternion=self.payload_quaternion,phase=self.phase,
            release_time=np.asarray([self.release_time if self.release_time is not None else -1.]))
        return path

    @classmethod
    def load(cls,path):
        blob=np.load(path)
        track=cls.__new__(cls)
        for key in ('t','position','quaternion','velocity','omega','throttle','gimbal','wind',
                    'payload_position','payload_quaternion','phase'):
            setattr(track,key,blob[key])
        release=float(blob['release_time'][0]);track.release_time=release if release>=0 else None
        track.outcome=None;track._data=None
        return track

    def events(self):
        """Mission milestones derived from the recorded history itself."""
        ignition=None
        burning=self.throttle>.2
        if burning.any():ignition=float(self.t[np.argmax(burning)])
        # While attached the payload always rides ~24.5 m above the booster
        # center; separation is the gap growing well past that stacked baseline.
        gap=np.linalg.norm(self.payload_position-self.position,axis=1)
        separation=None
        apart=gap>gap[0]+8.
        if apart.any():separation=float(self.t[np.argmax(apart)])
        landing_burn=None
        if separation is not None:
            burn_after=burning&(self.t>separation)
            if burn_after.any():landing_burn=float(self.t[np.argmax(burn_after)])
        touchdown=None
        if separation is not None:
            # Settling is the LAST slow near-ground sample, not the first:
            # the falling booster passes through low speeds mid-descent.
            min_z=float(self.position[:,2].min())
            near_ground=self.position[:,2]<min_z+1.2
            settled=near_ground&(np.linalg.norm(self.velocity,axis=1)<8.)
            if settled.any():touchdown=float(self.t[np.where(settled)[0][-1]])
            elif near_ground.any():touchdown=float(self.t[np.where(near_ground)[0][-1]])
        return dict(ignition=ignition,separation=separation,landing_burn=landing_burn,touchdown=touchdown)

    def sample(self,time):
        """State at an arbitrary time: linear poses, slerp orientations."""
        index=int(np.searchsorted(self.t,time))
        index=max(1,min(index,len(self.t)-1))
        t0,t1=self.t[index-1],self.t[index]
        span=max(t1-t0,1e-9);alpha=float(np.clip((time-t0)/span,0.,1.))
        def lerp(a,b):return (1.-alpha)*a+alpha*b
        def nlerp(qa,qb):
            # 120 Hz keyframes: adjacent quaternions differ by <0.1 deg, so
            # normalized linear interpolation is visually identical to slerp.
            blended=(1.-alpha)*qa+alpha*qb
            blended=blended/np.linalg.norm(blended)
            if blended[0]<0.:blended=-blended
            return blended
        quaternion=nlerp(self.quaternion[index-1],self.quaternion[index])
        payload_quaternion=nlerp(self.payload_quaternion[index-1],self.payload_quaternion[index])
        return dict(position=lerp(self.position[index-1],self.position[index]),
            quaternion=quaternion,
            velocity=lerp(self.velocity[index-1],self.velocity[index]),
            omega=lerp(self.omega[index-1],self.omega[index]),
            throttle=lerp(self.throttle[index-1],self.throttle[index]),
            gimbal=lerp(self.gimbal[index-1],self.gimbal[index]),
            wind=lerp(self.wind[index-1],self.wind[index]),
            payload_position=lerp(self.payload_position[index-1],self.payload_position[index]),
            payload_quaternion=payload_quaternion,
            phase=int(self.phase[index-1]))


class PlaybackPhysics:
    """Duck-typed physics view that NativeVisuals.update consumes during replay."""

    def __init__(self,cfg,track,half,engine_lever):
        self.cfg=cfg;self.track=track;self.half=half;self.engine_lever=engine_lever
        self.position=np.zeros(3);self.quaternion=np.array([1.,0.,0.,0.])
        self.velocity=np.zeros(3);self.omega_world=np.zeros(3);self.wind=np.zeros(3)
        self.throttle=0.;self.gimbal=np.zeros(2);self.phase='takeoff'
        self.release_time=track.release_time;self.attached=True
        from types import SimpleNamespace
        self.data=SimpleNamespace(time=0.)
        self._rotation=np.eye(3)

    def apply(self,state,time):
        self.position=state['position'];self.quaternion=state['quaternion']
        self.velocity=state['velocity'];self.omega_world=state['omega']
        self.throttle=state['throttle'];self.gimbal=state['gimbal'];self.wind=state['wind']
        self.phase='landing' if state['phase']==2 else 'takeoff'
        self.attached=state['phase']!=2
        self.data.time=time
        self._rotation=Rotation.from_quat([*self.quaternion[1:],self.quaternion[0]]).as_matrix()

    def rotation(self):return self._rotation


def smoothstep(edge0,edge1,x):
    t=float(np.clip((x-edge0)/(edge1-edge0),0.,1.));return t*t*(3.-2.*t)


class CameraDirector:
    """Launch-coverage shot list keyed on events mined from the flight track."""

    def __init__(self,cfg,track,half):
        self.track=track;self.half=half
        self.launch=np.array([*cfg['mission'].get('launch',[0,0])[:2],0.],dtype=float)
        self.pad=np.array([*cfg['mission']['pad'][:2],0.],dtype=float)
        self.events=track.events()
        ignition=self.events['separation'] or self.events['ignition'] or track.t[0]
        self.t_start=max(float(track.t[0]),ignition-4.0)
        # Hold on the parked vehicle after a real touchdown; never freeze a
        # mid-air pose beyond the recorded track (timeout/crash endings).
        touchdown=self.events['touchdown']
        settled=touchdown is not None and touchdown>=track.t[-1]-1.5
        self.t_end=float(track.t[-1])+(8. if settled else 0.)
        self.shots=self._build_shots()

    def _build_shots(self):
        events=self.events;track=self.track
        t0=self.t_start
        separation=events['separation'] if events['separation'] is not None else self.t_end
        landing_burn=events['landing_burn'] if events['landing_burn'] is not None else separation+20.
        touchdown=events['touchdown'] if events['touchdown'] is not None else min(landing_burn+18.,self.t_end)
        ignition=events['ignition'] if events['ignition'] is not None else t0+2.
        shots=[]
        def add(start,end,fn,fov=50.,name='shot'):shots.append((start,end,fn,fov,name))
        # 1. Establishing wide: whole pad complex, slow push-in through ignition.
        def establishing(p,t):
            d=150.-46.*p
            eye=self.launch+np.array([d*.62,-d*.82,26.-8.*p]);target=self.launch+np.array([0,0,22.])
            return eye,target
        add(t0,ignition+2.0,establishing,fov=33.,name="establishing_wide")
        # 2. Ignition close-up: octaweb, deluge steam, clamp release.
        def ignition_close(p,t):
            a=2.45-1.1*p
            eye=self.launch+np.array([np.cos(a)*31.,np.sin(a)*31.,5.2+2.6*p])
            booster=self.track.sample(t)['position']
            # Tilt up with the climbing stack; keeps the plume base in frame.
            return eye,np.array([booster[0],booster[1],max(booster[2]-12.,3.)])
        add(ignition+2.0,ignition+6.5,ignition_close,fov=58.,name="ignition_closeup")
        # 3. Tower rise: level with the interstage as it passes the gantry.
        def tower_rise(p,t):
            s=self.track.sample(t);height=s['position'][2]
            eye=self.launch+np.array([34.,-30.,min(max(height*.85,8.),52.)])
            return eye,s['position']-np.array([0.,0.,4.])
        add(ignition+6.5,ignition+11.5,tower_rise,fov=47.,name="tower_rise")
        # 4. Ascent telephoto tracking from the press site: aim below center so
        # the exhaust plume stays in frame, like real pad tracking cameras.
        def ascent_tracking(p,t):
            s=self.track.sample(t);eye=self.launch+np.array([190.,-240.,4.])
            return eye,s['position']-np.array([0.,0.,8.])
        add(ignition+11.5,max(separation-1.5,ignition+13.),ascent_tracking,fov=170.,name="ascent_telephoto")
        # 5. Separation: camera sits between the two vehicles.
        def separation_shot(p,t):
            s=self.track.sample(t);mid=.5*(s['position']+s['payload_position'])
            axis=s['payload_position']-s['position'];axis/=max(np.linalg.norm(axis),1e-6)
            side=np.cross(axis,[0.,0.,1.])
            if np.linalg.norm(side)<1e-4:side=np.array([1.,0.,0.])  # axis is vertical: stack still joined
            side=side/np.linalg.norm(side)
            eye=mid+side*(46.-8.*p)+np.array([0.,0.,8.])
            return eye,mid
        add(max(separation-1.5,ignition+13.),separation+5.,separation_shot,fov=50.,name="separation")
        # 6. Descent chase: slow orbit around the falling booster.
        def descent_chase(p,t):
            s=self.track.sample(t);az=2.9+p*1.15;d=42.+6.*math.sin(p*math.pi)
            eye=s['position']+np.array([np.cos(az)*d,np.sin(az)*d,6.-10.*p])
            return eye,s['position']+np.array([0.,0.,-2.])
        add(separation+5.,max(landing_burn-1.,separation+8.),descent_chase,fov=60.,name="descent_chase")
        # 7. Landing long lens: ground camera at the recovery zone.
        def approach(p,t):
            s=self.track.sample(t);eye=self.pad+np.array([92.,-118.,3.5])
            # 85 mm keeps the 40 m booster in frame until the final seconds;
            # aim below center so the landing burn plume never leaves view.
            return eye,s['position']-np.array([0.,0.,4.])
        add(max(landing_burn-1.,separation+8.),touchdown-2.5,approach,fov=85.,name="landing_approach")
        # 8. Touchdown: bullseye level, legs compress, steam clears.
        def touchdown_close(p,t):
            s=self.track.sample(t);a=.62+.35*p
            eye=self.pad+np.array([np.cos(a)*34.,np.sin(a)*34.,4.5])
            return eye,s['position']+np.array([0.,0.,8.])
        add(touchdown-2.5,touchdown+5.5,touchdown_close,fov=52.,name="touchdown")
        # 9. Beauty orbit: recovered vehicle on the pad, sun behind camera.
        def beauty(p,t):
            a=.95+p*.9;eye=self.pad+np.array([np.cos(a)*58.,np.sin(a)*58.,9.+3.*p])
            return eye,self.pad+np.array([0.,0.,16.])
        add(touchdown+5.5,self.t_end,beauty,fov=40.,name="beauty_orbit")
        # Drop degenerate shots and enforce ordering.
        cleaned=[]
        for shot in shots:
            start,end,fn,fov,name=shot
            end=min(end,self.t_end)
            if end<=start+0.15:continue
            if cleaned and start<cleaned[-1][1]:start=cleaned[-1][1]
            if end<=start+0.15:continue
            cleaned.append((start,end,fn,fov,name))
        return cleaned or [(t0,self.t_end,lambda p,t:(self.launch+np.array([120.,-150.,20.]),self.launch+np.array([0.,0.,20.])),40.,'fallback')]

    def frame(self,time):
        """Camera eye/target/focal-length at an arbitrary replay time."""
        selected=self.shots[-1]
        for shot in self.shots:
            if shot[0]<=time<shot[1]:selected=shot;break
        start,end,fn,fov,name=selected
        progress=smoothstep(0.,1.,(time-start)/(end-start))
        eye,target=fn(progress,time)
        return np.asarray(eye,dtype=float),np.asarray(target,dtype=float),fov


PRESETS={
    'balanced':dict(subframes=4,fog=True,motion_blur=False),
    'cinematic':dict(subframes=10,fog=True,motion_blur=False),
    'pathtraced':dict(subframes=24,fog=True,motion_blur=False),
}


class OfflineRenderer:
    """Replay a FlightTrack into an MP4: one render per output frame."""

    def __init__(self,visuals,stage,preset='cinematic',fps=60.,size=(1920,1080),cq=19):
        self.visuals=visuals;self.stage=stage
        self.preset=PRESETS[preset];self.fps=float(fps);self.size=(int(size[0]),int(size[1]));self.cq=int(cq)

    def _apply_quality(self):
        import carb
        settings=carb.settings.get_settings()
        # Coastal aerial perspective: soft distance haze toward the horizon.
        if self.preset['fog']:
            settings.set('/rtx/fog/enabled',True)
            settings.set('/rtx/fog/fogColor',[0.62,0.70,0.80])
            settings.set('/rtx/fog/fogStartDist',900.)
            settings.set('/rtx/fog/fogEndDist',11000.)
            settings.set('/rtx/fog/fogHeightFalloff',.012)
        settings.set('/rtx/post/motionblur/enabled',bool(self.preset['motion_blur']))
        settings.set('/rtx/post/bloom/enabled',False)
        settings.set('/rtx/post/glare/enabled',False)

    def _encoder_command(self,path):
        ffmpeg=shutil.which('ffmpeg')or os.environ.get('ROCKET_FFMPEG')
        if not ffmpeg:raise RuntimeError('ffmpeg not found on PATH; install ffmpeg or set ROCKET_FFMPEG')
        command=[ffmpeg,'-hide_banner','-loglevel','error','-y',
            '-f','rawvideo','-pix_fmt','rgb24','-s',f'{self.size[0]}x{self.size[1]}',
            '-r',f'{self.fps:g}','-i','pipe:0']
        command+=['-c:v','h264_nvenc','-preset','p6','-tune','hq','-rc','vbr',
            '-cq',str(self.cq),'-b:v','0','-pix_fmt','yuv420p','-movflags','+faststart',str(path)]
        return command

    def render(self,track:FlightTrack,path,physics_constants,on_frame=None):
        """Render the full track; returns stats dict. physics_constants: (cfg,half,engine_lever)."""
        import omni.replicator.core as rep
        from pxr import Gf,Sdf,UsdGeom
        from scipy.spatial.transform import Rotation
        self._apply_quality()
        cfg,half,engine_lever=physics_constants
        director=CameraDirector(cfg,track,half)
        playback=PlaybackPhysics(cfg,track,half,engine_lever)
        visuals=self.visuals
        visuals.mode='free';visuals.follow=False;visuals.last_camera=-1.

        booster=self.stage.GetPrimAtPath('/World/Booster');payload=self.stage.GetPrimAtPath('/World/Payload')
        # The film renders through /OmniverseKit_Persp driven by the viewport
        # API: authored xform ops on standalone camera prims proved unreliable
        # (read-back and hydra disagreed in full-scene sessions), while
        # set_camera_view is the same proven path the live follow camera uses.
        from isaacsim.core.utils.viewports import set_camera_view
        camera=self.stage.GetPrimAtPath('/OmniverseKit_Persp')

        def aim(eye,target,focal):
            set_camera_view(eye=np.asarray(eye,float),target=np.asarray(target,float))
            camera.GetPrim().GetAttribute('focalLength').Set(float(focal))

        product=rep.create.render_product('/OmniverseKit_Persp',self.size)
        annotator=rep.AnnotatorRegistry.get_annotator('rgb');annotator.attach(product)

        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.unlink(missing_ok=True)
        process=subprocess.Popen(self._encoder_command(path),stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)

        t_start,t_end=director.t_start,director.t_end
        frames=int(math.ceil((t_end-t_start)*self.fps))
        started=time.monotonic();encoded=0
        try:
            for frame in range(frames):
                time_s=t_start+frame/self.fps
                state=track.sample(time_s)
                playback.apply(state,time_s)
                with Sdf.ChangeBlock():
                    booster.GetAttribute('xformOp:translate').Set(Gf.Vec3d(*map(float,state['position'])))
                    booster.GetAttribute('xformOp:orient').Set(Gf.Quatf(float(state['quaternion'][0]),Gf.Vec3f(*map(float,state['quaternion'][1:]))))
                    payload.GetAttribute('xformOp:translate').Set(Gf.Vec3d(*map(float,state['payload_position'])))
                    payload.GetAttribute('xformOp:orient').Set(Gf.Quatf(float(state['payload_quaternion'][0]),Gf.Vec3f(*map(float,state['payload_quaternion'][1:]))))
                visuals.update(playback)
                eye,target,focal=director.frame(time_s)
                aim(eye,target,focal)
                if frame%120==0:
                    print(f'CINECAM f{frame}: eye=({eye[0]:.0f},{eye[1]:.0f},{eye[2]:.0f}) target=({target[0]:.0f},{target[1]:.0f},{target[2]:.0f}) focal={focal:.0f}',flush=True)
                rep.orchestrator.step(rt_subframes=self.preset['subframes'],pause_timeline=True)
                data=np.asarray(annotator.get_data())
                if data.dtype!=np.uint8:data=np.clip(data,0,255).astype(np.uint8)
                frame_rgb=np.ascontiguousarray(data[...,:3])
                process.stdin.write(frame_rgb.tobytes());encoded+=1
                if on_frame and frame%on_frame==0:
                    elapsed=time.monotonic()-started
                    print(f'CINEMATIC: frame {frame+1}/{frames} ({elapsed:.0f}s elapsed, ~{elapsed/max(frame+1,1)*1000:.0f} ms/frame)',flush=True)
        finally:
            process.stdin.close();stderr=process.stderr.read().decode(errors='replace');code=process.wait()
            annotator.detach();product.destroy()
        if code!=0:raise RuntimeError(f'ffmpeg failed ({code}): {stderr[:500]}')
        if encoded<frames*.5:raise RuntimeError(f'Only {encoded}/{frames} frames encoded')
        elapsed=time.monotonic()-started
        return dict(frames=encoded,fps=self.fps,width=self.size[0],height=self.size[1],
            seconds=float((t_end-t_start)),wall_seconds=elapsed,ms_per_frame=elapsed*1000./max(encoded,1),
            bytes=path.stat().st_size,preset=self.preset,video=str(path),
            events={k:(v if v is None else round(v,2)) for k,v in director.events.items()},
            shots=[dict(name=name,start=round(s,2),end=round(e,2),focal=fov) for s,e,f,fov,name in director.shots])
