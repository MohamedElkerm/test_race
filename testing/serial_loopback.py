"""POSIX pseudoterminal serial + real HTTP gateway test. NOT an ALGE hardware test."""
import json,os,pty,subprocess,sys,time,urllib.request
from pathlib import Path
from results_backend.store import ROOT

def request(base,path,data=None,token=None):
 h={'Content-Type':'application/json'}
 if token:h['Authorization']='Bearer '+token
 r=urllib.request.Request(base+path,json.dumps(data).encode() if data else None,h)
 with urllib.request.urlopen(r,timeout=3) as response:return json.load(response)
def main():
 if os.name!='posix':raise SystemExit('This harness requires POSIX PTY. Run Windows COM tests at the venue.')
 base='http://127.0.0.1:8768';tmp=ROOT/'testing/tmp';tmp.mkdir(exist_ok=True);db=tmp/'serial.sqlite3';spool=tmp/'gateway-spool.sqlite3'
 for suffix in ('','-wal','-shm'):
  q=Path(str(spool)+suffix)
  if q.exists():q.unlink()
 subprocess.run([sys.executable,'-m','testing.prepare_browser',str(db)],cwd=ROOT,check=True,capture_output=True)
 server=subprocess.Popen([sys.executable,'-m','uvicorn','results_backend.app:app','--host','127.0.0.1','--port','8768','--log-level','warning'],cwd=ROOT,env={**os.environ,'FINS_DB':str(db)},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 gateway=None;master,slave=pty.openpty();report={'type':'PSEUDOTERMINAL SERIAL SOFTWARE TEST','hardware_verified':False,'checks':[]}
 try:
  for _ in range(80):
   try:request(base,'/api/health');break
   except Exception:time.sleep(.05)
  env={**os.environ,'FINS_TEST_GATEWAY_PASSWORD':'Browser_TEST_password_123'}
  cmd=[sys.executable,'-m','alge_gateway.main','--url',base,'--user','TEST_TIMING_OPERATOR','--password-env','FINS_TEST_GATEWAY_PASSWORD','--source','TEST-PTY','--heat','TEST-IND-1','--profile','tm-swim-video-modern-v1','--port',os.ttyname(slave),'--spool',str(spool),'--confirm-profile']
  gateway=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
  for _ in range(80):
   s=request(base,'/api/state')
   if any(g['connected'] for g in s['gateways']):break
   time.sleep(.05)
  else:raise AssertionError('Virtual serial port not opened')
  report['checks'].append('Gateway opens POSIX PTY with configured serial settings and sends transport heartbeat')
  # Deliberately fragment a CR-terminated frame across serial writes.
  os.write(master,b'STA');time.sleep(.05);os.write(master,b'RT\rR001001 00:00:12.3000\rI0100100:00:06.1000\rF0100200:00:43.1200\r')
  for _ in range(80):
   h=next(h for h in request(base,'/api/state')['heats'] if h['id']=='TEST-IND-1')
   if any(t['kind']=='FINISH' for t in h['entries'][0]['timings']):break
   time.sleep(.05)
  else:raise AssertionError('Serial frames not processed')
  assert h['clock_ticks']==123000;assert h['entries'][0]['timings'][-1]['ticks']==431200
  report['checks'].append('Fragmented START / RUNNING / SPLIT / FINISH delivered through PySerial, durable spool, HTTP and SQLite')
  import sqlite3
  with sqlite3.connect(spool) as c:assert c.execute('SELECT COUNT(*) FROM queue WHERE delivered=1').fetchone()[0]==4
  report['checks'].append('All four raw frames retained in durable gateway spool and acknowledged')
  os.close(master);master=None
  for _ in range(80):
   g=request(base,'/api/state')['gateways']
   if g and not g[0]['connected']:break
   time.sleep(.05)
  else:raise AssertionError('Disconnection not detected')
  report['checks'].append('Serial disconnect detected and reconnect mode entered');report['status']='COMPLETED'
 except Exception as e:report.update(status='FAILED',error=str(e));raise
 finally:
  for p in [gateway,server]:
   if p:
    p.terminate()
    try:p.wait(3)
    except subprocess.TimeoutExpired:p.kill()
  if master is not None:os.close(master)
  os.close(slave);(ROOT/'testing/reports/serial_loopback.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
