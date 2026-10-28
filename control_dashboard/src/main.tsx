import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import SwimTimePanel,{type SwimTimeFeed,type EventGroup} from './SwimTimePanel';

type Entry={lane:number;name:string;country:string;university:string;ticks:number|null;seed_ticks:number|null;rank:number|null;irm:string|null;qualification:string|null;record:string|null;medal:string|null;timings:{kind:string;ticks:number;touch:number}[];members?:{name:string;gender:string;university:string}[]};
type Heat={id:string;name:string;gender:string;round:string;timing_heat:number;status:string;revision:number;clock_ticks:number|null;data_stale:boolean;timing_age_ms:number|null;published:number;entries:Entry[];approvals:{stage:string;user_id:string;revision:number}[]};
type Route={output:string;name:string;width:number;height:number;content:string;heat_id:string;safe:number;blackout:number;revision:number};
type Scene={template:string;heat_id:string};
type State={swimtime?:SwimTimeFeed;operator_mode:string;mode:string;revision:number;server_time:number;selected_heat:string;heats:Heat[];routes:Record<string,Route>;graphics:{preview:Scene|null;program:Scene|null;held:number};gateways:{state:string;connected:boolean;source:string}[];outputs:{output:string;online:boolean;width:number;height:number}[]};
type Template={code:string;name:string;approval_status:string;missing:string[];guide_page:number;fields:string[];reference:string;assets:{guide_name:string;original:string|null;resolution:string}[]};
type User={token:string;user:string;role:string};
const roles=['TIMING_OPERATOR','RESULTS_OPERATOR','CHIEF_RESULTS_OFFICER','JURY_APPROVER','BROADCAST_OPERATOR','LED_OPERATOR','SYSTEM_ADMINISTRATOR'];
const time=(t:number|null|undefined)=>{if(t==null)return '—';let n=Math.floor(t/100);return `${Math.floor(n/6000)}:${String(Math.floor(n/100)%60).padStart(2,'0')}.${String(n%100).padStart(2,'0')}`};
function Status({label,value,ok}:{label:string;value:React.ReactNode;ok?:boolean}){return <div className={'status '+(ok?'good':'')}><small>{label}</small><strong>{value}</strong></div>}
function App(){
 const [state,setState]=useState<State|null>(null),[online,setOnline]=useState(false),[registry,setRegistry]=useState<Record<string,Template>>({});
 const [user,setUser]=useState<User|null>(()=>{try{return JSON.parse(sessionStorage.getItem('fins-session')||'null')}catch{return null}});
 const [tab,setTab]=useState('Control'),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [login,setLogin]=useState({user:'operator',password:'hOJAj2-zGeWcvubZXCF80-Xg'}),[reason,setReason]=useState(''),[doc,setDoc]=useState(''),[template,setTemplate]=useState('SFS206');
 const [targets,setTargets]=useState<string[]>(['master']),[content,setContent]=useState('startlist'),[margin,setMargin]=useState(24),[playlist,setPlaylist]=useState(false);
 const [lane,setLane]=useState(1),[correction,setCorrection]=useState('{"lane":1,"rank":1}'),[audit,setAudit]=useState<unknown[]>([]),[importText,setImportText]=useState('');
 const [opsText,setOpsText]=useState(''),[authority,setAuthority]=useState('');
 useEffect(()=>{let ws:WebSocket|undefined,retry:number,watch:number,last=0,stopped=false;
  const connect=()=>{ws=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws');ws.onmessage=e=>{last=performance.now();setState(JSON.parse(e.data));setOnline(true)};ws.onerror=()=>ws?.close();ws.onclose=()=>{setOnline(false);if(!stopped)retry=window.setTimeout(connect,1000)}};
  connect();watch=window.setInterval(()=>{if(last&&performance.now()-last>8000)setOnline(false)},1000);
  fetch('/api/templates').then(r=>r.json()).then(setRegistry).catch(()=>setError('Template registry unavailable'));
  return()=>{stopped=true;clearTimeout(retry);clearInterval(watch);ws?.close()};
 },[]);
  const feed=state?.swimtime,feedActive=!!feed&&(feed.listening||feed.replay);
  const can=(...r:string[])=>!!user&&(r.includes(user.role)||(state?.operator_mode==='SINGLE'&&user.role==='SINGLE_OPERATOR'))&&online;
  async function api(path:string,body?:unknown){
   const res=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',...(user?{Authorization:'Bearer '+user.token}:{})},body:body?JSON.stringify(body):undefined});
   let result=await res.json();
   if(!res.ok){
    if(res.status===401){
     setUser(null);
     sessionStorage.removeItem('fins-session');
    }
    throw Error(result.error||result.detail||'Request failed');
   }
   return result;
  }
  async function action(fn:()=>Promise<unknown>,success='Action completed'){setBusy(true);setError('');setNotice('');try{await fn();setNotice(success)}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
  async function doLogin(e:React.FormEvent){e.preventDefault();await action(async()=>{const u=await api('/api/login',login);setUser(u);sessionStorage.setItem('fins-session',JSON.stringify(u));},'Authenticated')}

  const doSignOut = () => {
   if (user?.token) {
    api('/api/logout', {}).catch(() => {});
   }
   setUser(null);
   sessionStorage.removeItem('fins-session');
   setError('');
   setNotice('Signed out');
  };

  const events: EventGroup[] = React.useMemo(() => {
   if (!state?.heats) return [];
   const map = new Map<string, EventGroup>();
   for (const h of state.heats) {
    const eid = (h as any).event_id || ('EV-' + ((h as any).timing_event || 1));
    if (!map.has(eid)) {
     map.set(eid, {
      event_id: eid,
      timing_event: (h as any).timing_event || 1,
      name: h.name,
      gender: h.gender,
      discipline: (h as any).discipline || '',
      heats: []
     });
    }
    map.get(eid)!.heats.push(h);
   }
   return Array.from(map.values()).sort((a,b)=>a.timing_event - b.timing_event);
  }, [state?.heats]);

  const [selectedEventId, setSelectedEventId] = useState<string>('');
  const [localHeatId, setLocalHeatId] = useState<string>('');

  const activeEvent = events.find(ev => ev.event_id === selectedEventId) || events[0];
  const activeEventHeats = activeEvent?.heats || [];

  const heat = (localHeatId ? state?.heats.find(h => h.id === localHeatId) : null)
   || state?.heats.find(h => h.id === state?.selected_heat)
   || activeEventHeats[0]
   || state?.heats?.[0];

  useEffect(() => {
   if (heat?.id) {
    const foundEv = events.find(ev => ev.heats.some(h => h.id === heat.id));
    if (foundEv) setSelectedEventId(foundEv.event_id);
   } else if (events.length && !selectedEventId) {
    setSelectedEventId(events[0].event_id);
   }
  }, [heat?.id, events]);

  const handleEventSelect = (eventId: string) => {
   setSelectedEventId(eventId);
   const ev = events.find(e => e.event_id === eventId);
   if (ev && ev.heats.length > 0) {
    setLocalHeatId(ev.heats[0].id);
    if (can('TIMING_OPERATOR','RESULTS_OPERATOR','SYSTEM_ADMINISTRATOR')) {
     action(() => api('/api/select', { heat_id: ev.heats[0].id, reason: 'Operator selected event ' + ev.name }));
    }
   }
  };

  const handleHeatSelect = (heatId: string) => {
   setLocalHeatId(heatId);
   if (can('TIMING_OPERATOR','RESULTS_OPERATOR','SYSTEM_ADMINISTRATOR')) {
    action(() => api('/api/select', { heat_id: heatId, reason: 'Operator selected heat' }));
   }
  };

  const wf=(a:string)=>action(()=>api('/api/results/'+heat!.id+'/workflow',{action:a,revision:heat!.revision,reason,document_ref:doc,authority_name:authority}));
  const resultPath='/api/results/'+heat?.id;

  const handleGraphicAction = async (act: 'preview'|'take'|'hold'|'clear'|'direct', tmpl?: string, targetLane?: number, recordBadge?: string) => {
   if (act === 'clear') {
    await action(() => api('/api/graphics', { action: 'clear', reason: 'Cleared from SwimTime panel' }), 'Graphics cleared (Off-Air)');
   } else if (act === 'take') {
    await action(() => api('/api/graphics', { action: 'take', reason: 'TAKE from SwimTime panel' }), 'Pushed live to OBS (ON-AIR)');
   } else if (act === 'hold') {
    await action(() => api('/api/graphics', { action: 'hold', reason: 'Hold from SwimTime panel' }), 'Graphic held');
   } else if (act === 'preview') {
    await action(() => api('/api/graphics', { action: 'preview', template: tmpl, heat_id: heat?.id, lane: targetLane || 1, record: recordBadge, reason: 'Preview loaded' }), `Loaded preview (${tmpl})`);
   } else if (act === 'direct') {
    await action(async () => {
     await api('/api/graphics', { action: 'preview', template: tmpl, heat_id: heat?.id, lane: targetLane || 1, record: recordBadge, reason: 'Direct stream trigger' });
     await api('/api/graphics', { action: 'take', reason: 'Direct stream trigger TAKE' });
    }, `Live on OBS: ${tmpl} (Lane ${targetLane || 1})`);
   }
  };

  return <div className="app"><aside><div className="brand">FINS<span>2026</span></div><p className="subbrand">VENUE CONTROL ROOM</p><nav>{['Control','SwimTime TEST','Results','LED routing','Connections','Template library','Audit & recovery'].map(t=><button key={t} className={tab===t?'active':''} onClick={()=>setTab(t)}>{t}</button>)}</nav><div className="sidebottom"><span className={'dot '+(online?'on':'')}/>{online?'LAN connected':'Connection lost'}<p>{user?.user||'Read-only session'}</p><small>{user?.role.replaceAll('_',' ')||'Log in to operate'}</small><p>v0.8.0 / SwimTime TEST reception</p><a target="_blank" href="/results">Published results ↗</a></div></aside>
  <main><header><div><p className="eyebrow">2026 FISU WORLD UNIVERSITY CHAMPIONSHIP FINSWIMMING</p><h1>{tab}</h1></div><div className="headerRight"><span className="mode">{state?.mode||'CONNECTING'} / NOT PRODUCTION APPROVED</span><span>Revision {state?.revision??'—'}</span></div></header>
  {!online&&<div className="alert">DATA CONNECTION LOST — live clocks are suppressed. Reconnecting to the LAN service.</div>}
  {error&&<div role="alert" className="alert">{error}</div>}{notice&&<div role="status" className="feedback">{notice}</div>}
  <div className="statusgrid"><Status label={feedActive?'SwimTime transport':'ALGE transport'} value={!online?'CONNECTION LOST':feedActive?(feed?.replay?'TEST REPLAY':feed?.receiving?'UDP RECEIVING / TEST':'UDP / NO FRESH FEED'):state?.gateways.some(g=>g.connected)?'PORT OPEN':'DISCONNECTED'} ok={online&&(feedActive?feed?.receiving:state?.gateways.some(g=>g.connected))}/><Status label={feedActive?'SwimTime freshness':'Timing freshness'} value={!online?'CONNECTION LOST':feedActive?(feed?.replay?'OFFLINE REPLAY':feed?.age_ms==null?'NO FEED':feed.age_ms+' ms'):heat?.timing_age_ms!=null?heat.timing_age_ms+' ms':'NO FEED'} ok={online&&(feedActive?feed?.receiving:!!heat&&!heat.data_stale&&heat.timing_age_ms!=null)}/><Status label="Results" value={heat?.status||'NO HEAT'} ok={heat?.status==='OFFICIAL'}/><Status label="LED outputs online" value={`${Object.keys(state?.routes||{}).filter(k=>state?.outputs.some(o=>o.output===k&&o.online)).length} / 6`}/><Status label="TVG program" value={state?.graphics.program?.template||'CLEAR'}/></div>
  {!user?<form className="login panel" onSubmit={doLogin}><div><h2>Operator authentication</h2><p>Use the account issued during setup. Every action records your identity.</p></div><input aria-label="User" placeholder="User ID" value={login.user} onChange={e=>setLogin({...login,user:e.target.value})}/><input aria-label="Password" type="password" placeholder="Password" value={login.password} onChange={e=>setLogin({...login,password:e.target.value})}/><button disabled={busy} type="submit">Sign in</button></form>:<div className="operator"><span>{user.user} / {user.role.replaceAll('_',' ')}</span><button className="quiet" onClick={doSignOut}>Sign out</button></div>}
  <div className="commandbar">
   <label>Select Event Name
    <select
     aria-label="Event Name"
     value={activeEvent?.event_id || ''}
     onChange={e => handleEventSelect(e.target.value)}
     disabled={!can('TIMING_OPERATOR','RESULTS_OPERATOR','SYSTEM_ADMINISTRATOR') || busy || !events.length}
    >
     <option value="">Select Event...</option>
     {events.map(ev => (
      <option key={ev.event_id} value={ev.event_id}>
       Event {ev.timing_event}: {ev.name}
      </option>
     ))}
    </select>
   </label>
   <label>Select Heat Name
    <select
     aria-label="Heat Name"
     value={state?.selected_heat || ''}
     onChange={e => handleHeatSelect(e.target.value)}
     disabled={!can('TIMING_OPERATOR','RESULTS_OPERATOR','SYSTEM_ADMINISTRATOR') || busy || !activeEventHeats.length}
    >
     <option value="">Select Heat...</option>
     {activeEventHeats.map(h => (
      <option key={h.id} value={h.id}>
       Heat {h.timing_heat} of {activeEventHeats.length} ({h.round}) — {h.entries?.length || 0} swimmers
      </option>
     ))}
    </select>
   </label>
   <label>Change reason
    <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Required for recorded operations"/>
   </label>
   {state?.operator_mode === 'SINGLE' && (
    <label>External approving authority
     <input aria-label="External authority" value={authority} onChange={e => setAuthority(e.target.value)} placeholder="Name of Chief or Jury authority"/>
    </label>
   )}
   <label>Jury / LOC document reference
    <input value={doc} onChange={e => setDoc(e.target.value)} placeholder="Required for approval or adjudication"/>
   </label>
  </div>
  {tab==='SwimTime TEST'&&<SwimTimePanel
   feed={feed}
   online={online}
   busy={busy}
   allowed={can('TIMING_OPERATOR')}
   heat={heat}
   events={events}
   activeEventId={activeEvent?.event_id}
   onSelectEvent={handleEventSelect}
   onSelectHeat={handleHeatSelect}
   time={time}
   registry={registry}
   state={state}
   canBroadcast={can('BROADCAST_OPERATOR')}
   onGraphicAction={handleGraphicAction}
   start={(source_ip,port,cfg)=>action(()=>api('/api/swimtime/start',{source_ip,port,...cfg}),'UDP TEST listener started and API sync settings saved.')}
   stop={()=>action(()=>api('/api/swimtime/stop',{}),'UDP TEST listener stopped.')}
   replay={()=>action(()=>api('/api/swimtime/replay',{}),'Recorded TEST capture replayed. No results changed.')}
   saveSync={cfg=>action(()=>api('/api/swimtime/sync-config',cfg),'FASU API sync settings saved to network_settings.json.')}
   syncNow={(cfg,check_only,complete_heat)=>action(()=>api('/api/swimtime/sync-now',{...cfg,check_only,complete_heat}),complete_heat?'Marked heat COMPLETED on FASU API.':check_only?'Verified ONGOING heat match with API.':'Synced lane results to FASU API.')}
  />}
 {tab==='Control'&&<><div className="twocol"><section className="panel"><div className="paneltitle"><h2>Broadcast preview</h2><span className="tag">PREVIEW</span></div><iframe title="Broadcast preview" className="video checker" src="/broadcast_tvg/?preview=1"/><div className="fields"><select aria-label="Template" value={template} onChange={e=>setTemplate(e.target.value)}>{Object.values(registry).map(t=><option key={t.code} value={t.code}>{t.code} / {t.name}</option>)}</select><input aria-label="Lane" type="number" min="0" max="12" value={lane} onChange={e=>setLane(Number(e.target.value))}/></div><div className="buttons"><button disabled={busy||!heat||!can('BROADCAST_OPERATOR')} onClick={()=>action(()=>api('/api/graphics',{action:'preview',template,heat_id:heat?.id,lane,reason}))}>Load preview</button><button className="take" disabled={busy||!can('BROADCAST_OPERATOR')} onClick={()=>action(()=>api('/api/graphics',{action:'take',reason}))}>TAKE</button><button disabled={busy||!can('BROADCAST_OPERATOR')} onClick={()=>action(()=>api('/api/graphics',{action:'hold',reason}))}>Hold</button></div><p className="muted">{registry[template]?.approval_status}. Hold is disabled for live timing templates.</p></section><section className="panel"><div className="paneltitle"><h2>Broadcast program</h2><span className="tag red">PROGRAM</span></div><iframe title="Broadcast program" className="video checker" src="/broadcast_tvg/"/><div className="clock">{online&&!heat?.data_stale?time(heat?.clock_ticks):'—'}</div><div className="buttons"><button className="danger" disabled={busy||!can('BROADCAST_OPERATOR')} onClick={()=>action(()=>api('/api/graphics',{action:'clear',reason}))}>CLEAR GRAPHICS</button><a target="_blank" href="/broadcast_tvg/?program=1">Open 1920 × 1080 output ↗</a></div><p className="muted">OBS Browser Source / alpha output. Program URL: {location.origin}/broadcast_tvg/?program=1 — 1920 × 1080. Physical OBS and network test pending.</p></section></div><section className="panel"><h2>Timing input / simulation</h2><p>Serial integration runs on the timing computer. Device validation is pending.</p><button disabled={busy||!can('TIMING_OPERATOR')||state?.mode!=='TEST'||heat?.status!=='READY'} onClick={()=>action(()=>api('/api/demo/replay',{heat_id:heat?.id}),'TEST replay completed. Results remain unofficial.')}>Run TEST race (synthetic ALGE frames)</button><p className="muted">Profile: TM-SWIM modern ASCII / test messages reconstructed from manual pages 32–33. No actual device capture.</p></section></>}
 {tab==='Results'&&<section className="panel"><div className="paneltitle"><h2>{heat?.gender} {heat?.name} / Heat {heat?.timing_heat}</h2><span className="tag">{heat?.status}</span></div><div className="buttons"><button disabled={busy||!heat||!can('RESULTS_OPERATOR')} onClick={()=>action(()=>api(resultPath+'/compile',{revision:heat?.revision,reason}))}>Compile unofficial</button><button disabled={busy||!heat||!can('RESULTS_OPERATOR','CHIEF_RESULTS_OFFICER')} onClick={()=>wf('review')}>Submit for review</button><button disabled={busy||!heat||!can('CHIEF_RESULTS_OFFICER')} onClick={()=>wf('endorse')}>{state?.operator_mode==='SINGLE'?'Record external Chief endorsement':'Chief endorsement'}</button><button disabled={busy||!heat||!can('JURY_APPROVER')} onClick={()=>wf('approve')}>{state?.operator_mode==='SINGLE'?'Record external Jury approval':'Jury official approval'}</button><button disabled={busy||!heat||!can('RESULTS_OPERATOR','CHIEF_RESULTS_OFFICER')} onClick={()=>action(()=>api(resultPath+'/publication',{revision:heat?.revision,publish:!heat?.published,reason}))}>{heat?.published?'Unpublish':'Publish official'}</button></div><div className="tablewrap"><table><thead><tr>{['Lane','Athlete / team & university','Country','Seed','Latest split','Finish','Rank','Decision'].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{heat?.entries.map(a=><tr key={a.lane}><td>{a.lane}</td><td><b>{a.name}</b><small>{a.university}</small>{a.members?.map((m,i)=><small key={i}>{i+1}. {m.name} / {m.gender}</small>)}</td><td>{a.country}</td><td>{time(a.seed_ticks)}</td><td>{time([...a.timings].reverse().find(t=>t.kind==='SPLIT')?.ticks)}</td><td>{time(a.ticks??[...a.timings].reverse().find(t=>t.kind==='FINISH')?.ticks)}</td><td>{a.rank??'—'}</td><td>{[a.irm,a.qualification,a.record,a.medal].filter(Boolean).join(' / ')||'—'}</td></tr>)}</tbody></table></div><p className="muted">Approved by: {heat?.approvals.map(a=>`${a.stage}: ${a.user_id} (revision ${a.revision})`).join(' / ')||'No signatures'}. Timing source is immutable raw data; graphics has no timing-edit endpoint.</p><details><summary>Jury decisions & documented corrections</summary><div className="buttons"><button disabled={busy||!can('JURY_APPROVER')} onClick={()=>wf('reopen')}>Reopen official result</button><button disabled={busy||!can('JURY_APPROVER')} onClick={()=>wf('swimoff')}>Require swim-off</button><button disabled={busy||!can('JURY_APPROVER')} onClick={()=>wf('resume_review')}>Resume review after decision</button></div><p>Only documented Jury adjudication may change a competition result. Raw electronic timing is retained. Fields: lane, ticks (1/10000s), rank, qualification, record, medal, irm.</p><textarea aria-label="Correction JSON" value={correction} onChange={e=>setCorrection(e.target.value)}/><button disabled={busy||!can('JURY_APPROVER')} onClick={()=>action(()=>api(resultPath+'/correction',{...JSON.parse(correction),revision:heat?.revision,reason,document_ref:doc,source:doc}))}>Record approved correction</button></details></section>}
 {tab==='LED routing'&&<><section className="panel"><h2>Independent screen routing</h2><div className="screenchoices">{Object.entries(state?.routes||{}).map(([k,r])=><label key={k}><input type="checkbox" checked={targets.includes(k)} onChange={e=>setTargets(e.target.checked?[...targets,k]:targets.filter(x=>x!==k))}/>{r.name}<small>{r.width} × {r.height}</small></label>)}</div><div className="fields"><label>Content<select value={content} onChange={e=>setContent(e.target.value)}>{['idle','upcoming','startlist','live','splits','results','official','qualification','medals','notice'].map(c=><option key={c}>{c}</option>)}</select></label><label>Safe margin (native px)<input type="number" min="0" max="96" value={margin} onChange={e=>setMargin(Number(e.target.value))}/></label><label><input type="checkbox" checked={playlist} onChange={e=>setPlaylist(e.target.checked)}/>Playlist: selected content / identity (10s each)</label></div><div className="buttons"><button disabled={busy||!heat||!can('LED_OPERATOR')} onClick={()=>action(()=>api('/api/routes',{outputs:targets,content,heat_id:heat?.id,safe:margin,expected_revisions:Object.fromEntries(targets.map(k=>[k,state?.routes[k].revision])),playlist:playlist?[{content,seconds:10},{content:'idle',seconds:10}]:[],reason}))}>Route to selected screens</button><button className="danger" disabled={busy||!can('LED_OPERATOR')} onClick={()=>action(()=>api('/api/blackout',{outputs:targets,enabled:true,reason}))}>BLACKOUT SELECTED</button><button disabled={busy||!can('LED_OPERATOR')} onClick={()=>action(()=>api('/api/blackout',{outputs:targets,enabled:false,reason}))}>Release blackout</button></div><p className="muted">6 native canvases / 7,569,408 pixels total. LED design awaits venue and FISU approval; physical cabinet mapping and viewing-distance tests are pending.</p></section><div className="screenpreviews">{Object.entries(state?.routes||{}).map(([k,r])=><section className="panel" key={k}><div className="paneltitle"><h2>{r.name}</h2><a target="_blank" href={'/led_displays/?screen='+k}>Open ↗</a></div><div style={{aspectRatio:`${r.width}/${r.height}`}}><iframe title={r.name} src={'/led_displays/?screen='+k}/></div><small>{r.width} × {r.height} / {r.content} / {r.blackout?'BLACKOUT':state?.outputs.some(o=>o.output===k&&o.online)?'CLIENT ONLINE':'NO CLIENT'}</small></section>)}</div><section className="panel"><h2>Operational notice</h2><textarea value={opsText} onChange={e=>setOpsText(e.target.value)} aria-label="Operational notice"/><button disabled={busy||!can('LED_OPERATOR')} onClick={()=>action(()=>api('/api/notice',{text:opsText,approval_ref:doc,source:doc,reason}))}>Save approved notice</button></section></>}
 {tab==='Connections'&&<section className="panel"><h2>OBS / LAN setup and link diagnostics</h2><iframe title="Connection setup" style={{width:'100%',height:900,border:0}} src="/broadcast_tvg/setup.html"/><h2>ALGE GEN read-only inspection</h2><p>Uploaded samples contain no athlete names. Field semantics are not verified; inspection never changes timing or publishes a result.</p><input aria-label="GEN sample" type="file" accept=".gen" onChange={e=>{const f=e.target.files?.[0];if(f)action(async()=>{if(f.size>200000)throw Error('Sample exceeds 200 KB');const r=await api('/api/integration/gen/inspect',{filename:f.name,text:await f.text()});setImportText(JSON.stringify(r,null,2))},'GEN inspected; no results adopted')}} disabled={!can('TIMING_OPERATOR','RESULTS_OPERATOR')}/><pre>{importText}</pre></section>}
 {tab==='Template library'&&<section className="panel"><h2>35 official TVG template codes</h2><p>Reference: UWC2026_TVG_SFS_V1_0 / 14 October 2026. No template is marked Fully Matched or Production Approved.</p><table><thead><tr><th>Code / template</th><th>Guide page</th><th>Missing original assets</th><th>Review</th></tr></thead><tbody>{Object.values(registry).map(t=><tr key={t.code}><td><b>{t.code}</b><small>{t.name}</small></td><td>{t.guide_page}</td><td>{t.missing.join(', ')||'None by mapped name; QA pending'}</td><td><a target="_blank" href={'/templates_sfs/comparator.html?template='+t.code}>Compare reference ↗</a></td></tr>)}</tbody></table></section>}
 {tab==='Audit & recovery'&&<><section className="panel"><h2>Audit and online backup</h2><div className="buttons"><button disabled={busy||!can('SYSTEM_ADMINISTRATOR','CHIEF_RESULTS_OFFICER','JURY_APPROVER')} onClick={()=>action(async()=>setAudit(await api('/api/audit')))}>Read latest audit</button><button disabled={busy||!can('SYSTEM_ADMINISTRATOR')} onClick={()=>action(async()=>{const r=await api('/api/backup',{reason});setNotice('Backup created: '+r.backup)},'Backup request completed')}>Create consistent backup</button></div><pre>{JSON.stringify(audit,null,2)}</pre><p>Restore runs locally with the service stopped. Restored outputs are blacked out and sessions are revoked.</p></section><section className="panel"><h2>Import validated meet / roster JSON</h2><p>TEST and VENUE databases are isolated. A TEST import requires explicitly labelled IDs. Individual and M-W-M-W relay entries are validated.</p><textarea aria-label="Meet JSON" value={importText} onChange={e=>setImportText(e.target.value)} placeholder="Paste meet JSON (see testing/fixtures/meet.json schema)"/><button disabled={busy||!can('SYSTEM_ADMINISTRATOR','RESULTS_OPERATOR')} onClick={()=>action(()=>api('/api/import',JSON.parse(importText)))}>Validate and import</button></section><section className="panel"><h2>{state?.operator_mode==='SINGLE'?'Single operator / all control actions':'Role boundaries'}</h2>{(state?.operator_mode==='SINGLE'?['SINGLE_OPERATOR']:roles).map(r=><p key={r} className="muted">{r.replaceAll('_',' ')}</p>)}</section></>}
 <footer>Local LAN operation / 28–29 October competition programme / Hardware, FISU template sign-off and public results provider acceptance pending.</footer>
 </main></div>
}
createRoot(document.getElementById('root')!).render(<App/>);
