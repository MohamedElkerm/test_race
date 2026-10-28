const fs=require('fs'),path=require('path'),assert=require('assert'),crypto=require('crypto'),{spawn,spawnSync}=require('child_process'),{chromium}=require('playwright');
const R=path.resolve(__dirname,'..'),B='http://127.0.0.1:8772',db=path.join(R,'testing/tmp/results-identity.sqlite3'),evidence=path.join(R,'screenshots/results_identity');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const report={status:'RUNNING',executed_at:new Date().toISOString(),environment:'Linux / headless Chromium / loopback HTTP',checks:[],outputs:[],physical_led_test:false,windows_test:false,layout_approved:false,fully_matched:false};let server,browser;
function check(name,detail){report.checks.push({name,status:'PASS',detail})}
async function start(){server=spawn('python3',['-m','uvicorn','results_backend.app:app','--port','8772','--log-level','warning'],{cwd:R,env:{...process.env,FINS_DB:db,FINS_MODE:'TEST'},stdio:'ignore'});for(let i=0;i<100;i++){try{if((await fetch(B+'/api/health')).ok)return}catch{}await delay(80)}throw Error('Results identity server unavailable')}
async function api(p,body,token){const r=await fetch(B+p,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(body)});assert(r.ok,await r.text())}
(async()=>{try{
 fs.mkdirSync(evidence,{recursive:true});assert.equal(spawnSync('python3',['-m','testing.prepare_browser',db],{cwd:R}).status,0);await start();
 const manifest=JSON.parse(fs.readFileSync(path.join(R,'assets_processed/results_identity/manifest.json')));
 for(const [key,a]of Object.entries(manifest.assets)){
  const png=path.join(R,'assets_processed',a.processed.slice('/assets/'.length));
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(png)).digest('hex'),a.png_sha256);
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(R,a.original))).digest('hex'),a.original_sha256);
 }
 check('Six supplied TGA and PNG asset checksums agree with source mapping');
 const token=(await(await fetch(B+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:'TEST_LED_OPERATOR',password:'Browser_TEST_password_123'})})).json()).token;
 const state=await fetch(B+'/api/state').then(r=>r.json()),keys=Object.keys(state.routes);
 browser=await chromium.launch({executablePath:process.env.FINS_CHROME,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});
 const context=await browser.newContext({deviceScaleFactor:1}),external=[],wrongIdentity=[];
 context.on('request',r=>{if(!r.url().startsWith(B)&&!r.url().startsWith('data:')&&!r.url().startsWith('blob:'))external.push(r.url());if(/branding|loc_4x3/i.test(r.url()))wrongIdentity.push(r.url())});
 for(const content of ['idle','startlist','results']){
  await api('/api/routes',{outputs:keys,content,heat_id:'TEST-IND-1',safe:24,reason:'TEST correct FISU SFS results identity'},token);
  for(const key of keys){
   const r=state.routes[key],p=await context.newPage();await p.setViewportSize({width:r.width,height:r.height});await p.goto(B+'/led_displays/?screen='+key);await p.waitForFunction(c=>window.finsMetrics?.displayed_content===c&&window.finsMetrics?.branding?.loaded,content);await delay(50);
   const m=await p.evaluate(()=>window.finsMetrics);assert.equal(m.width,r.width);assert.equal(m.height,r.height);assert.equal(m.branding.id,manifest.id);assert.equal(m.fully_matched,false);assert.equal(m.approved,false);assert.equal(m.overflow.length,0,JSON.stringify(m.overflow));
   if(content!=='idle'){
    assert(m.missing.includes('BAR_BASIC_WITH_BLUE.TGA'));assert(m.blocked.includes('ASSET MISSING / NOT APPROVED'));
    assert(!m.sprites.some(s=>['bar_basic','bar_standing_rank'].includes(s.key)),'Missing ranked row was silently substituted');
    for(const s of m.sprites){assert.equal(s.scale,1);assert(s.x>=r.safe&&s.y>=r.safe);assert(s.x+s.width<=r.width-r.safe&&s.y+s.height<=r.height-r.safe)}
    if(key==='stage'){assert.equal(m.pages,2);assert.equal(m.visible_lanes.length,4)}
    if(['l1','l2'].includes(key)){assert.equal(m.pages,8);assert.equal(m.visible_lanes.length,1)}
   }
   const diff=await p.evaluate(async()=>{
    const m=window.finsMetrics,c=document.querySelector('canvas').getContext('2d'),e=document.createElement('canvas');e.width=m.width;e.height=m.height;const ec=e.getContext('2d');ec.fillStyle='#000';ec.fillRect(0,0,e.width,e.height);
    let region,asset;
    if(m.displayed_content==='idle'){const d=m.branding.draw;asset='/assets/sfs/presentation.png';const im=await createImageBitmap(await(await fetch(asset)).blob());ec.drawImage(im,d.x,d.y,d.width,d.height);region={x:Math.ceil(d.x)+2,y:Math.ceil(d.y)+2,w:Math.floor(d.width)-4,h:Math.floor(d.height)-4}}
    else{const s=m.sprites.find(s=>s.key==='footer');asset=s.asset;const im=await createImageBitmap(await(await fetch(asset)).blob());ec.drawImage(im,s.x,s.y);region={x:s.x,y:s.y,w:s.width,h:s.height}}
    const a=ec.getImageData(region.x,region.y,region.w,region.h).data,b=c.getImageData(region.x,region.y,region.w,region.h).data;let changed=0;for(let i=0;i<a.length;i++)if(a[i]!==b[i])changed++;return{asset,region,compared_channels:a.length,changed_channels:changed};
   });assert.equal(diff.changed_channels,0,key+' original sprite changed or covered');
   await p.screenshot({path:path.join(evidence,key+'_'+content+'.png')});report.outputs.push({key,content,metrics:m,source_sprite_comparison:diff});check(key+' '+content+': native canvas, original results source and explicit approval status',diff);
   if(content==='results'){
    const variants=await p.evaluate(async()=>{
     const {renderLED}=await import('/led_displays/render.js?v=RESULTS-20261020-2'),s=await fetch('/api/state').then(r=>r.json()),key=new URLSearchParams(location.search).get('screen'),route=s.routes[key],cv=document.createElement('canvas'),out=[];
     for(const content of ['upcoming','live','splits','official','qualification','medals','notice']){
      const m=await renderLED(cv,{...route,content},s);out.push({content,overflow:m.overflow,missing:m.missing,blocked:m.blocked,sprites:m.sprites.map(x=>x.key),fields:m.fields.map(f=>f.value)});
     }
     const h=s.heats.find(h=>h.id===route.heat_id);h.status='LIVE';h.data_stale=true;const lost=await renderLED(cv,{...route,content:'live'},s);out.push({content:'stale',suppressed:lost.clock_suppressed,fields:lost.fields.map(f=>f.value)});
     h.data_stale=false;h.clock_ticks=435600;const running=await renderLED(cv,{...route,content:'live'},s);out.push({content:'running',fields:running.fields.map(f=>f.value),missing:running.missing});
     h.entries[0].timings=[{kind:'SPLIT',ticks:200000}];const splits=await renderLED(cv,{...route,content:'splits'},s);out.push({content:'split',overflow:splits.overflow,original:splits.sprites.some(x=>x.key==='bar_standing_rank')});
     const venue=await renderLED(cv,{...route,content:'idle'},{...s,mode:'VENUE'});out.push({content:'venue',blocked:venue.blocked,sprites:venue.sprites});
     const black=await renderLED(cv,{...route,blackout:true},s),pixels=cv.getContext('2d').getImageData(0,0,cv.width,cv.height).data;out.push({content:'blackout',black:!pixels.some((v,i)=>i%4!==3&&v!==0),blocked:black.blackout});
     h.entries[0].name='TEST LONG ATHLETE NAME '.repeat(12);const long=await renderLED(cv,{...route,content:'startlist'},{...s,server_time:0});out.push({content:'long_name',suppressed:long.blocked.includes('FIELD OVERFLOW / OUTPUT SUPPRESSED')});
     return out;
    });
    for(const v of variants){if(v.overflow)assert.equal(v.overflow.length,0,key+' '+v.content+JSON.stringify(v.overflow));if(['official','qualification','medals'].includes(v.content))assert(v.blocked.includes('AWAITING OFFICIAL APPROVAL'));if(v.content==='stale'){assert(v.suppressed);assert(v.fields.includes('TIMING DATA LOST'))}if(v.content==='running'){assert(v.fields.includes('43.56'));assert(v.missing.includes('SFS_CLOCK.TGA'))}if(v.content==='split')assert(v.original);if(v.content==='venue'){assert(v.blocked.includes('LED LAYOUT NOT APPROVED / OUTPUT BLOCKED'));assert.equal(v.sprites.length,0)}if(v.content==='blackout')assert(v.black&&v.blocked);if(v.content==='long_name')assert(v.suppressed)}
    check(key+': content modes, official gate, stale timing, real split sprite, venue gate, blackout, long name suppression',variants);
   }
   await p.close();
  }
 }
 const missing=await browser.newContext();await missing.route('**/assets/sfs/header2_lines.png',r=>r.abort());const mp=await missing.newPage();await mp.goto(B+'/led_displays/?screen=master');await mp.waitForFunction(()=>window.finsMetrics?.blocked.includes('RESULTS IDENTITY ASSET MISSING / OUTPUT BLOCKED'));check('Missing original SFS sprite blocks output');await mp.screenshot({path:path.join(evidence,'asset_missing.png')});await missing.close();
 const wrong=await browser.newContext();await wrong.route('**/assets/sfs/footer.png',r=>r.fulfill({status:200,contentType:'image/png',body:Buffer.from('different identity')}));const wp=await wrong.newPage();await wp.goto(B+'/led_displays/?screen=master');await wp.waitForFunction(()=>window.finsMetrics?.blocked.includes('RESULTS IDENTITY ASSET MISSING / OUTPUT BLOCKED'));assert((await wp.evaluate(()=>window.finsMetrics.branding.error)).includes('checksum'));check('Incorrect results sprite checksum blocks output');await wrong.close();
 const lan=await browser.newContext();await lan.addInitScript(()=>Object.defineProperty(globalThis.crypto,'randomUUID',{value:undefined,configurable:true}));const lp=await lan.newPage(),errors=[];lp.on('pageerror',e=>errors.push(e.message));await lp.goto(B+'/led_displays/?screen=l1');await lp.waitForFunction(()=>window.finsMetrics?.branding.loaded);assert.equal(errors.length,0);check('LAN client ID fallback works without randomUUID');await lan.close();
 const recovery=await context.newPage();await recovery.goto(B+'/led_displays/?screen=master');await recovery.waitForFunction(()=>window.finsMetrics?.branding.loaded);const stopped=new Promise(r=>server.once('exit',r));server.kill('SIGTERM');await stopped;await recovery.waitForSelector('#lost',{state:'visible',timeout:6000});check('Disconnected output clears live canvas and warns');await start();await recovery.waitForFunction(()=>getComputedStyle(document.querySelector('#lost')).display==='none',null,{timeout:7000});check('WebSocket reconnect restores the original SFS results source');
 assert.equal(external.length,0);assert.equal(wrongIdentity.length,0);check('No Internet dependencies or withdrawn venue identity requests',{external,wrongIdentity});
 report.status='COMPLETED';report.browser=browser.version();
 }catch(e){report.status='FAILED';report.error=e.stack;process.exitCode=1;console.error(e.stack)}finally{if(browser)await browser.close();if(server)server.kill('SIGTERM');fs.writeFileSync(path.join(R,'testing/reports/results_identity.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,checks:report.checks.length,captures:report.outputs.length,error:report.error}));}})();
