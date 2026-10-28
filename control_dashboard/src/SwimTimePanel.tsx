import {useEffect,useState} from 'react';

export type Entry={lane:number;name:string;country:string;university:string;ticks:number|null;seed_ticks:number|null;rank:number|null;irm:string|null;qualification:string|null;record:string|null;medal:string|null;timings:{kind:string;ticks:number;touch:number}[];members?:{name:string;gender:string;university:string}[]};
export type Heat={id:string;event_id?:string;name:string;gender:string;round:string;timing_heat:number;status:string;revision:number;clock_ticks:number|null;data_stale:boolean;timing_age_ms:number|null;published:number;entries:Entry[];approvals:{stage:string;user_id:string;revision:number}[]};
export type EventGroup={event_id:string;timing_event:number;name:string;gender:string;discipline:string;heats:Heat[]};
export type Template={code:string;name:string;approval_status:string;missing:string[];guide_page:number;fields:string[];reference:string;assets:{guide_name:string;original:string|null;resolution:string}[]};

export type SwimTimeSyncConfig={api_base_url:string;bearer_token:string;lane_offset:number;auto_sync:boolean};
export type SwimTimeSyncStatus={state:string;last_sync_at:number|null;matched_heat_id:string|null;matched_heat_label:string|null;swimtime_heat_number:string|null;last_sent_lanes:number;last_message:string|null;last_error:string|null};
export type SwimTimeFeed={enabled:boolean;state:string;listening:boolean;receiving:boolean;replay:boolean;source_ip:string;port:number;age_ms:number|null;clock_display:string|null;clock_raw:number|null;clock_code:number|null;clock_fresh:boolean;counts:Record<string,number>;metadata?:Record<string,string>;capture_file:string|null;error:string|null;warning:string|null;layout:string;channels:{channel:number;raw_value:number;display_time:string|null;source_rank:string;source_lap:string;source_points:string;meaning:string}[];sync_config?:SwimTimeSyncConfig;sync_status?:SwimTimeSyncStatus};

type Props={
 feed?:SwimTimeFeed;
 online:boolean;
 allowed:boolean;
 busy:boolean;
 heat?:Heat;
 events?:EventGroup[];
 activeEventId?:string;
 onSelectEvent?:(eventId:string)=>void;
 onSelectHeat?:(heatId:string)=>void;
 time?:(t:number|null|undefined)=>string;
 registry?:Record<string,Template>;
 state?:any;
 canBroadcast?:boolean;
 onGraphicAction?:(act:'preview'|'take'|'hold'|'clear'|'direct', tmpl?:string, targetLane?:number, recordBadge?:string)=>Promise<void>|void;
 start:(source:string,port:number,cfg:SwimTimeSyncConfig)=>void;
 stop:()=>void;
 replay:()=>void;
 saveSync?:(cfg:SwimTimeSyncConfig)=>void;
 syncNow?:(cfg:SwimTimeSyncConfig,checkOnly:boolean,completeHeat?:boolean)=>void;
};

export default function SwimTimePanel({
 feed,
 online,
 allowed,
 busy,
 heat,
 events=[],
 activeEventId,
 onSelectEvent,
 onSelectHeat,
 time=(t=>t!=null?String(t):'—'),
 registry={},
 state,
 canBroadcast=true,
 onGraphicAction,
 start,
 stop,
 replay,
 saveSync,
 syncNow
}:Props){
 const [source,setSource]=useState('192.168.43.112'),[port,setPort]=useState(26);
 const [apiUrl,setApiUrl]=useState('https://fasugames2026.eusf.org.eg/v2/api');
 const [token,setToken]=useState('');
 const [laneOffset,setLaneOffset]=useState(0);
 const [autoSync,setAutoSync]=useState(true);
 const [initialized,setInitialized]=useState(false);

 // Broadcast graphics state
 const isRelay = !!(heat && ((heat as any).relay || heat.name.toLowerCase().includes('relay')));
 const [selectedTemplate, setSelectedTemplate] = useState(isRelay ? 'SFS201A' : 'SFS200A');
 const [selectedLane, setSelectedLane] = useState(1);
 const [copied, setCopied] = useState(false);
 const [recordBadge, setRecordBadge] = useState('00:00:00');

 useEffect(()=>{
  if(isRelay){
   if(selectedTemplate==='SFS200A'||selectedTemplate==='SFS200')setSelectedTemplate('SFS201A');
   if(selectedTemplate==='SFS203A'||selectedTemplate==='SFS100')setSelectedTemplate('SFS203B');
   if(selectedTemplate==='SFS302A'||selectedTemplate==='SFS300')setSelectedTemplate('SFS302B');
  }else{
   if(selectedTemplate==='SFS201A'||selectedTemplate==='SFS200')setSelectedTemplate('SFS200A');
   if(selectedTemplate==='SFS203B'||selectedTemplate==='SFS101')setSelectedTemplate('SFS203A');
   if(selectedTemplate==='SFS302B'||selectedTemplate==='SFS300')setSelectedTemplate('SFS302A');
  }
 },[isRelay]);

 useEffect(()=>{
  if(!initialized&&feed){
   if(feed.source_ip)setSource(feed.source_ip);
   if(feed.port)setPort(feed.port);
   if(feed.sync_config){
    setApiUrl(feed.sync_config.api_base_url||'https://fasugames2026.eusf.org.eg/v2/api');
    setToken(feed.sync_config.bearer_token||'');
    setLaneOffset(feed.sync_config.lane_offset??0);
    setAutoSync(feed.sync_config.auto_sync??true);
   }
   setInitialized(true);
  }
 },[feed,initialized]);

 const enabled=allowed&&feed?.enabled&&!busy&&online;
 const clock=online&&feed?.clock_fresh?feed.clock_display:null;
 const cfg:SwimTimeSyncConfig={api_base_url:apiUrl,bearer_token:token,lane_offset:laneOffset,auto_sync:autoSync};
 const st=feed?.sync_status;
 const heatNum=feed?.metadata?.['Heat.HeatNumber']||st?.swimtime_heat_number||'—';

 const currentEvent = events.find(ev => ev.event_id === activeEventId) || events[0];
 const eventHeats = currentEvent?.heats || [];

 // Build unified lanes 1..8 (or channels present in feed)
 const channelMap = new Map((feed?.channels || []).map(ch => [ch.channel, ch]));
 const lanesList = [1, 2, 3, 4, 5, 6, 7, 8];
 for (const ch of feed?.channels || []) {
  if (!lanesList.includes(ch.channel)) lanesList.push(ch.channel);
 }
 lanesList.sort((a,b)=>a-b);

 const obsHost = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
 const obsCleanUrl = `http://${obsHost}:8765/broadcast_tvg/?program=1&clean=1`;
 const obsStandardUrl = `http://${obsHost}:8765/broadcast_tvg/?program=1`;

 const copyUrl = (url: string) => {
  navigator.clipboard.writeText(url).then(()=>{
   setCopied(true);
   setTimeout(()=>setCopied(false), 2200);
  });
 };

 const programScene = state?.graphics?.program;
 const previewScene = state?.graphics?.preview;

 return <>
  {/* Active Meet Event & Heat Selector */}
  <section className="panel" style={{borderLeft:'4px solid #58c6f5'}}>
   <div className="paneltitle">
    <h2>Active Meet Event & Heat (Competition Program)</h2>
    <span className="tag" style={{background:'#0c3559',color:'#84d3ff'}}>
     {heat ? `${heat.gender} ${heat.name} • Heat ${heat.timing_heat} (${heat.round})` : 'NO HEAT SELECTED'}
    </span>
   </div>
   <p>Select the event and heat from the 28 October 2026 meet program to automatically drive all live graphics, OBS stream overlays, and SwimTime timing.</p>
   <div className="fields" style={{marginTop:'10px'}}>
    <label style={{flex:1.4}}>
     <b>1. Select Event Name</b>
     <select
      aria-label="Event Name"
      value={currentEvent?.event_id || ''}
      onChange={e=>onSelectEvent?.(e.target.value)}
      disabled={busy || !events.length}
     >
      {events.map(ev=>(
       <option key={ev.event_id} value={ev.event_id}>
        Event {ev.timing_event}: {ev.name} ({ev.heats.length} heats)
       </option>
      ))}
     </select>
    </label>
    <label style={{flex:1}}>
     <b>2. Select Heat Name</b>
     <select
      aria-label="Heat Name"
      value={heat?.id || ''}
      onChange={e=>onSelectHeat?.(e.target.value)}
      disabled={busy || !eventHeats.length}
     >
      {eventHeats.map(h=>(
       <option key={h.id} value={h.id}>
        Heat {h.timing_heat} of {eventHeats.length} ({h.round}) — {h.entries?.length || 0} swimmers
       </option>
      ))}
     </select>
    </label>
   </div>
  </section>

  {/* ======================================================== */}
  {/* LIVE BROADCAST GRAPHICS & OBS STREAMING CONTROL SECTION */}
  {/* ======================================================== */}
  <section className="panel" style={{borderLeft:'4px solid #f1c875'}}>
   <div className="paneltitle">
    <h2>Live Broadcast Graphics & OBS Streaming Output</h2>
    <span className="tag" style={{background:programScene?'#512035':'#173659',color:programScene?'#ffc1ca':'#9ab0cd'}}>
     {programScene ? `ON-AIR: ${programScene.template}` : 'OFF-AIR (CLEAR)'}
    </span>
   </div>
   <p>Control live transparent graphic overlays for OBS Studio in real time. Graphics update dynamically with the selected <b>Event</b>, <b>Heat</b>, and <b>Players</b>.</p>

   {/* OBS Links Bar */}
   <div style={{background:'#09162a',padding:'12px 16px',borderRadius:6,border:'1px solid #23374e',marginBottom:'16px',display:'flex',alignItems:'center',gap:'12px',flexWrap:'wrap'}}>
    <span style={{fontSize:'12px',fontWeight:700,color:'#90accd'}}>OBS Browser Source URL:</span>
    <input
     readOnly
     value={obsCleanUrl}
     style={{flex:1,minWidth:'280px',background:'#060e1b',border:'1px solid #34465f',color:'#7cc9ff',fontFamily:'monospace',fontSize:'12px'}}
     onClick={e=>(e.target as HTMLInputElement).select()}
    />
    <button
     style={{background:copied?'#2f765c':'#174d87',borderColor:copied?'#5fbc8e':'#3872aa',fontSize:'12px',padding:'8px 14px'}}
     onClick={()=>copyUrl(obsCleanUrl)}
    >
     {copied ? '✓ Copied to Clipboard!' : '📋 Copy Clean OBS Link'}
    </button>
    <a target="_blank" href={obsCleanUrl} style={{fontSize:'12px'}}>Open 1920×1080 Output ↗</a>
   </div>

   {/* Dynamic Quick Preset Buttons */}
   <div style={{marginBottom:'16px',display:'flex',gap:'8px',flexWrap:'wrap',alignItems:'center'}}>
    <span style={{fontSize:'11px',fontWeight:700,color:'#9ab0cd',marginRight:'4px'}}>Quick Presets for this Heat:</span>
    <button
     style={{fontSize:'12px',padding:'6px 12px',background:'#15324e'}}
     disabled={busy||!heat}
     onClick={()=>{
      const t = isRelay ? 'SFS201A' : 'SFS200A';
      setSelectedTemplate(t);
      onGraphicAction?.('preview', t, selectedLane);
     }}
    >
     👤 Lower-Third ({isRelay?'SFS201A':'SFS200A'})
    </button>
    <button
     style={{fontSize:'12px',padding:'6px 12px',background:'#15324e'}}
     disabled={busy||!heat}
     onClick={()=>{
      const t = isRelay ? 'SFS201C' : 'SFS200C';
      setSelectedTemplate(t);
      onGraphicAction?.('preview', t, selectedLane, recordBadge);
     }}
    >
     🎖️ Athlete + Record ({isRelay?'SFS201C':'SFS200C'})
    </button>
    <button
     style={{fontSize:'12px',padding:'6px 12px',background:'#15324e'}}
     disabled={busy||!heat}
     onClick={()=>{
      const t = isRelay ? 'SFS203B' : 'SFS203A';
      setSelectedTemplate(t);
      onGraphicAction?.('preview', t, selectedLane);
     }}
    >
     📋 Start List ({isRelay?'SFS203B':'SFS203A'})
    </button>
    <button
     style={{fontSize:'12px',padding:'6px 12px',background:'#15324e'}}
     disabled={busy||!heat}
     onClick={()=>{
      setSelectedTemplate('SFS206');
      onGraphicAction?.('preview', 'SFS206', selectedLane);
     }}
    >
     🎓 Athlete + University (SFS206)
    </button>
    <button
     style={{fontSize:'12px',padding:'6px 12px',background:'#15324e'}}
     disabled={busy||!heat}
     onClick={()=>{
      setSelectedTemplate('SFS500');
      onGraphicAction?.('preview', 'SFS500', selectedLane);
     }}
    >
     ⏱️ Race Clock (SFS500)
    </button>
    <button
     style={{fontSize:'12px',padding:'6px 12px',background:'#0f4c3a',color:'#86efac',border:'1px solid #22c55e',fontWeight:700}}
     disabled={busy||!heat}
     onClick={()=>{
      setSelectedTemplate('SFS550');
      onGraphicAction?.('preview', 'SFS550', selectedLane);
     }}
    >
     ⏳ Countdown 75s (SFS550)
    </button>
    <button
     style={{fontSize:'12px',padding:'6px 12px',background:'#1e293b',color:'#38bdf8',border:'1px solid #0284c7',fontWeight:700}}
     disabled={busy||!heat}
     onClick={()=>{
      setSelectedTemplate('STANDBY');
      onGraphicAction?.('preview', 'STANDBY', selectedLane);
     }}
    >
     🛡️ Standby Card (STANDBY)
    </button>
    <button
     style={{fontSize:'12px',padding:'6px 12px',background:'#15324e'}}
     disabled={busy||!heat}
     onClick={()=>{
      const t = isRelay ? 'SFS302B' : 'SFS302A';
      setSelectedTemplate(t);
      onGraphicAction?.('preview', t, selectedLane);
     }}
    >
     🏆 Results ({isRelay?'SFS302B':'SFS302A'})
    </button>
   </div>

   {/* Two Monitors: Preview & Program */}
   <div className="twocol">
    {/* Preview Monitor */}
    <div style={{background:'#0c1728',border:'1px solid #23374e',borderRadius:6,padding:'16px'}}>
     <div className="paneltitle" style={{marginBottom:'10px'}}>
      <h3 style={{margin:0,fontSize:'15px',color:'#e8f0ff'}}>Broadcast preview</h3>
      <span className="tag">PREVIEW</span>
     </div>
     <iframe title="Broadcast preview" className="video checker" src="/broadcast_tvg/?preview=1" style={{borderRadius:4}}/>
     
     <div className="fields" style={{marginTop:'12px'}}>
      <label style={{flex:1.4}}>
       <small>Template</small>
       <select
        aria-label="Template"
        value={selectedTemplate}
        onChange={e=>setSelectedTemplate(e.target.value)}
       >
        <optgroup label="Official Templates">
         {Object.values(registry).map(t=>(
          <option key={t.code} value={t.code}>{t.code} / {t.name}</option>
         ))}
        </optgroup>
       </select>
      </label>
      <label style={{flex:1.1}}>
       <small>Select Player / Lane</small>
       <select
        aria-label="Player Lane"
        value={selectedLane}
        onChange={e=>setSelectedLane(Number(e.target.value))}
       >
        {(heat?.entries||[]).map(e=>(
         <option key={e.lane} value={e.lane}>
          Lane {e.lane}: {e.name} ({e.country})
         </option>
        ))}
        {(!heat?.entries?.length) && [1,2,3,4,5,6,7,8].map(l=><option key={l} value={l}>Lane {l}</option>)}
       </select>
      </label>
      <label style={{flex:0.9}}>
       <small>Record / Qual. Badge</small>
       <input
        placeholder="00:00:00"
        value={recordBadge}
        onChange={e=>setRecordBadge(e.target.value)}
        style={{height:34,fontSize:12,padding:'4px 8px'}}
       />
      </label>
     </div>

     <div className="buttons" style={{marginTop:'14px'}}>
      <button
       disabled={busy||!heat}
       onClick={()=>onGraphicAction?.('preview', selectedTemplate, selectedLane, recordBadge)}
      >
       Load preview
      </button>
      <button
       className="take"
       disabled={busy||!previewScene}
       onClick={()=>onGraphicAction?.('take')}
      >
       🔴 TAKE (Push to OBS)
      </button>
      <button
       disabled={busy||!programScene}
       onClick={()=>onGraphicAction?.('hold')}
      >
       Hold
      </button>
     </div>
     <p className="muted" style={{margin:'6px 0 0'}}>
      {registry[selectedTemplate]?.name || selectedTemplate}: {registry[selectedTemplate]?.approval_status || 'Ready'}.
     </p>
    </div>

    {/* Program Monitor (Live to OBS) */}
    <div style={{background:'#0c1728',border:'1px solid #23374e',borderRadius:6,padding:'16px'}}>
     <div className="paneltitle" style={{marginBottom:'10px'}}>
      <h3 style={{margin:0,fontSize:'15px',color:'#e8f0ff'}}>Broadcast program (Live on Stream)</h3>
      <span className="tag red">PROGRAM</span>
     </div>
     <iframe title="Broadcast program" className="video checker" src="/broadcast_tvg/" style={{borderRadius:4}}/>
     
     <div className="clock" style={{marginTop:'12px',fontSize:'36px',color:'#63daba'}}>
      {online&&!heat?.data_stale ? time(heat?.clock_ticks) : (clock || '—')}
     </div>
     
     <div className="buttons" style={{marginTop:'14px'}}>
      <button
       className="danger"
       disabled={busy||!programScene}
       onClick={()=>onGraphicAction?.('clear')}
      >
       ⬛ CLEAR GRAPHICS (Off-Air)
      </button>
      <a target="_blank" href={obsCleanUrl} style={{fontSize:'12px'}}>Open 1920×1080 Clean Layer ↗</a>
     </div>
     <p className="muted" style={{margin:'6px 0 0'}}>
      Active on stream: <b>{programScene ? `${programScene.template} (Lane ${programScene.lane || 1})` : 'None / Clear'}</b>
     </p>
    </div>
   </div>
  </section>

  {/* Dedicated Players List: Name, Nationality & Quick Stream Trigger */}
  {heat && heat.entries && heat.entries.length > 0 && (
   <section className="panel" style={{borderLeft:'4px solid #45d6b0'}}>
    <div className="paneltitle">
     <h2>Athletes & Nationalities List — Heat {heat.timing_heat} ({heat.entries.length} participants)</h2>
     <span className="tag" style={{background:'#123a31',color:'#5fe0ba'}}>START LIST</span>
    </div>
    <div className="tablewrap" style={{marginTop:'12px'}}>
     <table>
      <thead>
       <tr>
        <th style={{width:'80px'}}>Lane</th>
        <th>Player / Team Name</th>
        <th style={{width:'150px'}}>Nationality</th>
        <th>Affiliation / University</th>
        <th style={{width:'110px'}}>Seed Time</th>
        <th style={{width:'160px'}}>Live Graphics Action</th>
       </tr>
      </thead>
      <tbody>
       {heat.entries.map(entry => (
        <tr key={entry.lane}>
         <td>
          <span style={{background:'#173659',padding:'4px 10px',borderRadius:4,fontWeight:900,color:'#84d3ff'}}>
           Lane {entry.lane}
          </span>
         </td>
         <td>
          <b style={{fontSize:'14px',color:'#fff'}}>{entry.name}</b>
          {entry.members && entry.members.length > 0 && (
           <div style={{marginTop:4,display:'grid',gridTemplateColumns:'repeat(auto-fit, minmax(180px, 1fr))',gap:4}}>
            {entry.members.map((m, idx) => (
             <small key={idx} style={{color:'#9ab0cd'}}>
              {idx + 1}. {m.name} ({m.gender === 'MEN' ? 'M' : 'W'})
             </small>
            ))}
           </div>
          )}
         </td>
         <td>
          <div style={{display:'flex',alignItems:'center',gap:8}}>
           {entry.country && (
            <img
             src={`/assets/flags/${entry.country}.png`}
             alt={entry.country}
             style={{width:24,height:16,objectFit:'cover',borderRadius:2,border:'1px solid #334e68'}}
             onError={e => { (e.target as HTMLElement).style.display = 'none'; }}
            />
           )}
           <strong style={{color:'#7cc9ff',letterSpacing:0.5}}>{entry.country}</strong>
          </div>
         </td>
         <td><span style={{color:'#c4d8f0'}}>{entry.university || '—'}</span></td>
         <td><b style={{color:'#f5cf8d',fontVariantNumeric:'tabular-nums'}}>{time(entry.seed_ticks)}</b></td>
         <td>
          <div style={{display:'flex',gap:6}}>
           <button
            style={{fontSize:'11px',padding:'5px 8px',background:'#174d87'}}
            disabled={busy}
            onClick={()=>{
             const tmpl = isRelay ? 'SFS201A' : 'SFS200A';
             setSelectedLane(entry.lane);
             setSelectedTemplate(tmpl);
             onGraphicAction?.('direct', tmpl, entry.lane);
            }}
            title="Trigger Lower-Third on OBS"
           >
            📺 Lower-Third
           </button>
           <button
            style={{fontSize:'11px',padding:'5px 8px',background:'#1c5339',borderColor:'#2e8b60'}}
            disabled={busy}
            onClick={()=>{
             const tmpl = isRelay ? 'SFS201C' : 'SFS200C';
             setSelectedLane(entry.lane);
             setSelectedTemplate(tmpl);
             onGraphicAction?.('direct', tmpl, entry.lane, recordBadge);
            }}
            title="Trigger Athlete + Record on OBS"
           >
            🎖️ Record
           </button>
          </div>
         </td>
        </tr>
       ))}
      </tbody>
     </table>
    </div>
   </section>
  )}

  <section className="panel">
   <div className="paneltitle"><h2>SwimTime Network Display & FASU API Sync</h2><span className="tag">TEST OBSERVER + LIVE SYNC</span></div>
   <p>Receives SwimTime UDP packets on port 26, automatically syncs finished lane times to <code>POST /heats/:id/results</code>, and marks the heat <code>COMPLETED</code> via <code>PATCH /heats/:id/status</code> when SwimTime stops/ends the race.</p>
   {!feed?.enabled&&<div className="alert">This observed profile is disabled outside TEST mode.</div>}
   {feed?.error&&<div role="alert" className="alert">{feed.error}</div>}
   {feed?.warning&&<div role="alert" className="alert">{feed.warning}</div>}
   {st?.last_error&&<div role="alert" className="alert">API Sync Error: {st.last_error}</div>}
   <div className="fields">
    <label>SwimTime PC IPv4<input aria-label="SwimTime source IP" value={source} onChange={e=>setSource(e.target.value)} disabled={feed?.listening}/></label>
    <label>UDP port<input aria-label="SwimTime UDP port" type="number" min="1" max="65535" value={port} onChange={e=>setPort(Number(e.target.value))} disabled={feed?.listening}/></label>
    <label>API Base URL<input aria-label="API Base URL" value={apiUrl} onChange={e=>setApiUrl(e.target.value)} placeholder="https://fasugames2026.eusf.org.eg/v2/api"/></label>
    <label>Bearer Token<input aria-label="Bearer Token" type="password" value={token} onChange={e=>setToken(e.target.value)} placeholder="Paste JWT Bearer token"/></label>
    <label>Lane Offset (0 = exact match)<input aria-label="Lane Offset" type="number" min="-10" max="10" value={laneOffset} onChange={e=>setLaneOffset(Number(e.target.value))}/></label>
    <label><input type="checkbox" checked={autoSync} onChange={e=>setAutoSync(e.target.checked)}/> Auto-POST results & Auto-COMPLETE heat on race end</label>
   </div>
   <div className="buttons">
    <button disabled={!enabled||feed?.listening} onClick={()=>start(source,port,cfg)}>Start UDP TEST listener</button>
    <button disabled={!enabled||!feed?.listening} onClick={stop}>Stop UDP listener</button>
    <button disabled={!enabled||feed?.listening} onClick={replay}>Replay recorded TEST capture</button>
    {saveSync&&<button disabled={!enabled} onClick={()=>saveSync(cfg)}>Save API Settings</button>}
    {syncNow&&<button disabled={!enabled} onClick={()=>syncNow(cfg,true,false)}>Verify ONGOING Heat</button>}
    {syncNow&&<button className="take" disabled={!enabled} onClick={()=>syncNow(cfg,false,false)}>Sync Results to API Now</button>}
    {syncNow&&<button disabled={!enabled} onClick={()=>syncNow(cfg,false,true)}>Complete Heat Now</button>}
   </div>
   <p className="muted">API Sync Status: <b>{st?.state||'IDLE'}</b> | SwimTime Heat #: <b>{heatNum}</b> | Matched API Heat: <b>{st?.matched_heat_label||'Not matched yet'}</b> — {st?.last_message||'Ready'}</p>
  </section>

  <section className="panel"><div className="paneltitle"><h2>{online?feed?.state||'NO FEED':'FINS CONNECTION LOST'}</h2><span className="tag">TEST / NOT OFFICIAL</span></div>
   <div className="swimtime-summary">
    <div>
     <small>Source clock / no extrapolation</small>
     <div className="clock" data-testid="swimtime-clock">{clock||'—'}</div>
     <p>{clock?'RECEIVED TEST CLOCK':feed?.replay?'OFFLINE RECORDING':feed?.receiving?'NO CURRENT NONNEGATIVE CLOCK':'CLOCK SUPPRESSED'}</p>
    </div>
    <div>
     <p>Selected Heat: <b>{heat ? `${heat.gender} ${heat.name} (Heat ${heat.timing_heat})` : 'None'}</b></p>
     <p>Source: {feed?.source_ip||'—'} → UDP {feed?.port||26} | Freshness: {feed?.replay?'RECORDED / NOT LIVE':feed?.age_ms==null?'NO FEED':`${feed.age_ms} ms since last valid datagram`}</p>
     <p>Datagrams: <b>{feed?.counts.datagrams||0}</b> / parsed: <b>{feed?.counts.accepted||0}</b> / unparsed: <b>{feed?.counts.unparsed||0}</b></p>
     <p>LaneTime messages: <b>{feed?.counts.LaneTime||0}</b> / repeated content within 2 s: {feed?.counts.duplicate_payload_within_2s||0}</p>
    </div>
   </div>
   <p className="muted">1 tick = 0.0001 s for this observed TEST profile. Display truncates to hundredths.</p>
   
   <div className="tablewrap">
    <table data-testid="swimtime-channels">
     <thead>
      <tr>
       {['Lane','Player / Team','Nationality','Seed Time','Observed SwimTime','Raw code','Rank','Lap'].map(x=><th key={x}>{x}</th>)}
      </tr>
     </thead>
     <tbody>
      {lanesList.map(laneNum => {
       const swimmer = heat?.entries?.find(e => e.lane === laneNum);
       const chData = channelMap.get(laneNum);
       return (
        <tr key={laneNum} style={swimmer ? {background:'rgba(23, 77, 135, 0.1)'} : {}}>
         <td><b>Lane {laneNum}</b></td>
         <td>
          {swimmer ? (
           <>
            <b style={{color:'#fff'}}>{swimmer.name}</b>
            <small>{swimmer.university}</small>
            {swimmer.members?.map((m, idx)=>(
             <small key={idx}>{idx+1}. {m.name} ({m.gender[0]})</small>
            ))}
           </>
          ) : <span className="muted">—</span>}
         </td>
         <td>
          {swimmer?.country ? (
           <div style={{display:'flex',alignItems:'center',gap:6}}>
            <img
             src={`/assets/flags/${swimmer.country}.png`}
             alt={swimmer.country}
             style={{width:20,height:14,objectFit:'cover',borderRadius:2,border:'1px solid #334e68'}}
             onError={e => { (e.target as HTMLElement).style.display = 'none'; }}
            />
            <span style={{fontWeight:700,color:'#7cc9ff'}}>
             {swimmer.country}
            </span>
           </div>
          ) : '—'}
         </td>
         <td>{swimmer ? time(swimmer.seed_ticks) : '—'}</td>
         <td>
          {chData?.display_time ? (
           <b style={{color:'#45d6b0',fontSize:'15px'}}>{chData.display_time}</b>
          ) : <span className="muted">—</span>}
         </td>
         <td><small>{chData?.raw_value ?? '—'}</small></td>
         <td>{chData?.source_rank || '—'}</td>
         <td>{chData?.source_lap || '—'}</td>
        </tr>
       );
      })}
     </tbody>
    </table>
   </div>
   <p className="muted">Capture: {feed?.capture_file||'No live capture opened'}. Raw logs saved in runtime\swimtime.</p>
  </section>
 </>;
}
