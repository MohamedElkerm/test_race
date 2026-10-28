"""Serial receive gateway with durable delivery spool. Never writes to ALGE."""
import argparse,getpass,json,logging,os,sqlite3,time,urllib.request,urllib.error
from pathlib import Path
from .protocol import FrameBuffer,PROFILES

class Gateway:
    def __init__(self,args):
        self.args=args;self.root=Path(args.spool);self.root.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root);self.db.execute('CREATE TABLE IF NOT EXISTS queue(sequence INTEGER PRIMARY KEY AUTOINCREMENT,frame_hex TEXT,delivered INTEGER DEFAULT 0)');self.db.commit()
        self.token='';self.last_heartbeat=0
    def request(self,path,data,login=False):
        headers={'Content-Type':'application/json'}
        if not login:headers['Authorization']='Bearer '+self.token
        req=urllib.request.Request(self.args.url.rstrip('/')+path,json.dumps(data).encode(),headers)
        with urllib.request.urlopen(req,timeout=3) as r:return json.load(r)
    def login(self):
        self.token=self.request('/api/login',{'user':self.args.user,'password':self.args.password},True)['token']
    def queue(self,frame):
        self.db.execute('INSERT INTO queue(frame_hex) VALUES(?)',(frame.hex(),));self.db.commit()
        # Raw retention is the spool itself; accepted/rejected disposition is retained by backend.
    def drain(self):
        rows=self.db.execute('SELECT sequence,frame_hex FROM queue WHERE delivered=0 ORDER BY sequence LIMIT 100').fetchall()
        if not rows:return
        r=self.request('/api/timing',{'source':self.args.source,'profile':self.args.profile,'heat_id':self.args.heat,
              'simulation':bool(self.args.replay),'frames':[{'sequence':s,'hex':h} for s,h in rows]})
        for row in r['outcomes']:
            self.db.execute('UPDATE queue SET delivered=1 WHERE sequence=?',(row['sequence'],))
            if row['disposition'] not in ('ACCEPTED','DUPLICATE','SEMANTIC_DUPLICATE','IDENTITY_CONFIRMED'):logging.warning('Quarantined sequence %s: %s',row['sequence'],row['disposition'])
        self.db.commit()
    def heartbeat(self,connected,state):
        if time.monotonic()-self.last_heartbeat<1:return
        self.request('/api/gateway/heartbeat',{'source':self.args.source,'profile':self.args.profile,'hardware_connected':connected,'state':state})
        self.last_heartbeat=time.monotonic()
    def run(self):
        self.login();buffer=FrameBuffer()
        if self.args.replay:
            for raw in Path(self.args.replay).read_bytes().splitlines():
                if not raw or raw.startswith(b'#'):continue
                # Fixture is hex, so CR and exact spacing survive text editors.
                for frame in buffer.feed(bytes.fromhex(raw.decode())):self.queue(frame)
                self.drain();self.heartbeat(False,'SIMULATION');time.sleep(self.args.replay_delay)
            self.drain();return
        import serial
        delay=1
        while True:
            try:
                with serial.Serial(self.args.port,baudrate=self.args.baud,bytesize=8,parity='N',stopbits=1,timeout=.1,xonxoff=False,rtscts=False,dsrdtr=False) as port:
                    # No port.write() exists. Wiring must be receive-only according to vendor.
                    delay=1
                    while True:
                        for frame in buffer.feed(port.read(256)):self.queue(frame)
                        self.heartbeat(True,'SERIAL_OPEN / FIRMWARE TEST PENDING');self.drain()
            except KeyboardInterrupt:break
            except (serial.SerialException,OSError,urllib.error.URLError,urllib.error.HTTPError) as e:
                logging.warning('Connection interrupted (%s); queued frames retained',type(e).__name__)
                try:self.heartbeat(False,'RECONNECTING')
                except Exception:pass
                time.sleep(delay);delay=min(30,delay*2)
                try:self.login()
                except Exception:pass
                buffer=FrameBuffer()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://127.0.0.1:8765');p.add_argument('--user',required=True)
    p.add_argument('--password-env');p.add_argument('--source',required=True,help='Stable unique source ID; keep same spool across reconnects')
    p.add_argument('--heat',required=True,help='Explicit roster/timing heat binding; change only between races')
    p.add_argument('--profile',choices=PROFILES,required=True);p.add_argument('--port',default='COM3')
    p.add_argument('--baud',type=int,choices=[4800,9600,19200,38400],default=19200)
    p.add_argument('--spool',default='runtime/gateway-spool.sqlite3');p.add_argument('--replay');p.add_argument('--replay-delay',type=float,default=.1)
    p.add_argument('--confirm-profile',action='store_true',help='Confirm selected profile against hardware firmware; does not mark hardware verified')
    a=p.parse_args()
    if not a.replay and not a.confirm_profile:p.error('Select firmware profile with vendor and pass --confirm-profile before opening a serial connection')
    a.password=os.environ[a.password_env] if a.password_env else getpass.getpass('Timing operator password: ')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    Gateway(a).run()
if __name__=='__main__':main()
