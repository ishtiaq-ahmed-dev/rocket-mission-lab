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
