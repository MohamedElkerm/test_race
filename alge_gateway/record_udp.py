"""Capture a confirmed UDP destination port as raw evidence, without decoding.

Usage: python -m alge_gateway.record_udp --port CONFIRMED_PORT --seconds 60
Port must be discovered at the venue, not guessed from a screenshot.
"""
import argparse,base64,json,socket,time
from pathlib import Path

def record(port,seconds,output,bind='0.0.0.0'):
    if not 1<=port<=65535 or not 1<=seconds<=600:raise ValueError('Port 1..65535 and duration 1..600 required')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    count=0
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(.5);sock.bind((bind,port));start=time.monotonic()
        # Exclusive new output preserves earlier evidence and never writes to SwimTime.
        with output.open('x',encoding='utf-8') as f:
            f.write(json.dumps({'type':'metadata','port':port,'bind':bind,'started_at_unix':time.time(),'decoded':False,'hardware_verified':False})+'\n')
            while time.monotonic()-start<seconds:
                try:data,sender=sock.recvfrom(65535)
                except socket.timeout:continue
                f.write(json.dumps({'type':'datagram','received_at_unix':time.time(),'sender_ip':sender[0],'sender_port':sender[1],'length':len(data),'hex':data.hex(),'base64':base64.b64encode(data).decode()})+'\n');f.flush();count+=1
            f.write(json.dumps({'type':'summary','datagrams':count,'elapsed_seconds':round(time.monotonic()-start,3)})+'\n')
    return count

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True,type=int);p.add_argument('--seconds',type=int,default=60);p.add_argument('--bind',default='0.0.0.0');p.add_argument('--output',default='runtime/captures/udp-'+str(time.time_ns())+'.jsonl');a=p.parse_args()
    print(json.dumps({'datagrams':record(a.port,a.seconds,a.output,a.bind),'output':a.output,'decoded':False}))
