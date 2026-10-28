"""Bounded backend soak test. No claim about venue hardware or GPU capacity."""
import asyncio,json,math,os,statistics,subprocess,sys,time
from pathlib import Path
import httpx,websockets
from results_backend.store import ROOT

async def main():
    duration=int(os.getenv('FINS_STRESS_SECONDS','60'));base='http://127.0.0.1:8767';db=ROOT/'testing/tmp/stress.sqlite3'
    subprocess.run([sys.executable,'-m','testing.prepare_browser',str(db)],cwd=ROOT,check=True,capture_output=True)
    proc=subprocess.Popen([sys.executable,'-m','uvicorn','results_backend.app:app','--host','127.0.0.1','--port','8767','--log-level','warning'],cwd=ROOT,env={**os.environ,'FINS_DB':str(db)},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    report={'kind':'backend_loopback_soak','requested_seconds':duration,'clients':8,'physical_device':False,'gpu_measured':False,'windows_tested':False,'errors':[]}
    sent={};latency=[];http_latency=[];received=[0]*8;health=[];stop=asyncio.Event()
    async with httpx.AsyncClient(base_url=base,trust_env=False,timeout=5) as client:
      try:
        for _ in range(100):
          try:
            if (await client.get('/api/health')).status_code==200:break
          except httpx.ConnectError:pass
          await asyncio.sleep(.05)
        else:raise RuntimeError('Server not ready')
        token=(await client.post('/api/login',json={'user':'TEST_TIMING_OPERATOR','password':'Browser_TEST_password_123'})).json()['token']
        headers={'Authorization':'Bearer '+token}
        async def listener(i):
          async with websockets.connect('ws://127.0.0.1:8767/ws',proxy=None,max_size=2**22) as ws:
            seen=set()
            while not stop.is_set():
              try:s=json.loads(await asyncio.wait_for(ws.recv(),1))
              except asyncio.TimeoutError:continue
              received[i]+=1;h=s['heats'][0];ticks=h.get('clock_ticks')
              if ticks in sent and ticks not in seen:latency.append((time.perf_counter()-sent[ticks])*1000);seen.add(ticks)
        tasks=[asyncio.create_task(listener(i)) for i in range(8)]
        seq=1
        async def send(raw):
          nonlocal seq
          t=time.perf_counter();r=await client.post('/api/timing',headers=headers,json={'heat_id':'TEST-IND-1','profile':'tm-swim-video-modern-v1','source':'TEST-STRESS','simulation':True,'frames':[{'sequence':seq,'hex':raw.encode().hex()}]});http_latency.append((time.perf_counter()-t)*1000);seq+=1
          if r.status_code!=200:raise RuntimeError(r.text)
        await send('START');began=time.perf_counter()
        for n in range(duration*10):
          ticks=n*1000;sent[ticks]=time.perf_counter();whole=n//10;fraction=n%10
          await send(f'R001001 00:{whole//60:02}:{whole%60:02}.{fraction}000')
          if n%10==0:health.append((await client.get('/api/health')).json())
          await asyncio.sleep(max(0,began+(n+1)/10-time.perf_counter()))
        await asyncio.sleep(.3);stop.set();await asyncio.gather(*tasks)
        def stats(xs):
          xs=sorted(xs)
          return {'n':len(xs),'median_ms':round(statistics.median(xs),2),'p95_ms':round(xs[math.ceil(len(xs)*.95)-1],2),'max_ms':round(max(xs),2)} if xs else None
        rss=[h['rss_mb'] for h in health if h['rss_mb'] is not None]
        report.update(status='COMPLETED',elapsed_seconds=round(time.perf_counter()-began,2),messages=seq-1,websocket_snapshots_by_client=received,http_roundtrip=stats(http_latency),ingest_to_websocket=stats(latency),rss_mb_min=min(rss) if rss else None,rss_mb_max=max(rss) if rss else None,memory_measurement='VALID' if rss else 'UNAVAILABLE - process namespace prevents psutil measurement',cpu_percent_max=max(h['cpu_percent'] for h in health),notes=['Backend receipt-to-WebSocket measurement on loopback, not device-to-LED end-to-end latency.','60-second bounded soak is not a full competition-day endurance test.','CPU is backend process CPU; no Surface CPU/RAM/GPU or LED refresh measurement.'])
      except Exception as e:report.update(status='FAILED');report['errors'].append(str(e));stop.set()
      finally:
        proc.terminate()
        try:proc.wait(5)
        except subprocess.TimeoutExpired:proc.kill()
        err=proc.stderr.read().decode()
        if err:report['server_log']=err
        (ROOT/'testing/reports/stress.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
        if report.get('status')!='COMPLETED':raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
