/* Official-source sprites only. Missing assets are reported, never replaced.
   All coordinates refer to native 1920 x 1080. Approval is external to rendering. */
const cache=new Map();
export async function loadImage(url){
 if(!cache.has(url)) cache.set(url,new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(Error('Asset unavailable: '+url));i.src=url}));
 return cache.get(url);
}
export async function readyFonts(){
 await Promise.all([document.fonts.load('900 30px Lato'),document.fonts.load('700 24px Lato'),document.fonts.load('400 24px Lato')]);
}
export const clock=t=>{
 if(t===null||t===undefined)return '—';const n=Math.floor(t/100);
 const m=Math.floor(n/6000),s=Math.floor(n/100)%60,c=n%100;
 return `${m?m+':':''}${String(s).padStart(m?2:1,'0')}.${String(c).padStart(2,'0')}`;
};
export async function renderTemplate(canvas,code,heat,registry,{test=true,diagnostics=true}={}){
 const c=canvas.getContext('2d');c.clearRect(0,0,1920,1080);
 const t=registry[code],metrics={code,missing:t?.missing||[],fields:[],overflow:[],blocked:[],approval:t?.approval_status||'UNKNOWN TEMPLATE'};
 if(!t){return metrics}
 let unavailable=[];
 const required=[...t.assets.filter(a=>a.processed).map(a=>a.processed)];
 const allFlags=[...new Set((heat?.entries||[]).map(a=>a.country).filter(Boolean))];
 await Promise.all([...required,...allFlags.map(cc=>'/assets/flags/'+cc+'.png')].map(url=>loadImage(url).catch(()=>unavailable.push(url))));
 await readyFonts();
 function sprite(asset,x,y){const url='/assets/sfs/'+asset+'.png',p=cache.get(url);if(p&&!unavailable.includes(url))p.then(im=>{});return loadImage(url).then(im=>c.drawImage(im,x,y));}
 // Rendering order is awaited to preserve alpha compositing and text placement.
 async function image(asset,x,y){try{const im=await loadImage('/assets/sfs/'+asset+'.png');c.drawImage(im,x,y)}catch(e){metrics.blocked.push(String(e))}}
 function text(value,x,y,size=24,width=700,color='#fff',weight=900){
  value=String(value??'');c.font=`${weight} ${size}px Lato`;c.fillStyle=color;c.textBaseline='top';
  let measured=c.measureText(value).width;
  if(width>0 && measured>width){
   const scaledSize = Math.max(13, Math.floor(size * (width / measured)));
   c.font = `${weight} ${scaledSize}px Lato`;
   measured = c.measureText(value).width;
   if(measured > width){
    c.save();
    c.translate(x, y);
    c.scale(width / measured, 1);
    c.fillText(value, 0, 0);
    c.restore();
    metrics.fields.push({value,x,y,size:scaledSize,width:measured,max_width:width,weight});
    return;
   }
   size = scaledSize;
  }
  metrics.fields.push({value,x,y,size,width:measured,max_width:width,weight});
  c.fillText(value,x,y);
 }
 // Supplied flags already include the IOC code; draw the entire 93x26 MEDIUM sprite natively.
 async function flag(code,x,y){try{const im=await loadImage('/assets/flags/'+code+'.png');c.drawImage(im,x,y)}catch{metrics.blocked.push('FLAG MISSING '+code)}}
 const entries=heat?.entries||[],selected=entries.find(a=>a.lane===heat?.selected_lane)||entries[0]||{};
 const isRelay=!!heat?.relay;
 const relayCodes=['SFS201A','SFS201B','SFS201C','SFS202','SFS203B','SFS300B','SFS301B','SFS302B','SFS504B','SFS901B','SFS902B'];
 if(relayCodes.includes(code)&&!isRelay)metrics.blocked.push('RELAY HEAT REQUIRED');
 const description=`${heat?.gender||''} ${heat?.name||''} - ${heat?.round||''}${heat?.timing_heat?' '+heat.timing_heat:''}`.trim();
 const status=heat?.status||'NO DATA';
 async function header(y,title='FINSWIMMING',sub=description,x=522){await image('header2_lines',x,y);await image('sfs_2',x,y);text(title,x+142,y+7,30,620);text(sub,x+142,y+47,24,700)}
 let rows=entries;
 if(t.kind==='results'||t.kind==='qualification'||t.kind==='medals')rows=[...rows].sort((a,b)=>(a.rank??999)-(b.rank??999));
 if(t.kind==='qualification'){
  rows=rows.filter(a=>a.qualification);
  if(status!=='OFFICIAL'||!rows.length)metrics.blocked.push('Approved qualification decisions required');
 }
 if(['medals','medal','winner'].includes(t.kind)){
  if(status!=='OFFICIAL')metrics.blocked.push('OFFICIAL results required');
  if(t.kind==='winner')rows=entries.filter(a=>a.rank===1&&!a.fisu_team);
  else rows=entries.filter(a=>a.medal&&!a.fisu_team);
  if(!rows.length)metrics.blocked.push('No approved winner/medal decision');
 }
 if(t.kind==='startlist'||t.kind==='results'||t.kind==='qualification'||t.kind==='medals'){
  const n=Math.min(rows.length,8),x=522,fy=986,ry=fy-n*41,hy=ry-83;
  const label=t.kind==='startlist'?'START LIST':t.kind==='results'?(status==='OFFICIAL'?'FINAL RESULT':status+' RESULT'):t.kind==='qualification'?'ADVANCE TO PHASE':'MEDALS';
  await header(hy,'FINSWIMMING',label+' - '+description);
  for(let i=0;i<n;i++){
   const a=rows[i],y=ry+41*i;
   await image('bar_basic',x,y);
   if(t.kind==='startlist')await image('lane_box',x,y);
   const value=t.kind==='startlist'?a.lane:a.rank??'—';
   text(value,x+15,y+4,26,45);if(a.country)await flag(a.country,x+77,y+6);
   text(a.name||'',x+187,y+4,26,t.kind==='startlist'?650:510);
   if(t.kind!=='startlist')text(a.irm||a.display_time||clock(a.ticks),x+747,y+5,24,110);
  }
  // Native footer already includes SHARM EL SHEIKH 2026; never draw duplicate event text.
  await image('footer',x,fy);
 }else if(t.kind==='university'){
  await image('header2_lines',522,946);await image('sfs_2',522,946);
  if(selected.country)await flag(selected.country,666,953);
  text(selected.name||'',777,953,27,600);text(selected.university||'',666,991,24,712);
 }else if(t.kind==='athlete'||t.kind==='team'){
  await image('header1_line',522,987);await image('sfs_1',522,987);
  if(selected.country)await flag(selected.country,606,993);
  text(selected.name||'',713,992,26,560);
  if(code.endsWith('B')){if(!selected.irm)metrics.blocked.push('Approved false-start/IRM decision required');await image('short_box_red',1350,987);text(selected.irm||'IRM PENDING',1380,993,22,165)}
  if(code.endsWith('C')){
   const recText = selected.record || selected.qualification || (selected.display_time ? 'TIME: ' + selected.display_time : (selected.seed_ticks ? clock(selected.seed_ticks) : '00:00:00'));
   await image('short_box_light_blue',1350,1028);text(recText,1370,1034,22,180);
  }
 }else if(t.kind==='relay_members'){
  const x=96,ys=1000-(selected.members?.length||4)*41;
  await image('header1_short_no_logo',x,ys-41);text(selected.name||'',x+12,ys-36,23,430);
  for(let i=0;i<(selected.members?.length||0);i++){await image('bar_basic_short',x,ys+i*41);text((i+1)+'. '+selected.members[i].name,x+12,ys+i*41+5,22,430)}
  await image('footer_short',x,1000);
 }else if(t.kind==='lane'){
  await image('finish',96,70);text('LANE '+(selected.lane??'—'),110,76,23,130);
  await image('finish',96,987);text('LANE '+(selected.lane??'—'),110,993,23,130);
 }else if(t.kind==='area'){
  await image('short_box_light_blue',96,987);text(code==='SFS205A'?'WARM UP POOL':'CALL ROOM',111,993,20,195);
 }else if(t.kind==='clock'||t.kind==='standings'){
  const stale=!!heat?.data_stale;
  if(stale)metrics.blocked.push('TIMING DATA LOST / CLOCK SUPPRESSED');
  if(code==='SFS503'&&!entries.some(a=>a.timings?.some(t=>t.kind==='FINISH')))metrics.blocked.push('Finish event required');
  await image('csp_clock',1520,987);
  const finish=[...(selected.timings||[])].reverse().find(t=>t.kind==='FINISH');
  const clkVal = heat?.clock_display || clock(code==='SFS503'?finish?.ticks:heat?.clock_ticks);
   text(stale?'DATA LOST':(clkVal !== '—' ? clkVal : (heat?.clock_ticks ? clock(heat.clock_ticks) : '00:00.00')),1580,994,24,230);
  if(t.kind==='standings'){
   let ss=entries.map(a=>({...a,split:[...(a.timings||[])].reverse().find(t=>t.kind==='SPLIT')})).filter(a=>a.split).sort((a,b)=>a.split.ticks-b.split.ticks).slice(0,3);
   for(let i=0;i<ss.length;i++){
    const a=ss[i];await image('bar_standing_rank',96,70+i*41);text(a.lane,108,76+i*41,23,40);text(a.name,170,76+i*41,23,390);text(clock(a.split.ticks),583,76+i*41,22,98);
   }
   if(!ss.length)metrics.blocked.push('Split data required');
  }
 }else if(t.kind==='schedule'){
  const list=heat?.schedule||[];await header(946-list.length*41,'FINSWIMMING','SESSION SCHEDULE');
  for(let i=0;i<Math.min(list.length,8);i++){await image('bar_basic',522,1029-list.length*41+i*41);text(list[i],538,1034-list.length*41+i*41,23,830)}
  if(!list.length)metrics.blocked.push('Schedule source not assigned');
 }else if(t.kind==='winner'){
  const a=rows[0]||{};await header(946,a.name||'WINNER PENDING',description+' - WINNER');
 }else if(t.kind==='medal'){
  const a=rows[0]||{};await image('header1_line',522,987);await image('sfs_1',522,987);text(a.name||'MEDAL DECISION PENDING',610,993,25,680);
 }else if(t.kind==='countdown'||code==='SFS550'||code==='COUNTDOWN'){
  const now=Date.now()/1000;
  const setAt=heat?.scene_set_at||globalThis._cdStart||now;
  if(!globalThis._cdStart)globalThis._cdStart=setAt;
  const elapsed=Math.max(0,now-setAt);
  const remainingFloat=Math.max(0,75-elapsed);
  const remaining=Math.ceil(remainingFloat);
  const progress=Math.min(1,Math.max(0.005,elapsed/75));

  // Pure circular countdown with NO card/box background
  const cx=960,cy=540;
  c.save();

  // Circular Track (clean dark translucent slate ring)
  const radius=140,strokeW=34;
  c.beginPath();
  c.arc(cx,cy,radius,0,Math.PI*2);
  c.lineWidth=strokeW;
  c.strokeStyle='rgba(30, 36, 48, 0.85)';
  c.stroke();

  // Dynamic Progress Arc (sweeping clockwise)
  const startAngle=-Math.PI/2;
  const sweepAngle=Math.PI*2*progress;
  const endAngle=startAngle+sweepAngle;

  const grad=c.createLinearGradient(cx-radius,cy-radius,cx+radius,cy+radius);
  grad.addColorStop(0,'#1848dc');
  grad.addColorStop(0.4,'#0284c7');
  grad.addColorStop(1,'#38bdf8');

  c.beginPath();
  c.arc(cx,cy,radius,startAngle,endAngle,false);
  c.lineWidth=strokeW;
  c.strokeStyle=grad;
  c.lineCap='round';
  c.stroke();

  // Leading 3D Sphere / Bead at the tip
  const tipX=cx+Math.cos(endAngle)*radius;
  const tipY=cy+Math.sin(endAngle)*radius;
  const beadR=strokeW*0.62;

  // Ambient glow behind bead
  c.save();
  c.shadowColor='rgba(56, 189, 248, 0.7)';
  c.shadowBlur=16;
  c.beginPath();
  c.arc(tipX,tipY,beadR,0,Math.PI*2);
  c.fillStyle='#0ea5e9';
  c.fill();
  c.restore();

  // 3D Sphere Radial Highlight
  const sphereGrad=c.createRadialGradient(
   tipX-beadR*0.25, tipY-beadR*0.25, beadR*0.05,
   tipX, tipY, beadR
  );
  sphereGrad.addColorStop(0,'#7dd3fc');
  sphereGrad.addColorStop(0.35,'#38bdf8');
  sphereGrad.addColorStop(0.75,'#0ea5e9');
  sphereGrad.addColorStop(1,'#0369a1');

  c.beginPath();
  c.arc(tipX,tipY,beadR,0,Math.PI*2);
  c.fillStyle=sphereGrad;
  c.fill();

  // Center Seconds Number: bold white with subtle shadow for crisp broadcast visibility
  c.textBaseline='middle';
  c.textAlign='center';
  c.shadowColor='rgba(0, 0, 0, 0.8)';
  c.shadowBlur=12;
  c.shadowOffsetX=2;
  c.shadowOffsetY=3;
  c.fillStyle='#ffffff';
  c.font=remaining>=100?'900 96px Lato, Arial, sans-serif':'900 124px Lato, Arial, sans-serif';
  c.fillText(remaining===0?'0':String(remaining),cx,cy+2);
  c.restore();

  }else if(t.kind==='comp_logo'||code==='COMP_LOGO'||code==='LOGO'||code==='COMPETITION_LOGO'){
   const x=535,y=416;
   await image('competition_logo',x,y);
  }else if(t.kind==='standby'||code==='STANDBY'){
  const x=535,y=740;
  await image('presentation',x,y);
  c.textBaseline='middle';
  c.fillStyle='#ffffff';
  c.font='900 17px Lato, sans-serif';
  const text='● LIVE TIMING STANDBY';
  const tw=c.measureText(text).width;
  c.fillText(text,x+(849-tw)/2,y+266);
 }else{
  await header(946,'FINSWIMMING',code==='SFS900'?'VICTORY CEREMONY - '+description:code==='SFS001'||code==='SFS002'?'SHARM EL SHEIKH - '+(heat?.venue||'VENUE CONFIRMATION PENDING'):description);

 }
 metrics.blocked.push(...unavailable.map(x=>'ASSET UNAVAILABLE '+x));
 // Auto-fitting handles overflow cleanly; never suppress/blank broadcast graphics.
 if(diagnostics&&(metrics.missing.length||metrics.blocked.length||metrics.overflow.length)){
  c.fillStyle='rgba(88,7,18,.95)';c.fillRect(60,75,1500,metrics.missing.length?92:56);
  text('NOT APPROVED / '+[...metrics.missing,...metrics.blocked].slice(0,4).join(' | '),76,92,20,1460,'#fff',700);
 }
 if(test&&diagnostics&&code!=='SFS550'&&code!=='COUNTDOWN'&&code!=='COMP_LOGO'&&code!=='LOGO'){c.fillStyle='rgba(4,20,44,.94)';c.fillRect(60,18,1800,36);text('TEST / ENGINEERING BUILD  •  '+code+'  •  NOT FISU APPROVED',76,25,21,1760,'#fff',700)}
 return metrics;
}
