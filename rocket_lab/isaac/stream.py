"""Bounded loopback JSON socket server. Socket IO never blocks PhysX stepping."""
import json
import queue
import socket
import socketserver
import threading
import time

MAX_PACKET=65536


def exchange(message,port=8766,timeout=.3):
    with socket.create_connection(('127.0.0.1',port),timeout=timeout) as connection:
        connection.sendall(json.dumps(message,allow_nan=False).encode()+b'\n')
        with connection.makefile('rb') as source:
            payload=source.readline(MAX_PACKET+1)
    if len(payload)>MAX_PACKET:raise ValueError('Native response exceeded packet limit')
    return json.loads(payload)


class TelemetryServer:
    def __init__(self,port=8766):
        self.latest=None;self.updated_at=None;self.commands=queue.Queue(maxsize=16)
        self.lock=threading.Lock();self.sequence=0
        owner=self
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(.5)
                try:
                    raw=self.rfile.readline(MAX_PACKET+1)
                    if len(raw)>MAX_PACKET:raise ValueError('Packet too large')
                    message=json.loads(raw)
                    if not isinstance(message,dict):raise ValueError('Socket request must be an object')
                    if message.get('op')=='status':
                        with owner.lock:response=dict(ok=True,sequence=owner.sequence,updated_at=owner.updated_at,snapshot=owner.latest)
                    elif message.get('op')=='command':
                        command=validate_command(message.get('command'))
                        with owner.lock:snapshot=owner.latest
                        if command['type']=='detach' and snapshot and snapshot.get('payload_attached') is False:
                            raise ValueError('Payload is already released')
                        if snapshot and snapshot.get('control_mode') in ('training','qualification') and command['type']!='stop':
                            raise ValueError('Training and qualification runs accept stop commands only')
                        owner.commands.put_nowait(command)
                        response=dict(ok=True,queued=True)
                    else:raise ValueError('Unknown socket operation')
                except (ValueError,TypeError,queue.Full,socket.timeout) as error:response=dict(ok=False,error=str(error) or 'Command queue full')
                try:self.wfile.write(json.dumps(response,allow_nan=False).encode()+b'\n')
                except (OSError,ValueError):pass
        # One short request at a time bounds thread count and connection memory.
        class Server(socketserver.TCPServer):
            allow_reuse_address=True
        self.server=Server(('127.0.0.1',port),Handler)
        self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.1},daemon=True)

    def start(self):self.thread.start();return self

    def publish(self,snapshot):
        # Serialize once here to reject nonfinite values before sharing state.
        value=json.loads(json.dumps(snapshot,allow_nan=False))
        if len(json.dumps(value))>MAX_PACKET-1024:raise ValueError('Snapshot too large')
        with self.lock:self.latest=value;self.updated_at=time.time();self.sequence+=1

    def drain(self):
        while True:
            try:yield self.commands.get_nowait()
            except queue.Empty:return

    def close(self):
        if self.thread.is_alive():self.server.shutdown();self.thread.join(timeout=2)
        self.server.server_close()


def validate_command(command):
    if not isinstance(command,dict):raise ValueError('Command must be an object')
    kind=command.get('type')
    if kind=='retarget':
        import math
        target=command.get('landing')
        if not isinstance(target,list) or len(target)!=2 or any(type(value) not in (int,float) or not math.isfinite(value) or abs(value)>10000 for value in target):
            raise ValueError('Landing target requires two finite coordinates within +/-10000 m')
        return dict(type=kind,landing=target)
    if kind=='manual':
        import math
        action=command.get('action')
        if not isinstance(action,list) or len(action)!=3 or any(type(value) not in (float,int) or not math.isfinite(value) or abs(value)>1 for value in action):
            raise ValueError('Manual action requires throttle and two gimbal controls within [-1,1]')
        roll=command.get('roll',0.)
        if type(roll) not in (float,int) or not math.isfinite(roll) or abs(roll)>1:raise ValueError('Manual roll requires a finite command within [-1,1]')
        return dict(type=kind,action=action,roll=roll)
    if kind=='camera':
        mode=command.get('mode')
        if mode not in ('free','follow','vehicle','launch','landing'):raise ValueError('Unknown native camera mode')
        return dict(type=kind,mode=mode)
    if kind not in ('detach','cutoff','stop','guidance','pause','resume','step'):raise ValueError('Unknown native command')
    return dict(type=kind)
