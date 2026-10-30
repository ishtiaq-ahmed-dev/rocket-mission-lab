"""Two-pass cinematic capture: record the live flight, render the film offline.

Pass 1 runs during the mission: physics steps at full real-time speed with no
rendering-for-recording overhead while FlightTrack samples every physical
substep (120 Hz) — booster pose, upper-stage pose, engine state, wind.

Pass 2 runs after touchdown: the track is replayed frame-exactly at the output
frame rate through PlaybackPhysics (the same NativeVisuals.update consumes it),
a shot-list camera director frames each moment like launch coverage, and every
frame is rendered once through a Replicator render product into an ffmpeg NVENC
pipe. Because no wall clock is involved, playback is perfectly smooth at any
resolution and sample count the GPU can afford per frame.

The edit is a highlight reel like a real broadcast: launch, staging, the
booster flip, the landing burn and touchdown play at real speed; the long
coasts between them are time-compressed instead of being padded with distant
wide shots. Every camera stays inside tight close coverage (~15-70 m).
"""
from pathlib import Path
import json
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
        """Mission milestones derived from the recorded history itself.

        Separation is the first sample where the vehicle is detached: the
        boolean phase is exact, while a payload-gap threshold trails the
        release by many seconds (the pusher imparts only ~0.02 m/s).
        """
        t=self.t
        ignition=None
        burning=self.throttle>.2
        if burning.any():ignition=float(t[np.argmax(burning)])
        detached=np.flatnonzero(self.phase==2)
        separation=float(t[detached[0]]) if detached.size else None
        touchdown=None;landing_burn=None
        if separation is not None:
            min_z=float(self.position[:,2].min())
            near_ground=self.position[:,2]<min_z+1.2
            settled=near_ground&(np.linalg.norm(self.velocity,axis=1)<8.)
            if settled.any():touchdown=float(t[np.where(settled)[0][-1]])
            elif near_ground.any():touchdown=float(t[np.where(near_ground)[0][-1]])
            if touchdown is not None:
                # The landing burn is the last throttle block before touchdown;
                # the first post-separation burn is the boostback.
                end=int(np.searchsorted(t,touchdown))
                block=burning[:end]
                lit=np.flatnonzero(block)
                if lit.size:
                    start=lit[-1]
                    while start-1>=0 and block[start-1]:start-=1
                    landing_burn=float(t[start])
        boostback=None
        if separation is not None:
            after=burning&(t>separation+1.)
            if after.any():boostback=float(t[np.argmax(after)])
        return dict(ignition=ignition,liftoff=self.release_time,separation=separation,
                    boostback=boostback,landing_burn=landing_burn,touchdown=touchdown)

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
        self.rest=half+float(cfg['mission'].get('launch_stand_height',0.))
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


class FilmTimeline:
    """Highlight edit: maps film seconds to track seconds with compressed coasts.

    A negative speed is a HOLD: the frame freezes on track time `start` for
    -speed seconds. That gives the edit a pre-ignition beat on the pad without
    inventing frames the flight never recorded.
    """

    def __init__(self,segments):
        self.segments=[(float(a),float(b),float(speed)) for a,b,speed in segments]
        self._starts=[];clock=0.
        for start,end,speed in self.segments:
            self._starts.append(clock)
            clock+=(-speed) if speed<0 else (end-start)/speed
        self.duration=clock

    @staticmethod
    def _length(start,end,speed):
        return (-speed) if speed<0 else (end-start)/speed

    def track_time(self,film_time):
        film_time=float(np.clip(film_time,0.,max(self.duration,1e-6)))
        index=int(np.searchsorted(self._starts,film_time,side='right'))-1
        index=max(0,min(index,len(self.segments)-1))
        start,end,speed=self.segments[index]
        if speed<0:return start
        return start+(film_time-self._starts[index])*speed

    def film_time(self,track_time):
        for (start,end,speed),film_start in zip(self.segments,self._starts):
            if speed<0:continue
            if track_time<=end:return film_start+(max(start,track_time)-start)/speed
        start,end,speed=self.segments[-1]
        if speed<0:return self._starts[-1]
        return self._starts[-1]+(track_time-start)/speed

    def export(self):
        rows=[]
        for (start,end,speed),film_start in zip(self.segments,self._starts):
            rows.append(dict(film_start=round(film_start,3),
                film_end=round(film_start+self._length(start,end,speed),3),
                track_start=round(start,3),track_end=round(end,3),speed=max(speed,0.)))
        return rows


class CameraDirector:
    """Tight launch-coverage shot list keyed on events mined from the flight track.

    Every eye is 15-70 m from the hardware: pad track, liftoff crane, close
    chase, staging close-up, booster flip, engine-level landing burn and a
    ground-level touchdown. No distant press-site telephoto, no orbiting drone
    that drifts away.
    """

    def __init__(self,cfg,track,half):
        self.track=track;self.half=half
        self.launch=np.array([*cfg['mission'].get('launch',[0,0])[:2],0.],dtype=float)
        # Landing coordinates are not in config.yaml (the runner injects them);
        # the recovered booster's own final position is the pad.
        self.pad=np.array([float(track.position[-1][0]),float(track.position[-1][1]),0.])
        self.events=track.events()
        self.t_last=float(track.t[-1])
        self.timeline=self._build_timeline()
        self.t_start=self.timeline.track_time(0.)
        self.t_end=self.timeline.track_time(self.timeline.duration)
        self.shots=self._build_shots()

    def _build_timeline(self):
        track=self.track;ev=self.events
        t0=float(track.t[0]);t_last=float(track.t[-1])
        ignition=ev['ignition'] if ev['ignition'] is not None else t0
        liftoff=ev['liftoff'] if ev['liftoff'] is not None else min(ignition+1.5,t_last)
        separation=ev['separation'];boostback=ev['boostback']
        burn=ev['landing_burn'];touchdown=ev['touchdown']
        start=max(t0,min(ignition-2.5,liftoff-1.5))
        # Three seconds parked on the pad before the clock starts: real webcast
        # coverage always opens on the vehicle, and the edit had none.
        segments=[(start,start,-3.0)]
        cursor=start
        def add(a,b,speed):
            nonlocal cursor
            a=float(max(a,cursor));b=float(min(max(b,a+.02),t_last+14.))
            if b-a>.05:segments.append((a,b,speed));cursor=b
        # Ignition and the first seconds of climb at real speed.
        climb_end=min(liftoff+17.5,(separation-3.) if separation else liftoff+17.5)
        add(start,max(climb_end,start+3.),1.)
        if separation:
            add(cursor,separation-3.,6.)
            add(cursor,separation+6.5,1.)
        if boostback:
            # The flip and boostback burn are the visual peak of the return.
            add(cursor,boostback+12.,1.)
        if burn:
            add(cursor,burn-7.,12.)
            add(cursor,(touchdown if touchdown is not None else burn+18.)+5.,1.)
        elif touchdown:
            add(cursor,touchdown+5.,12.)
        if touchdown is None:
            add(cursor,t_last,1.)
        else:
            # Hold on the recovered booster while the steam clears.
            add(cursor,t_last+13.,1.)
        return FilmTimeline(segments or [(start,t_last,1.)])

    def _build_shots(self):
        ev=self.events;track=self.track
        t0=self.t_start;end=self.t_end
        liftoff=ev['liftoff'] if ev['liftoff'] is not None else t0+1.
        separation=ev['separation'] if ev['separation'] is not None else end
        boostback=ev['boostback'] if ev['boostback'] is not None else separation+8.
        burn=ev['landing_burn'] if ev['landing_burn'] is not None else end-20.
        touchdown=ev['touchdown'] if ev['touchdown'] is not None else end-4.
        shots=[]
        def add(a,b,fn,focal,name):
            a=max(a,t0);b=min(b,end)
            if b>a+.05:shots.append((a,b,fn,focal,name))
        def side(azimuth):
            return np.array([np.cos(azimuth),np.sin(azimuth),0.])

        # Focal length picks the perspective (wide = dramatic, long = compressed
        # press-site look); distance is solved per frame by _fit so the subject
        # always sits inside the gate with air around it. Nothing is ever
        # cropped and no shot needs a far-away wide framing to see the vehicle.

        # Ground cameras return an absolute eye; chase cameras return a sight
        # direction from the subject centre. Either way the framing solver in
        # frame() sets the distance.
        def ground(anchor,azimuth,distance,height=2.4):
            return lambda p,t: (anchor+np.array([np.cos(azimuth(p)),np.sin(azimuth(p)),0.])*distance+np.array([0.,0.,height]),'eye')

        # 1. Pad: full stack on the mount, deluge and ignition, slow push-in.
        add(t0,liftoff+2.5,ground(self.launch,lambda p:2.42+.12*p,64.,2.2),28.,'pad_ignition')
        # 2. Liftoff: ground camera at the pad edge tracking the climb.
        add(liftoff+2.5,liftoff+8.,ground(self.launch,lambda p:2.1+.5*p,52.,2.2),24.,'liftoff_track')
        # 3. Ascent chase: alongside the stack, a touch below the engine plane
        #    so the exhaust is seen against the sky, not the ground.
        def ascent_chase(p,t):
            return side(1.35+.45*p)-np.array([0.,0.,.18]),None
        add(liftoff+8.,separation-3.,ascent_chase,24.,'ascent_chase')
        # 4. Staging: level with the interstage as the stack opens up.
        def separation_shot(p,t):
            s=track.sample(t)
            axis=s['payload_position']-s['position'];axis/=max(np.linalg.norm(axis),1e-6)
            lateral=np.cross(axis,[0.,0.,1.])
            if np.linalg.norm(lateral)<1e-3:lateral=np.array([1.,0.,0.])
            lateral/=np.linalg.norm(lateral)
            return lateral+np.array([0.,0.,.10]),'detail'
        add(separation-3.,separation+6.5,separation_shot,40.,'stage_separation')
        # 5. Flip: whole booster while it turns, engine bay in view.
        def flip(p,t):
            return side(2.0-.55*p)-np.array([0.,0.,.10]),None
        add(separation+6.5,boostback+6.,flip,26.,'booster_flip')
        # 6. Boostback / descent: below and off to the side, plume against the plain.
        def boostback_shot(p,t):
            return side(1.1+.35*p)-np.array([0.,0.,.35]),None
        add(boostback+6.,burn-7.,boostback_shot,30.,'descent_chase')
        # 7. Landing burn: low ground-level angle, legs, fins and full plume.
        add(burn-7.,touchdown-4.,ground(self.pad,lambda p:2.2+.25*p,46.,2.2),26.,'landing_burn')
        # 8. Touchdown: ground camera beside the pad, eye-level with the legs.
        add(touchdown-4.,touchdown+5.,ground(self.pad,lambda p:2.15+.35*p,40.,2.1),24.,'touchdown')
        # 9. Reveal: slow orbit of the recovered vehicle.
        def reveal(p,t):
            return np.array([np.cos(.7+.75*p),np.sin(.7+.75*p),.18+.10*p]),None
        add(touchdown+5.,end,reveal,30.,'recovered')
        if not shots:shots.append((t0,end,lambda p,t:(np.array([1.,0.,0.]),None),26.,'fallback'))
        shots.sort(key=lambda shot:shot[0])
        return shots

    def _subject(self,time):
        """World-space silhouette of the hardware at `time`, plus its centre.

        The framing solver needs real points: engine bay, hull silhouette at
        quarter/ half/ three-quarter length, upper-stage nose and the tip of
        the exhaust plume. Without the plume points every shot framed the
        vehicle and cut the flame off at the bottom of the gate.
        """
        state=self.track.sample(time)
        quaternion=state['quaternion']
        rotation=Rotation.from_quat([quaternion[1],quaternion[2],quaternion[3],quaternion[0]]).as_matrix()
        up=rotation[:,2]
        base=state['position']-up*self.half
        top=state['position']+up*self.half
        clearance=max(0.,float(base[2]))
        plume=0.
        if state['throttle']>.03:
            plume=min(13.5*float(state['throttle']),max(.35*clearance,1.2))
        plume_tip=base-up*plume
        payload_quaternion=state['payload_quaternion']
        payload_rotation=Rotation.from_quat([payload_quaternion[1],payload_quaternion[2],
            payload_quaternion[3],payload_quaternion[0]]).as_matrix()
        payload_up=payload_rotation[:,2]
        payload_base=state['payload_position']-payload_up*4.5
        payload_top=state['payload_position']+payload_up*4.9
        attached=state['phase']!=2
        points=[]
        for center,radius in ((base,1.9),(base+up*self.half*.5,1.9),(top,1.9)):
            for k in range(8):
                angle=k*np.pi/4
                points.append(center+np.array([np.cos(angle),np.sin(angle),0.])*radius)
        if plume>1.:
            points.append(plume_tip)
            points.append(plume_tip+np.array([1.4,0.,0.]))
            points.append(plume_tip+np.array([-1.4,0.,0.]))
        if attached:
            points.extend([payload_top,payload_top+np.array([1.8,0.,0.]),payload_top+np.array([-1.8,0.,0.])])
            center=.5*(base+payload_top)
        else:
            center=state['position']
        detail_points=[]
        for offset in (-7.,0.,7.):
            ring_center=top+up*offset
            for k in range(8):
                angle=k*np.pi/4
                detail_points.append(ring_center+np.array([np.cos(angle),np.sin(angle),0.])*2.4)
        return dict(state=state,base=base,top=top,plume_tip=plume_tip,plume=plume,
            payload_top=payload_top,payload_base=payload_base,attached=attached,
            up=up,center=center,points=points,detail_points=detail_points)

    def _need(self,eye,target,focal,points):
        """How far outside the gate the subject projects (1.0 = exactly full)."""
        eye=np.asarray(eye,dtype=float);target=np.asarray(target,dtype=float)
        forward=target-eye;forward/=max(float(np.linalg.norm(forward)),1e-9)
        right=np.cross(forward,np.array([0.,0.,1.]))
        if np.linalg.norm(right)<1e-4:right=np.array([1.,0.,0.])
        right/=np.linalg.norm(right)
        up=np.cross(right,forward)
        vertical=self.VERTICAL_APERTURE/(2.*focal);horizontal=self.HORIZONTAL_APERTURE/(2.*focal)
        need=0.
        for point in points:
            offset=np.asarray(point,dtype=float)-eye
            depth=max(float(np.dot(offset,forward)),.5)
            need=max(need,abs(float(np.dot(offset,right)))/depth/horizontal,
                          abs(float(np.dot(offset,up)))/depth/vertical)
        return need

    def _solve(self,place,target,focal,points,margin=.9,low=6.,high=6000.):
        """Find the distance along a placement curve that fills the gate.

        `place(span)` returns the camera position for a distance parameter;
        the projected fill falls monotonically as the distance grows, so a
        bisection always lands on the same framing instead of oscillating
        between too-tight and too-wide the way a multiplicative step does.
        """
        def fill(span):return self._need(place(span),target,focal,points)
        if fill(high)>margin:return place(high)
        if fill(low)<margin:return place(low)
        lo,hi=low,high
        for _ in range(28):
            mid=.5*(lo+hi)
            if fill(mid)>margin:lo=mid
            else:hi=mid
        return place(.5*(lo+hi))

    def frame(self,time):
        """Camera eye/target/focal-length at an arbitrary replay time.

        The shot supplies a sight direction and a focal length; the subject's
        own silhouette supplies the distance, so every frame puts the entire
        vehicle and its flame inside the gate with air around it. Ground
        cameras keep their feet on the surface and step back instead of
        floating upward like a drone.
        """
        selected=self.shots[-1]
        for shot in self.shots:
            if shot[0]<=time<shot[1]:selected=shot;break
        start,end,fn,focal,name=selected
        progress=smoothstep(0.,1.,(time-start)/(end-start))
        subject=self._subject(time)
        vector,kind=fn(progress,time)
        vector=np.asarray(vector,dtype=float)
        points=subject['points']
        target=subject['center']
        if kind=='detail':
            points=subject['detail_points']
            target=subject['top']
        if kind=='eye':
            anchor=np.array([self.pad[0] if name in ('landing_burn','touchdown') else self.launch[0],
                             self.pad[1] if name in ('landing_burn','touchdown') else self.launch[1],0.])
            azimuth=math.atan2(vector[1]-anchor[1],vector[0]-anchor[0])
            height=float(np.clip(vector[2],2.1,4.0))
            def place(span):
                return np.array([anchor[0]+math.cos(azimuth)*span,anchor[1]+math.sin(azimuth)*span,height])
            # A camera almost directly under the vehicle sees it end-on, where
            # projected size FALLS as the camera gets closer: start the bracket
            # outside that fold so the bisection stays monotone.
            low=max(14.,1.5*max(0.,float(target[2])-height))
            eye=self._solve(place,target,focal,points,low=low)
            return eye,target,focal

        direction=vector/max(float(np.linalg.norm(vector)),1e-9)
        floor_z=8. if kind!='detail' else 6.
        def place(span):
            eye=target+direction*span
            if eye[2]<floor_z:eye[2]=floor_z
            return eye
        eye=self._solve(place,target,focal,points,low=8. if kind=='detail' else 20.)
        return eye,target,focal

    HORIZONTAL_APERTURE=20.955
    VERTICAL_APERTURE=11.787

    def film_events(self):
        rows={}
        for name,value in self.events.items():
            rows[name]=None if value is None else round(float(self.timeline.film_time(value)),3)
        return rows

    def export(self):
        return dict(start_track=round(self.t_start,3),end_track=round(self.t_end,3),
            film_seconds=round(self.timeline.duration,3),timeline=self.timeline.export(),
            events=self.film_events(),event_track={k:None if v is None else round(float(v),3)
                for k,v in self.events.items()},
            shots=[dict(name=name,start=round(self.timeline.film_time(a),3),
                end=round(self.timeline.film_time(b),3),focal=focal) for a,b,_,focal,name in self.shots])


PRESETS={
    'balanced':dict(subframes=4,motion_blur=False),
    'cinematic':dict(subframes=10,motion_blur=False),
    'pathtraced':dict(subframes=24,motion_blur=False),
}


class OfflineRenderer:
    """Replay a FlightTrack into an MP4: one render per output frame."""

    def __init__(self,visuals,stage,preset='cinematic',fps=60.,size=(1920,1080),cq=19):
        self.visuals=visuals;self.stage=stage
        self.preset=PRESETS[preset];self.fps=float(fps);self.size=(int(size[0]),int(size[1]));self.cq=int(cq)

    def _apply_quality(self):
        import carb
        settings=carb.settings.get_settings()
        # RTX height fog fogs the sky dome itself: the horizon goes flat gray
        # and every surface loses its shadow contrast. The HDRI sky already
        # carries aerial perspective, so the fog pass stays off.
        settings.set('/rtx/fog/enabled',False)
        settings.set('/rtx/post/motionblur/enabled',bool(self.preset['motion_blur']))
        # Thresholded bloom: only the exhaust sits above ~2 HDR units, so the
        # flame gets a fire halo while the hull and sky stay crisp.
        settings.set('/rtx/post/bloom/enabled',True)
        settings.set('/rtx/post/bloom/quality',3)
        settings.set('/rtx/post/bloom/size',.28)
        settings.set('/rtx/post/bloom/intensity',.7)
        settings.set('/rtx/post/bloom/threshold',2.1)
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

    def render(self,track:FlightTrack,path,physics_constants,on_frame=None,limit_seconds=None,stills=None):
        """Render the full track; returns stats dict. physics_constants: (cfg,half,engine_lever).

        stills=(film_times, folder) renders only those moments as PNGs for a
        framing check, with no video encoder involved.
        """
        import omni.replicator.core as rep
        from pxr import Gf,Sdf,UsdGeom
        self._apply_quality()
        cfg,half,engine_lever=physics_constants
        director=CameraDirector(cfg,track,half)
        playback=PlaybackPhysics(cfg,track,half,engine_lever)
        visuals=self.visuals
        visuals.mode='free';visuals.follow=False;visuals.last_camera=-1.

        booster=self.stage.GetPrimAtPath('/World/Booster');payload=self.stage.GetPrimAtPath('/World/Payload')
        # A dedicated film camera, not the viewport: the viewport rewrites its
        # own camera focalLength every frame (probed: 10/20/50/100 mm all read
        # back 18.15 and framed identically), while a film-owned camera keeps
        # the lens and the look-at matrix we author. One transform matrix
        # avoids the op-order ambiguity of separate translate/rotate ops.
        camera=UsdGeom.Camera.Define(self.stage,'/World/FilmCamera')
        camera.CreateFocalLengthAttr(18.147)
        camera.CreateHorizontalApertureAttr(20.955)
        camera.CreateVerticalApertureAttr(11.787)
        camera.CreateClippingRangeAttr(Gf.Vec2f(.1,30000.))
        # The viewport auto-exposes; a film camera does not, so the same scene
        # clips to white. Negative exposure restores the sky and hull shading.
        camera.CreateExposureAttr(-1.4)
        camera_xform=UsdGeom.Xformable(camera).AddTransformOp()

        def aim(eye,target,focal):
            matrix=Gf.Matrix4d(1.).SetLookAt(Gf.Vec3d(*map(float,eye)),Gf.Vec3d(*map(float,target)),Gf.Vec3d(0,0,1)).GetInverse()
            camera_xform.Set(matrix)
            camera.GetFocalLengthAttr().Set(float(focal))

        product=rep.create.render_product('/World/FilmCamera',self.size)
        annotator=rep.AnnotatorRegistry.get_annotator('rgb');annotator.attach(product)

        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.unlink(missing_ok=True)
        process=subprocess.Popen(self._encoder_command(path),stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)

        def show(film_time):
            time_s=director.timeline.track_time(film_time)
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
            if os.environ.get('ROCKET_CINE_DEBUG'):
                subject=director._subject(time_s)
                need=director._need(eye,target,focal,subject['points'])
                print(f'CINE film={film_time:.2f} track={time_s:.2f} eye={eye.round(1)} '
                      f'target={target.round(1)} focal={focal:.1f} dist={np.linalg.norm(eye-target):.1f} '
                      f'fill={need:.3f}',flush=True)
            rep.orchestrator.step(rt_subframes=self.preset['subframes'],pause_timeline=True)
            data=np.asarray(annotator.get_data())
            if data.dtype!=np.uint8:data=np.clip(data,0,255).astype(np.uint8)
            return time_s,np.ascontiguousarray(data[...,:3])

        if stills:
            import cv2
            folder=Path(stills[1]);folder.mkdir(parents=True,exist_ok=True)
            files=[]
            for film_time in stills[0]:
                time_s,frame_rgb=show(float(film_time))
                name=folder/f'film-{float(film_time):05.1f}s.png'
                cv2.imwrite(str(name),frame_rgb[...,::-1])
                files.append(dict(film_time=float(film_time),track_time=round(time_s,2),file=str(name)))
                print(f'STILL film={float(film_time):.1f}s track={time_s:.1f}s -> {name}',flush=True)
            annotator.detach();product.destroy()
            return dict(stills=files,meta=director.export())

        duration=director.timeline.duration
        if limit_seconds is not None:duration=min(duration,float(limit_seconds))
        frames=int(math.ceil(duration*self.fps))
        started=time.monotonic();encoded=0
        try:
            for frame in range(frames):
                film_time=frame/self.fps
                time_s,frame_rgb=show(film_time)
                process.stdin.write(frame_rgb.tobytes());encoded+=1
                if on_frame and frame%on_frame==0:
                    elapsed=time.monotonic()-started
                    print(f'CINEMATIC: frame {frame+1}/{frames} t={time_s:.1f}s ({elapsed:.0f}s elapsed, ~{elapsed/max(frame+1,1)*1000:.0f} ms/frame)',flush=True)
        finally:
            process.stdin.close();stderr=process.stderr.read().decode(errors='replace');code=process.wait()
            annotator.detach();product.destroy()
        if code!=0:raise RuntimeError(f'ffmpeg failed ({code}): {stderr[:500]}')
        if encoded<int(frames*.9):raise RuntimeError(f'Only {encoded}/{frames} frames encoded')
        elapsed=time.monotonic()-started
        meta=director.export();meta.update(fps=self.fps,width=self.size[0],height=self.size[1],
            rendered_seconds=float(encoded/self.fps),partial=limit_seconds is not None)
        meta_path=path.with_name(path.stem+'-meta.json')
        meta_path.write_text(json.dumps(meta,indent=2))
        return dict(frames=encoded,fps=self.fps,width=self.size[0],height=self.size[1],
            seconds=float(encoded/self.fps),wall_seconds=elapsed,ms_per_frame=elapsed*1000./max(encoded,1),
            bytes=path.stat().st_size,preset=self.preset,video=str(path),meta=str(meta_path),
            events=meta['events'],shots=meta['shots'])
