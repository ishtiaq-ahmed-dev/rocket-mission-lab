"""Dashboard bridge to the native simulator's bounded loopback socket."""
import asyncio
import time
from fastapi import APIRouter,HTTPException,WebSocket,WebSocketDisconnect
from .stream import exchange,validate_command
from .launcher import NativeStart,runtime_status,start,mark_stopping,cancel_start

router=APIRouter(prefix='/native')


def status():
    try:
        value=exchange(dict(op='status'))
        return dict(connected=bool(value.get('snapshot')),runtime=runtime_status(),**value)
    except (OSError,ValueError):return dict(connected=False,ok=False,snapshot=None,runtime=runtime_status())


@router.get('/status')
def native_status():return status()


@router.post('/start')
def native_start(request:NativeStart):
    try:return start(request)
    except FileNotFoundError as error:raise HTTPException(503,str(error)) from error
    except ValueError as error:raise HTTPException(409,str(error)) from error


@router.post('/cancel-start')
def native_cancel_start():
    try:return cancel_start()
    except ValueError as error:raise HTTPException(409,str(error)) from error


@router.post('/command')
def native_command(command:dict):
    try:
        validated=validate_command(command)
        result=exchange(dict(op='command',command=validated))
    except ValueError as error:raise HTTPException(422,str(error)) from error
    except OSError as error:raise HTTPException(503,'Native Isaac Sim runner is not connected') from error
    if not result.get('ok'):raise HTTPException(409,result.get('error','Native command rejected'))
    if validated['type']=='stop':mark_stopping()
    return result


from pathlib import Path
from fastapi.responses import FileResponse
from ..config import ROOT

PREVIEW_MAP = {
    'launch': ROOT / 'data/isaac/diagnostic-launch.png',
    'ascent': ROOT / 'data/isaac/diagnostic.png',
    'engine': ROOT / 'data/isaac/diagnostic-engine.png',
    'landing': ROOT / 'data/isaac/diagnostic-landing.png',
}

@router.get('/previews')
def list_previews():
    items = []
    descriptions = {
        'launch': {
            'title': 'Takeoff Pad 01 & Launch Umbilical Tower',
            'desc': '10-level steel lattice gantry with structural X-trusses, swing arm, hold-down clamps, and upright pad markings.',
            'badge': 'TAKEOFF PAD 01'
        },
        'ascent': {
            'title': 'Supersonic Ascent & Mach Shock Diamonds',
            'desc': 'PhysX supersonic thrust plume with 4 shock diamond discs, titanium lattice grid fins, and carbon interstage.',
            'badge': 'SUPERSONIC PLUME'
        },
        'engine': {
            'title': 'Octaweb 9-Engine Cluster & Nozzle Bells',
            'desc': 'Center gimbaled bell with 8 outer auxiliary nozzles, Inconel alloy bells, and chrome landing leg pistons.',
            'badge': 'OCTAWEB CLUSTER'
        },
        'landing': {
            'title': 'Landing Pad 01 Downrange Target (>1km)',
            'desc': 'Recovery site at [1050, 250] with reflective green perimeter ring, concentric guide circles, and touchdown cross.',
            'badge': 'LANDING PAD 01'
        }
    }
    for key, path in PREVIEW_MAP.items():
        if path.is_file():
            meta = descriptions.get(key, {'title': key, 'desc': '', 'badge': 'RTX'})
            items.append({
                'id': key,
                'title': meta['title'],
                'description': meta['desc'],
                'badge': meta['badge'],
                'url': f'/api/native/preview/{key}',
                'size': path.stat().st_size,
                'modified': path.stat().st_mtime
            })
    video_path = ROOT / 'videos/rocket_mission_takeoff_detach_landing.mp4'
    has_video = video_path.is_file()
    duration = None
    if has_video:
        try:
            import cv2
            probe = cv2.VideoCapture(str(video_path))
            duration = probe.get(cv2.CAP_PROP_FRAME_COUNT) / max(probe.get(cv2.CAP_PROP_FPS), 1.)
            probe.release()
        except Exception:
            duration = None
    return {
        'images': items,
        'video': {
            'available': has_video,
            'url': '/api/native/video',
            'title': 'Full Isaac Sim Mission: Liftoff -> Staging (600m) -> Landing',
            'description': 'Continuous high-definition render of full mission flight with real-time PhysX physics and precision touchdown on Landing Pad 01 (>1 km separation).',
            'duration': round(duration, 2) if duration else None
        } if has_video else None
    }


@router.get('/preview/{name}')
def get_preview(name: str):
    path = PREVIEW_MAP.get(name)
    if not path or not path.is_file():
        raise HTTPException(404, f'Preview image "{name}" not found')
    return FileResponse(path, media_type='image/png')


@router.get('/video')
def get_video():
    video_path = ROOT / 'videos/rocket_mission_takeoff_detach_landing.mp4'
    if not video_path.is_file():
        raise HTTPException(404, 'Video recording not found')
    return FileResponse(video_path, media_type='video/mp4')


@router.websocket('/stream')
async def native_stream(websocket:WebSocket):
    # Read-only, same-origin local visualization. Commands use validated POST.
    origin=websocket.headers.get('origin')
    if origin and origin not in ('http://127.0.0.1:5180','http://localhost:5180'):
        await websocket.close(code=1008);return
    await websocket.accept()
    previous=None;last_send=0.
    try:
        while True:
            value=await asyncio.to_thread(status)
            marker=(value.get('connected'),value.get('sequence'))
            if marker!=previous or time.monotonic()-last_send>=1.:
                await websocket.send_json(value);previous=marker;last_send=time.monotonic()
            await asyncio.sleep(.2)
    except (WebSocketDisconnect,RuntimeError,OSError):return

