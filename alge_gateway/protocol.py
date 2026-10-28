"""Read-only TM-SWIM VIDEO ASCII parser. Manual pp32-33; device test pending.

Profiles deliberately reject the other firmware layout instead of guessing.
The legacy RR column disappears above version 14xx (manual wording).
START support begins with version 14xx. Identify the actual firmware at venue.
No outbound commands to timing hardware are implemented.
"""
from dataclasses import dataclass, asdict
from decimal import Decimal
import re

PROFILES = {
    'tm-swim-video-modern-v1': {'rank_width': 0, 'baud': 19200, 'source_pages': [32, 33], 'hardware_verified': False},
    'tm-swim-video-legacy-v1': {'rank_width': 2, 'baud': 19200, 'source_pages': [32, 33], 'hardware_verified': False},
}

@dataclass
class TimingEvent:
    kind: str
    event: int | None = None
    heat: int | None = None
    lane: int | None = None
    ticks: int | None = None  # integer 1/10000 seconds, never float official timing
    touch: int | None = None
    rank: int | None = None
    detail: dict | None = None

def ticks_from_clock(value):
    if not re.fullmatch(r'\d{2}:\d{2}:\d{2}\.\d{1,4}', value):
        raise ValueError('Invalid HH:MM:SS.ffff clock')
    h, m, sec = value.split(':')
    if int(m)>59 or Decimal(sec)>=60: raise ValueError('Clock range')
    return int((int(h)*3600+int(m)*60+Decimal(sec))*10000)

def parse_frame(frame: bytes, profile='tm-swim-video-modern-v1') -> TimingEvent:
    if profile not in PROFILES: raise ValueError('Unknown versioned profile')
    if len(frame)>64: raise ValueError('Frame exceeds documented 64 character maximum')
    s=frame.decode('ascii', errors='strict').rstrip('\r\n')
    if s=='START': return TimingEvent('START')
    m=re.fullmatch(r'R(\d{3})(\d{3}) (\d{2}:\d{2}:\d{2}\.\d{1,4})',s)
    if m:return TimingEvent('RUNNING',event=int(m[1]),heat=int(m[2]),ticks=ticks_from_clock(m[3]))
    # SwimTime reaction row has two blank columns where older I/F/C rows carry RR.
    m=re.fullmatch(r'M(\d{2})(\d{3})  (\d{2}:\d{2}:\d{2}\.\d{1,4})',s)
    if m:
        if int(m[1])>12 or not 1<=int(m[2])<=999:raise ValueError('Reaction lane/touch range')
        return TimingEvent('REACTION',lane=int(m[1]),touch=int(m[2]),ticks=ticks_from_clock(m[3]))
    w=PROFILES[profile]['rank_width']
    m=re.fullmatch(r'([IFC])(\d{2})(\d{3})'+(r'(\d{2})' if w else '')+r'(\d{2}:\d{2}:\d{2}\.\d{1,4})',s)
    if m:
        lane=int(m[2]);touch=int(m[3])
        if not 0<=lane<=12 or not 1<=touch<=999:raise ValueError('Lane/touch range')
        return TimingEvent({'I':'SPLIT','F':'FINISH','C':'DELETE','M':'REACTION'}[m[1]],lane=lane,touch=touch,
                           rank=int(m[4]) if w else None,ticks=ticks_from_clock(m[5 if w else 4]))
    m=re.fullmatch(r'ID(\d{1,3})/(\d{1,3})/([^/]+)/([^/]+)',s)
    if m:return TimingEvent('IDENTITY',event=int(m[1]),heat=int(m[2]),detail={'discipline':m[3],'class':m[4]})
    m=re.fullmatch(r'(\d{1,2}):([^/]+)/([^/]+)/(.+)',s)
    if m and int(m[1])<=12:
        return TimingEvent('SWIMMER_ID',lane=int(m[1]),detail={'name':m[2],'nation':m[3],'club':m[4]})
    raise ValueError('Unrecognised frame for selected profile')

class FrameBuffer:
    """CR framing, fragmented reads, optional LF, bounded resynchronisation."""
    def __init__(self):self.buffer=bytearray();self.discarding=False;self.rejected=0
    def feed(self,data:bytes):
        out=[]
        for b in data:
            if b==10 and not self.buffer:continue
            if b==13:
                if not self.discarding and self.buffer:out.append(bytes(self.buffer))
                self.buffer.clear();self.discarding=False
            elif not self.discarding:
                self.buffer.append(b)
                if len(self.buffer)>64:self.buffer.clear();self.discarding=True;self.rejected+=1
        return out
