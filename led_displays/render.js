import{readyFonts,clock,loadImage}from '/broadcast_tvg/render.js';
import{loadIdentity,containArtwork,LED_IDENTITY_PATCH}from './identity.js?v=RESULTS-20261020-2';
// LED placement is an engineering adaptation, not an approved SFS TV template.
// Missing SFS backgrounds are left absent, with an explicit diagnostic warning.
export async function renderLED(canvas,route,state){
 canvas.width=route.width;canvas.height=route.height;
 const c=canvas.getContext('2d'),W=canvas.width,H=canvas.height,S=route.safe??24;
 const metrics={width:W,height:H,content:route.content,displayed_content:route.content,overflow:[],fields:[],sprites:[],missing:[],blocked:[],test:state.mode==='TEST',approved:false,fully_matched:false,patch:LED_IDENTITY_PATCH,branding:{loaded:false,approval:'AWAITING_LED_LAYOUT_AND_FISU_APPROVAL'}};
 const black=()=>{c.fillStyle='#000';c.fillRect(0,0,W,H)};black();
 if(route.blackout){metrics.blackout=true;return metrics}
 await readyFonts();
 function text(value,x,y,size,width,weight=900){
  value=String(value??'');c.font=`${weight} ${size}px Lato`;c.fillStyle='#fff';c.textBaseline='top';
  const measured=c.measureText(value).width;metrics.fields.push({value,x,y,size,width:measured,max_width:width,weight});
  if(measured>width||x<S||y<S||x+measured>W-S||y+size>H-S){metrics.overflow.push(value);return}
  c.fillText(value,x,y);
 }
 function status(message){text(message,S,H-S-16,16,W-2*S,700)}
 function stop(message){metrics.blocked.push(message);black();text(message,S,S,20,W-2*S);return metrics}
 if(!metrics.test)return stop('LED LAYOUT NOT APPROVED / OUTPUT BLOCKED');
 let identity;
 try{identity=await loadIdentity()}catch(error){metrics.branding.error=String(error);return stop('RESULTS IDENTITY ASSET MISSING / OUTPUT BLOCKED')}
 const {manifest,images}=identity;
 metrics.branding={...metrics.branding,loaded:true,id:manifest.id,source:manifest.source_folder_url,manifest:'/assets/results_identity/manifest.json',fully_matched:false};
 function sprite(key,x,y){const im=images[key];c.drawImage(im,x,y);metrics.sprites.push({key,x,y,width:im.width,height:im.height,scale:1,asset:manifest.assets[key].processed})}
 let content=route.content;
 if(route.playlist?.length){const total=route.playlist.reduce((n,p)=>n+p.seconds,0);let phase=Math.max(0,state.server_time-route.playlist_epoch)%total;for(const p of route.playlist){if(phase<p.seconds){content=p.content;break}phase-=p.seconds}}
 metrics.displayed_content=content;
 text('TEST / DEMO  |  FISU RESULTS SOURCE  |  LED LAYOUT NOT APPROVED',S,S,16,W-2*S,700);
 const available=H-2*S-46;
 if(available<=0)return stop('SAFE ZONE TOO LARGE / OUTPUT BLOCKED');
 if(content==='idle'){
  metrics.branding.draw=containArtwork(c,images.presentation,{x:S,y:S+22,width:W-2*S,height:available});
  status('ORIGINAL PRESENTATION.TGA / LED PLACEMENT AWAITING APPROVAL');return metrics;
 }
 const heat=state.heats?.find(h=>h.id===route.heat_id)||state.heats?.find(h=>h.id===state.selected_heat);
 if(!heat)return stop('NO COMPETITION DATA');
 const relay=!!heat.relay;
 const code=content==='startlist'?(relay?'SFS203B':'SFS203A'):['results','official'].includes(content)?(relay?'SFS302B':'SFS302A'):content==='qualification'?(relay?'SFS301B':'SFS301A'):content==='live'?'SFS500':content==='splits'?(relay?'SFS504B':'SFS504A'):content==='medals'?(relay?'SFS902B':'SFS902A'):'SFS003';
 metrics.template=code;
 metrics.missing=manifest.template_missing[code]||[];
 if(W-2*S<870||available<162)return stop('SAFE ZONE TOO LARGE FOR NATIVE SFS SPRITES');
 let entries=[...(heat.entries||[])];
 if(['results','official','qualification','medals'].includes(content))entries.sort((a,b)=>(a.rank??999)-(b.rank??999));
 if(content==='qualification')entries=entries.filter(a=>a.qualification);
 if(content==='medals')entries=entries.filter(a=>a.medal&&!a.fisu_team);
 if(content==='splits')entries=entries.map(a=>({...a,split:[...(a.timings||[])].reverse().find(t=>t.kind==='SPLIT')})).filter(a=>a.split).sort((a,b)=>a.split.ticks-b.split.ticks).slice(0,3);
 const officialGate=['official','qualification','medals'].includes(content)&&heat.status!=='OFFICIAL';
 const pageSize=Math.min(H<=256?1:H<=560?4:8,Math.floor((available-121)/41));
 const pages=Math.max(1,Math.ceil(entries.length/pageSize)),page=Math.floor(Math.max(0,state.server_time)/8)%pages;
 let visible=entries.slice(page*pageSize,(page+1)*pageSize);
 const diagnostic=officialGate||['live','notice','upcoming','medals'].includes(content)||!visible.length;
 const n=diagnostic?1:visible.length,blockHeight=121+n*41;
 const x=Math.floor((W-870)/2),y=S+22+Math.floor((available-blockHeight)/2),ry=y+83;
 metrics.page=page+1;metrics.pages=pages;metrics.visible_lanes=diagnostic?[]:visible.map(a=>a.lane);
 sprite('header2_lines',x,y);sprite('sfs_2',x,y);
 text('FINSWIMMING',x+142,y+7,30,570);
 let label=content==='startlist'?'START LIST':content==='official'?(officialGate?'APPROVAL PENDING':'FINAL RESULT'):content==='results'?(heat.status==='OFFICIAL'?'FINAL RESULT':['SCHEDULED','READY'].includes(heat.status)?'AWAITING RESULTS':heat.status+' RESULT'):content.toUpperCase();
 text(label+' - '+heat.gender+' '+heat.name,x+142,y+47,24,700);
 sprite('footer',x,ry+n*41);
 if(officialGate){metrics.blocked.push('AWAITING OFFICIAL APPROVAL');text('AWAITING OFFICIAL APPROVAL',x+15,ry+6,24,840)}
 else if(content==='live'){
  const stale=!!heat.data_stale;metrics.clock_suppressed=stale||heat.status!=='LIVE';
  const value=stale?'TIMING DATA LOST':heat.status!=='LIVE'?'WAITING FOR TIMING':clock(heat.clock_ticks);
  if(stale)metrics.blocked.push('TIMING DATA LOST / CLOCK SUPPRESSED');
  text(value,x+15,ry+6,24,840);
 }else if(content==='medals'){
  metrics.blocked.push('MEDAL ASSETS NOT APPROVED');text('MEDAL ASSETS MISSING / NOT APPROVED',x+15,ry+6,24,840);
 }else if(content==='notice'){
  sprite('bar_basic',x,ry);text(state.notice?.text||'NO OPERATIONAL NOTICE',x+15,ry+6,24,840);
 }else if(content==='upcoming'){
  const upcoming=state.heats.filter(h=>['READY','SCHEDULED'].includes(h.status));
  const next=upcoming.length?upcoming[Math.floor(state.server_time/8)%upcoming.length]:undefined;
  sprite('bar_basic',x,ry);text(next?`${next.gender} ${next.name} / ${next.round} / HEAT ${next.timing_heat}`:'NO UPCOMING RACES',x+15,ry+6,24,840);
 }else if(!visible.length){text('NO APPROVED DATA FOR THIS VIEW',x+15,ry+6,24,840)}
 else for(let i=0;i<visible.length;i++){
  const a=visible[i],rowY=ry+i*41;
  if(content==='splits'){
   const left=x+138;sprite('bar_standing_rank',left,rowY);
   text(a.lane,left+12,rowY+6,23,40);text(a.name,left+74,rowY+6,23,390);text(clock(a.split.ticks),left+487,rowY+6,22,98);
  }else{
   // BAR_BASIC_WITH_BLUE.TGA is absent. Do NOT replace it with BAR_BASIC,
   // LANE_BOX, BAR_STANDING_RANK, a crop from a JPG, or a newly drawn shape.
   text(content==='startlist'?a.lane:a.rank??'—',x+15,rowY+4,26,45);
   if(a.country){
    const cc=String(a.country).toUpperCase().trim();
    if(!/^[A-Z]{3}$/.test(cc))metrics.blocked.push('FLAG CODE INVALID');
    else try{const im=await loadImage('/assets/flags/'+cc+'.png');c.drawImage(im,x+77,rowY+6)}catch{metrics.blocked.push('FLAG MISSING '+cc)}
   }
   text(a.name||'',x+187,rowY+4,26,content==='startlist'?650:510);
   if(content!=='startlist')text(content==='qualification'?a.qualification:a.irm||clock(a.ticks),x+747,rowY+5,24,110);
  }
 }
 if(metrics.missing.length){metrics.blocked.push('ASSET MISSING / NOT APPROVED');status('ASSET MISSING: '+metrics.missing.join(', '))}
 else status(`${heat.status} / HEAT ${heat.timing_heat} / PAGE ${page+1} OF ${pages} / NOT APPROVED`);
 if(metrics.overflow.length){black();metrics.blocked.push('FIELD OVERFLOW / OUTPUT SUPPRESSED');text('FIELD TOO LONG / OPERATOR REVIEW REQUIRED',S,S,20,W-2*S)}
 return metrics;
}
