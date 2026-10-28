import {renderTemplate} from './render.js?v=10';import{subscribe}from './stream.js';
const q=new URLSearchParams(location.search),canvas=document.querySelector('canvas'),lost=document.querySelector('#lost');
const registry=await fetch('/api/templates').then(r=>r.json());let state,busy=false,drawAgain=false,lastBeat=0,connectionLost=false;
const client=globalThis.crypto?.randomUUID?.()||'tv-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
function fit(){const k=Math.min(innerWidth/1920,innerHeight/1080);canvas.style.width=1920*k+'px';canvas.style.height=1080*k+'px'}addEventListener('resize',fit);fit();
// Preload standby assets for zero-time immediate display
const standbyPres=new Image();standbyPres.src='/assets/sfs/presentation.png';

function drawStandby(){
 const c=canvas.getContext('2d');
 c.clearRect(0,0,1920,1080);
 const x=535,y=740;
 if(standbyPres.complete&&standbyPres.naturalWidth>0)c.drawImage(standbyPres,x,y);
 c.textBaseline='middle';
 c.fillStyle='#ffffff';
 c.font='900 17px Lato, sans-serif';
 const text='● LIVE TIMING STANDBY';
 const tw=c.measureText(text).width;
 c.fillText(text, x + (849 - tw) / 2, y + 266);
}

async function draw(){
 if(connectionLost){drawStandby();return}
 if(busy){drawAgain=true;return}busy=true;
 try{
  const scene=(!q.has('program')&&q.get('template'))?{template:q.get('template'),heat_id:q.get('heat')||state.selected_heat,lane:Number(q.get('lane')||1)}:state.graphics[q.has('preview')?'preview':'program'];
  if(!scene){canvas.getContext('2d').clearRect(0,0,1920,1080);return}
  let heat=scene.frozen_heat||state.heats.find(h=>h.id===scene.heat_id)||state.heats.find(h=>h.id===state.selected_heat)||state.heats[0];
  if(scene.template==='SFS550'||scene.template==='COUNTDOWN'){
   if(!scene.set_at){
    if(!globalThis._cdStart||globalThis._cdTmpl!==scene.template){
     globalThis._cdStart=Date.now()/1000;
     globalThis._cdTmpl=scene.template;
    }
    scene.set_at=globalThis._cdStart;
   }else{
    globalThis._cdStart=scene.set_at;
   }
  }else{
   globalThis._cdStart=null;
  }
  heat={...heat,selected_lane:scene.lane,scene_set_at:scene.set_at};

  // Manage smooth 33ms (~30fps) dynamic timer for countdown
  if(scene.template==='SFS550'||scene.template==='COUNTDOWN'){
   if(!globalThis._cdTimer){
    globalThis._cdTimer=setInterval(()=>{
     const cur=(!q.has('program')&&q.get('template'))?{template:q.get('template')}:state?.graphics?.[q.has('preview')?'preview':'program'];
     if(cur&&(cur.template==='SFS550'||cur.template==='COUNTDOWN'))draw();
     else{clearInterval(globalThis._cdTimer);globalThis._cdTimer=null;globalThis._cdStart=null}
    },33);
   }
  }else if(globalThis._cdTimer){
   clearInterval(globalThis._cdTimer);globalThis._cdTimer=null;globalThis._cdStart=null;
  }

  // Bind live SwimTime UDP timing & clock into heat
  const st = state.swimtime;
  if(st){
   if(st.clock_display || st.clock_raw){
    heat.clock_ticks = st.clock_raw ?? heat.clock_ticks;
    heat.clock_display = st.clock_display;
    heat.data_stale = !st.clock_fresh && !st.receiving;
   }
   if(st.channels && st.channels.length > 0){
    const chMap = new Map(st.channels.map(c => [c.channel, c]));
    heat.entries = (heat.entries || []).map(entry => {
     const ch = chMap.get(entry.lane);
     if(ch){
      const rk = (ch.source_rank && ch.source_rank !== "—") ? parseInt(ch.source_rank, 10) : entry.rank;
      return {
       ...entry,
       ticks: ch.raw_value ?? entry.ticks,
       display_time: ch.display_time || entry.display_time,
       rank: (rk && !isNaN(rk)) ? rk : entry.rank,
       lap: ch.source_lap
      };
     }
     return entry;
    });
   }
  }

  // Inject record/qualification from scene if specified
  if(scene.record || scene.qualification){
   heat.entries = (heat.entries || []).map(entry => {
    if(entry.lane === heat.selected_lane){
     return {
      ...entry,
      record: scene.record || entry.record,
      qualification: scene.qualification || entry.qualification
     };
    }
    return entry;
   });
  }
  const isClean=q.has('clean');
  const metrics=await renderTemplate(canvas,scene.template,heat,registry,{test:isClean?false:(state.mode==='TEST'),diagnostics:!isClean});
  window.finsMetrics=metrics;
 }finally{busy=false;if(drawAgain){drawAgain=false;draw()}}
}
subscribe(s=>{state=s;connectionLost=false;lost.style.display='none';draw();if(performance.now()-lastBeat>1800){lastBeat=performance.now();fetch('/api/output/heartbeat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_id:client,output:'tv',width:1920,height:1080,revision:s.revision})}).catch(()=>{})}},()=>{connectionLost=true;drawStandby();});
