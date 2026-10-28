from contextlib import asynccontextmanager
from pathlib import Path
import asyncio, json, os, sqlite3, time, uuid
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .store import Store, DomainError, ROOT, ROLES, SCREENS, J
from alge_gateway.swimtime_network import SwimTimeNetwork

def create_app(db_path=None,mode=None):
    mode=mode or os.getenv('FINS_MODE','TEST')
    store=Store(db_path or os.getenv('FINS_DB',str(ROOT/'runtime'/f'{mode.lower()}.sqlite3')),mode)
    swimtime=SwimTimeNetwork(ROOT,mode)
    def snapshot():
        result=store.snapshot()
        result['swimtime']=swimtime.snapshot()
        return result
    async def health_loop():
        while True:
            await asyncio.sleep(1)
    @asynccontextmanager
    async def lifespan(app):
        task=asyncio.create_task(health_loop())
        try:
            yield
        finally:
            swimtime.stop()
            task.cancel()
    app=FastAPI(title='FINS 2026 - Venue Results API',version='0.8.0',lifespan=lifespan)
    app.state.store=store
    app.state.swimtime=swimtime
    @app.exception_handler(DomainError)
    async def domain_error(_,e):return JSONResponse({'error':str(e)},status_code=e.status)
    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(_,e):return JSONResponse({'error':'Data conflict: duplicate identity, lane, or invalid relationship'},status_code=409)
    @app.middleware('http')
    async def boundary(req,call_next):
        if req.method in ('POST','PUT','PATCH','DELETE'):
            origin=req.headers.get('origin')
            # Same-origin controls; external integrations use authenticated non-browser HTTP.
            if origin and origin.rstrip('/')!=str(req.base_url).rstrip('/'):
                return JSONResponse({'error':'Cross-origin mutation denied'},status_code=403)
            try:n=int(req.headers.get('content-length','0'))
            except ValueError:n=3000000
            if n>2000000:return JSONResponse({'error':'Request too large'},status_code=413)
        try:r=await call_next(req)
        except (KeyError,TypeError,ValueError) as e:return JSONResponse({'error':'Invalid request: '+str(e)},status_code=422)
        r.headers['Cache-Control']='no-store'
        r.headers['X-Content-Type-Options']='nosniff'
        return r
    def actor(req):
        h=req.headers.get('authorization','')
        if not h.startswith('Bearer '):raise DomainError('Authentication required',401)
        return store.identity(h[7:])
    async def payload(req):
        p=await req.json()
        if not isinstance(p,dict):raise DomainError('Expected JSON object')
        return p
    def reason(p):
        s=p.get('reason','').strip()
        if not 3<=len(s)<=1000:raise DomainError('Reason must be 3..1000 characters')
        return s
    def templates():return json.loads((ROOT/'templates_sfs/registry.json').read_text())
    health_sample={'cpu':time.process_time(),'at':time.monotonic()}
    @app.get('/api/health')
    def health():
        import psutil
        warning=None;rss=None;now=time.monotonic();cpu=time.process_time()
        percent=round(100*(cpu-health_sample['cpu'])/max(now-health_sample['at'],.001),2)
        health_sample.update(cpu=cpu,at=now)
        try:
            process=psutil.Process()
            if Path(process.exe()).resolve()!=Path(os.sys.executable).resolve():raise OSError('PID namespace maps to a different executable')
            rss=round(process.memory_info().rss/1048576,1)
            if rss<8:raise OSError('Implausible RSS for this Python service in isolated process namespace')
        except (psutil.Error,OSError):warning='Process RSS unavailable in this isolated environment'
        if warning:rss=None
        return {'ok':True,'mode':mode,'version':'0.8.0','operator_mode':store.operator_mode,'production_approved':False,'hardware_verified':False,
                'rss_mb':rss,'cpu_percent':percent,'monitor_warning':warning,'server_time':time.time()}
    @app.post('/api/login')
    async def login(req:Request):
        p=await payload(req);return await asyncio.to_thread(store.login,p.get('user',''),p.get('password',''))
    @app.post('/api/logout')
    async def logout(req:Request):
        actor(req);store.logout(req.headers['authorization'][7:]);return {'logged_out':True}
    @app.get('/api/me')
    def me(req:Request):return actor(req)
    @app.get('/api/state')
    def state():return snapshot()
    @app.get('/api/swimtime')
    def swimtime_state():return swimtime.snapshot()
    @app.post('/api/swimtime/start')
    async def swimtime_start(req:Request):
        a=actor(req);store.require(a,'TIMING_OPERATOR');p=await payload(req)
        try:
            if any(k in p for k in ('api_base_url','bearer_token','lane_offset','auto_sync')):
                swimtime.update_sync_config(p)
            result=await swimtime.start(p.get('source_ip','10.227.186.112'),p.get('port',26))
        except (OSError,ValueError) as exc:raise DomainError('UDP listener: '+str(exc),409)
        with store.db() as c:store.audit(c,a['id'],'SWIMTIME_TEST_START','observer',None,{'source_ip':result['source_ip'],'port':result['port']},'SwimTime Network Display','Read-only TEST observer; no competition timing or results changed')
        return result
    @app.post('/api/swimtime/sync-config')
    async def swimtime_sync_config(req:Request):
        a=actor(req);store.require(a,'TIMING_OPERATOR');p=await payload(req)
        try:return swimtime.update_sync_config(p)
        except ValueError as exc:raise DomainError(str(exc),400)
    @app.post('/api/swimtime/sync-now')
    async def swimtime_sync_now(req:Request):
        a=actor(req);store.require(a,'TIMING_OPERATOR');p=await payload(req)
        if any(k in p for k in ('api_base_url','bearer_token','lane_offset','auto_sync')):
            try:swimtime.update_sync_config(p)
            except ValueError as exc:raise DomainError(str(exc),400)
        comp=bool(p.get('complete_heat'))
        st=await swimtime.sync_to_external_api(force=True,check_only=bool(p.get('check_only')),reason='manual_complete' if comp else 'manual_operator',complete_heat=comp)
        if st.get('state')=='ERROR':raise DomainError(st.get('last_error') or 'External API sync failed',409)
        return swimtime.snapshot()
    @app.post('/api/swimtime/stop')
    async def swimtime_stop(req:Request):
        a=actor(req);store.require(a,'TIMING_OPERATOR')
        swimtime.stop()
        await asyncio.sleep(0)
        with store.db() as c:store.audit(c,a['id'],'SWIMTIME_TEST_STOP','observer',None,None,'SwimTime Network Display','Operator stopped the TEST observer')
        return swimtime.snapshot()
    @app.post('/api/swimtime/replay')
    async def swimtime_replay(req:Request):
        a=actor(req);store.require(a,'TIMING_OPERATOR')
        try:result=swimtime.replay_capture()
        except (OSError,ValueError) as exc:raise DomainError(str(exc),409)
        with store.db() as c:store.audit(c,a['id'],'SWIMTIME_TEST_REPLAY','observer',None,{'datagrams':result['counts'].get('datagrams',0)},'Bundled 24 October field recording','Offline TEST replay; no results written or published')
        return result
    @app.get('/api/templates')
    def template_registry():return templates()
    @app.get('/api/public/results')
    def public_results():
        s=store.snapshot()
        return {'mode':mode,'revision':s['revision'],'heats':[h for h in s['heats'] if h['status']=='OFFICIAL' and h['published']],
                'approval':'LOCAL TEST SERVICE / FISU PROVIDER ACCEPTANCE PENDING','production_approved':False}
    @app.post('/api/import')
    async def import_meet(req:Request):return store.import_meet(actor(req),await payload(req))
    @app.post('/api/select')
    async def select(req:Request):
        a=actor(req);store.require(a,'RESULTS_OPERATOR','TIMING_OPERATOR','SYSTEM_ADMINISTRATOR');p=await payload(req)
        with store.db() as c:
            store.heat(c,p['heat_id'])
            old=c.execute("SELECT value FROM meta WHERE key='selected_heat'").fetchone()[0]
            c.execute("UPDATE meta SET value=? WHERE key='selected_heat'",(p['heat_id'],))
            store.audit(c,a['id'],'SELECT_HEAT',p['heat_id'],old,p['heat_id'],'control',reason(p))
        return {'selected':p['heat_id']}
    @app.post('/api/timing')
    async def ingest(req:Request):return store.ingest(actor(req),await payload(req))
    @app.post('/api/demo/replay')
    async def demo_replay(req:Request):
        a=actor(req);store.require(a,'TIMING_OPERATOR');p=await payload(req)
        if mode!='TEST':raise DomainError('Demo replay disabled in VENUE',403)
        with store.db(False) as c:
            h=store.heat(c,p['heat_id'])
            if h['status']!='READY':raise DomainError('Select an unused READY test heat')
            lanes=[r[0] for r in c.execute('SELECT lane FROM entries WHERE heat_id=? ORDER BY lane',(h['id'],))]
        frames=[b'START']+[f'R{h["timing_event"]:03}{h["timing_heat"]:03} 00:00:{i:02}.0000'.encode() for i in range(43)]
        frames+=[f'I{lane:02}00100:00:20.{lane:04}'.encode() for lane in lanes]
        frames+=[f'F{lane:02}00200:00:{42+lane:02}.1200'.encode() for lane in lanes]
        source='TEST-DASHBOARD-'+uuid.uuid4().hex
        for seq,raw in enumerate(frames,1):
            store.ingest(a,{'source':source,'profile':'tm-swim-video-modern-v1','heat_id':h['id'],'simulation':True,'frames':[{'sequence':seq,'hex':raw.hex()}]})
            await asyncio.sleep(.1)
        return {'replayed':len(frames),'test':True,'source':'SYNTHETIC MANUAL-RECONSTRUCTED FRAMES / NOT DEVICE LOG'}
    @app.post('/api/notice')
    async def notice(req:Request):
        a=actor(req);store.require(a,'LED_OPERATOR');p=await payload(req)
        if not 1<=len(p.get('text',''))<=300 or not p.get('approval_ref') or not p.get('source'):raise DomainError('Notice text, LOC approval reference and source required')
        with store.db() as c:
            old=c.execute("SELECT value FROM meta WHERE key='notice'").fetchone()
            c.execute("INSERT INTO meta VALUES('notice',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(J({'text':p['text'],'approval_ref':p['approval_ref'],'source':p['source'],'by':a['id'],'at':time.time()}),))
            store.audit(c,a['id'],'NOTICE','venue',old[0] if old else None,p,p['source'],reason(p))
        return {'ok':True}
    @app.post('/api/gateway/heartbeat')
    async def gateway(req:Request):
        a=actor(req);store.require(a,'TIMING_OPERATOR');p=await payload(req)
        if p['profile'] not in ('tm-swim-video-modern-v1','tm-swim-video-legacy-v1'):raise DomainError('Invalid profile')
        if mode=='VENUE' and p.get('state')=='SIMULATION':raise DomainError('Simulation disabled in VENUE')
        with store.db() as c:
            c.execute('INSERT INTO gateways VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat,source=excluded.source,profile=excluded.profile,hardware_connected=excluded.hardware_connected,state=excluded.state',
                      (a['id'],time.time(),str(p['source'])[:100],p['profile'],int(bool(p.get('hardware_connected'))),str(p.get('state','UNKNOWN'))[:100]))
        return {'ok':True,'hardware_verified':False}
    @app.post('/api/results/{heat_id}/compile')
    async def compile_results(heat_id:str,req:Request):
        p=await payload(req);return store.compile_results(actor(req),heat_id,p['revision'],reason(p))
    @app.post('/api/results/{heat_id}/workflow')
    async def workflow(heat_id:str,req:Request):
        p=await payload(req);return store.workflow(actor(req),heat_id,p['action'],p['revision'],reason(p),p.get('document_ref',''),p.get('authority_name',''))
    @app.post('/api/results/{heat_id}/correction')
    async def correction(heat_id:str,req:Request):return store.correction(actor(req),heat_id,await payload(req))
    @app.post('/api/results/{heat_id}/publication')
    async def publication(heat_id:str,req:Request):
        a=actor(req);store.require(a,'RESULTS_OPERATOR','CHIEF_RESULTS_OFFICER');p=await payload(req)
        with store.db() as c:
            h=store.heat(c,heat_id,p['revision'])
            if p['publish'] and h['status']!='OFFICIAL':raise DomainError('Only approved OFFICIAL results can be published')
            c.execute('UPDATE heats SET published=? WHERE id=?',(int(bool(p['publish'])),heat_id))
            store.audit(c,a['id'],'PUBLICATION',heat_id,h['published'],bool(p['publish']),'results officer',reason(p))
        return {'published':bool(p['publish'])}
    @app.post('/api/routes')
    async def routes(req:Request):
        a=actor(req);store.require(a,'LED_OPERATOR');p=await payload(req);targets=p['outputs']
        if not isinstance(targets,list) or not targets or len(targets)!=len(set(targets)) or any(t not in SCREENS for t in targets):raise DomainError('Invalid output selection')
        content=p['content'];valid={'idle','upcoming','startlist','live','splits','results','official','qualification','medals','notice'}
        if content not in valid:raise DomainError('Unsupported screen content')
        safe=p.get('safe',32)
        if not isinstance(safe,int) or not 0<=safe<=96:raise DomainError('Safe margin must be 0..96 native pixels')
        playlist=p.get('playlist',[])
        if len(playlist)>20 or any(x.get('content') not in valid or not 3<=x.get('seconds',0)<=3600 for x in playlist):raise DomainError('Invalid playlist')
        with store.db() as c:
            store.heat(c,p['heat_id'])
            for t in targets:
                old=dict(c.execute('SELECT * FROM routes WHERE output=?',(t,)).fetchone())
                if p.get('expected_revisions',{}).get(t,old['revision'])!=old['revision']:raise DomainError('Route revision conflict',409)
                c.execute('UPDATE routes SET content=?,heat_id=?,safe=?,playlist=?,playlist_epoch=?,revision=revision+1 WHERE output=?',(content,p['heat_id'],safe,J(playlist),time.time(),t))
                store.audit(c,a['id'],'ROUTE',t,old,p,'LED control',reason(p))
        return {'routed':targets}
    @app.post('/api/blackout')
    async def blackout(req:Request):
        a=actor(req);p=await payload(req)
        if p.get('output')=='tv':
            store.require(a,'BROADCAST_OPERATOR')
            with store.db() as c:
                old=dict(c.execute("SELECT * FROM graphics WHERE id='tv'").fetchone());c.execute("UPDATE graphics SET program=NULL,held=0 WHERE id='tv'")
                store.audit(c,a['id'],'TV_CLEAR','tv',old,None,'broadcast',reason(p))
        else:
            store.require(a,'LED_OPERATOR')
            targets=p.get('outputs',list(SCREENS))
            if any(t not in SCREENS for t in targets):raise DomainError('Invalid output')
            with store.db() as c:
                for t in targets:
                    old=dict(c.execute('SELECT * FROM routes WHERE output=?',(t,)).fetchone())
                    c.execute('UPDATE routes SET blackout=?,revision=revision+1 WHERE output=?',(int(bool(p.get('enabled',True))),t))
                    store.audit(c,a['id'],'LED_BLACKOUT',t,old,p,'LED control',reason(p))
        return {'ok':True}
    @app.post('/api/graphics')
    async def graphics(req:Request):
        a=actor(req);store.require(a,'BROADCAST_OPERATOR');p=await payload(req);action=p['action']
        with store.db() as c:
            old=dict(c.execute("SELECT * FROM graphics WHERE id='tv'").fetchone())
            if action=='preview':
                h=store.heat(c,p['heat_id']);registry=templates()
                t_code=str(p.get('template','') or '').strip().upper()
                aliases={'COUNTDOWN':'SFS550','SFS550A':'SFS550','SFS200':'SFS200A','SFS201':'SFS201A','SFS100':'SFS203A','SFS101':'SFS203B','SFS300':'SFS302A','SFS300A':'SFS300A','SFS302':'SFS302A','SFS001A':'SFS001','SFS002A':'SFS002','SFS203':'SFS203A','SFS301':'SFS301A','SFS901':'SFS901A','SFS902':'SFS902A'}
                t_code=aliases.get(t_code,t_code)
                if t_code not in registry:raise DomainError('Unknown official template code: '+str(t_code))
                if p.get('result_label')=='OFFICIAL' and h['status']!='OFFICIAL':raise DomainError('Cannot preview OFFICIAL on unapproved results')
                scene={'template':t_code,'heat_id':p['heat_id'],'lane':p.get('lane',1),'record':p.get('record'),'qualification':p.get('qualification'),'result_label':p.get('result_label'),'set_at':time.time()}
                c.execute("UPDATE graphics SET preview=? WHERE id='tv'",(J(scene),))
            elif action=='take':
                if not old['preview']:raise DomainError('Preview a template before TAKE')
                scene=json.loads(old['preview']);h=store.heat(c,scene['heat_id'])
                if scene.get('result_label')=='OFFICIAL' and h['status']!='OFFICIAL':raise DomainError('Official result approval was revoked')
                template=templates()[scene['template']]
                if mode=='VENUE' and template['approval_status']!='PRODUCTION APPROVED':raise DomainError('Template is not production approved: '+template['approval_status'],409)
                scene['set_at']=time.time()
                c.execute("UPDATE graphics SET program=?,held=0 WHERE id='tv'",(J(scene),))
            elif action=='hold':
                if not old['program']:raise DomainError('Nothing on program')
                scene=json.loads(old['program'])
                if scene['template'].startswith('SFS50'):raise DomainError('Live timing cannot be held as a live clock')
                s=store.snapshot();scene['frozen_heat']=next(h for h in s['heats'] if h['id']==scene['heat_id'])
                c.execute("UPDATE graphics SET program=?,held=1 WHERE id='tv'",(J(scene),))
            elif action=='clear':c.execute("UPDATE graphics SET program=NULL,held=0 WHERE id='tv'")
            else:raise DomainError('Unknown graphic action')
            store.audit(c,a['id'],'GRAPHICS_'+action.upper(),'tv',old,p,'broadcast operator',reason(p))
        return {'ok':True}
    @app.post('/api/output/heartbeat')
    async def output_heartbeat(req:Request):
        p=await payload(req)
        if p.get('output') not in {*SCREENS,'tv'}:raise DomainError('Invalid output')
        if not 0<p.get('width',0)<=8192 or not 0<p.get('height',0)<=8192:raise DomainError('Invalid dimensions')
        client=str(p.get('client_id',''))
        if not 1<=len(client)<=100:raise DomainError('Client identity required')
        with store.db() as c:
            c.execute('DELETE FROM output_clients WHERE heartbeat<?',(time.time()-3600,))
            c.execute('INSERT INTO output_clients VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat,width=excluded.width,height=excluded.height,revision=excluded.revision',
                      (client,p['output'],time.time(),p['width'],p['height'],p.get('revision',0)))
        return {'ok':True}
    @app.get('/api/link/ping')
    def link_ping():return {'server_time':time.time(),'transport':'HTTP','production_approved':False}
    @app.post('/api/integration/gen/inspect')
    async def gen_inspect(req:Request):
        a=actor(req);store.require(a,'TIMING_OPERATOR','RESULTS_OPERATOR')
        p=await payload(req)
        from alge_gateway.gen_inspector import inspect_text
        result=inspect_text(p.get('text',''),p.get('filename','upload.gen'))
        with store.db() as c:store.audit(c,a['id'],'GEN_INSPECT',result['filename'],None,{'sha256':result['sha256'],'rows':len(result['rows']),'adopted':False},'Uploaded ALGE GEN sample','Read-only inspection; field semantics unresolved; no result publication')
        return result
    @app.get('/api/audit')
    def audit(req:Request,limit:int=100):
        a=actor(req);store.require(a,'SYSTEM_ADMINISTRATOR','CHIEF_RESULTS_OFFICER','JURY_APPROVER')
        with store.db(False) as c:return [dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT ?',(min(max(limit,1),500),))]
    @app.post('/api/backup')
    async def backup(req:Request):
        a=actor(req);store.require(a,'SYSTEM_ADMINISTRATOR');p=await payload(req)
        target=ROOT/'backups'/f'{mode.lower()}-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:6]}.sqlite3'
        with store.db(False) as c:
            with sqlite3.connect(target) as dest:c.backup(dest)
        with store.db() as c:store.audit(c,a['id'],'BACKUP',target.name,None,{'filename':target.name},'SQLite online backup',reason(p))
        return {'backup':target.name}
    @app.websocket('/ws')
    async def websocket(ws:WebSocket):
        origin=ws.headers.get('origin');host=ws.headers.get('host')
        if origin and origin.split('://')[-1].rstrip('/')!=host:await ws.close(code=1008);return
        await ws.accept()
        try:
            while True:
                s=await asyncio.to_thread(snapshot)
                try:
                    await asyncio.wait_for(ws.send_json(s),timeout=6)
                except asyncio.TimeoutError:
                    pass
                st = s.get('swimtime') or {}
                fast = st.get('clock_fresh') or st.get('receiving')
                await asyncio.sleep(.1 if fast else .3)
        except (WebSocketDisconnect,RuntimeError):pass
        except Exception:pass
    app.mount('/assets',StaticFiles(directory=ROOT/'assets_processed'),name='assets')
    app.mount('/references',StaticFiles(directory=ROOT/'assets_original/references'),name='references')
    for name in ('control_dashboard','broadcast_tvg','led_displays','templates_sfs'):
        folder=ROOT/name/('dist' if name=='control_dashboard' else '')
        folder.mkdir(exist_ok=True)
        app.mount('/'+name,StaticFiles(directory=folder,html=True),name=name)
    @app.get('/')
    def home():return FileResponse(ROOT/'control_dashboard/dist/index.html')
    @app.get('/results')
    def web_results():return FileResponse(ROOT/'led_displays/results.html')
    return app

app=create_app()
