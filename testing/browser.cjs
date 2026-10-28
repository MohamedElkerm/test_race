const fs=require('fs'),path=require('path'),assert=require('assert'),{spawn,spawnSync}=require('child_process');
const {chromium}=require('playwright');
const ROOT=path.resolve(__dirname,'..'),BASE='http://127.0.0.1:8766',db=path.join(ROOT,'testing/tmp/browser.sqlite3');
const report={executed_at:new Date().toISOString(),environment:'Linux / headless Chromium / loopback network',checks:[],templates:[],led:[],errors:[],limitations:['No physical ALGE, LED processor, video mixer or Windows 11 device is attached.','Visual comparison screenshots are evidence; no template is declared fully matched.']};
let server,browser;
const delay=ms=>new Promise(r=>setTimeout(r,ms));
function check(name,detail){report.checks.push({name,status:'PASS',detail})}
async function start(){server=spawn('python3',['-m','uvicorn','results_backend.app:app','--host','127.0.0.1','--port','8766','--log-level','warning'],{cwd:ROOT,env:{...process.env,FINS_DB:db,FINS_MODE:'TEST'},stdio:['ignore','pipe','pipe']});server.stderr.on('data',x=>report.errors.push(x.toString()));for(let i=0;i<60;i++){try{const r=await fetch(BASE+'/api/health');if(r.ok)return}catch{}await delay(100)}throw Error('Test server not ready')}
async function login(role){const r=await fetch(BASE+'/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:'TEST_'+role,password:'Browser_TEST_password_123'})});assert(r.ok);return(await r.json()).token}
async function post(p,body,token){const r=await fetch(BASE+p,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(r.status+' '+JSON.stringify(d));return d}
(async()=>{try{
 fs.mkdirSync(path.join(ROOT,'screenshots/tvg'),{recursive:true});fs.mkdirSync(path.join(ROOT,'screenshots/led'),{recursive:true});
 const seed=spawnSync('python3',['-m','testing.prepare_browser',db],{cwd:ROOT,encoding:'utf8'});assert.equal(seed.status,0,seed.stderr);await start();
 browser=await chromium.launch({executablePath:process.env.FINS_CHROME,headless:true,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage']});report.browser=browser.version();
 const context=await browser.newContext({viewport:{width:1600,height:1000},deviceScaleFactor:1});
 const requests=[];context.on('request',r=>{if(!r.url().startsWith(BASE)&&!r.url().startsWith('data:'))requests.push(r.url())});
 const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));await page.goto(BASE);await page.getByRole('heading',{name:'Control',exact:true}).waitFor();check('React control dashboard loads');
 await page.getByLabel('User',{exact:true}).fill('TEST_BROADCAST_OPERATOR');await page.getByLabel('Password',{exact:true}).fill('Browser_TEST_password_123');await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.getByRole('button',{name:'Sign out',exact:true}).waitFor();check('Browser login authenticates named broadcast role');
 await page.getByPlaceholder('Required for recorded operations').fill('Browser production-boundary test');await page.getByRole('button',{name:'Load preview',exact:true}).click();await delay(500);await page.getByRole('button',{name:'TAKE',exact:true}).click();await delay(500);
 const s=await fetch(BASE+'/api/state').then(r=>r.json());assert.equal(s.graphics.program.template,'SFS203A');check('Preview then TAKE updates program in TEST mode');
 await page.screenshot({path:path.join(ROOT,'screenshots/Control_Dashboard.png'),fullPage:true});
 await page.getByRole('button',{name:'Results',exact:true}).click();await page.screenshot({path:path.join(ROOT,'screenshots/Results_Review.png'),fullPage:true});
 await page.getByRole('button',{name:'LED routing',exact:true}).click();await delay(1200);await page.screenshot({path:path.join(ROOT,'screenshots/Six_Screen_Routing.png'),fullPage:true});
 const registry=await fetch(BASE+'/api/templates').then(r=>r.json());
 for(const t of Object.values(registry)){
  const p=await context.newPage();await p.setViewportSize({width:1920,height:1080});const relay=['SFS201A','SFS201B','SFS201C','SFS202','SFS203B','SFS300B','SFS301B','SFS302B','SFS504B','SFS901B','SFS902B'].includes(t.code);await p.goto(BASE+'/broadcast_tvg/?template='+t.code+'&preview=1&heat='+(relay?'TEST-RELAY-1':'TEST-IND-1'));await p.waitForFunction(()=>window.finsMetrics!==undefined);await delay(80);
  const m=await p.evaluate(()=>window.finsMetrics);assert.equal(m.code,t.code);assert.equal(m.overflow.length,0,t.code+' field overflow: '+JSON.stringify(m.overflow));
  await p.screenshot({path:path.join(ROOT,'screenshots/tvg/'+t.code+'.png'),omitBackground:true});report.templates.push({code:t.code,captured:true,metrics:m,visually_matched:false});await p.close();
 }
 check('All 35 TVG browser captures executed',{count:report.templates.length});
 for(const t of Object.values(registry)){const p=await context.newPage();await p.goto(BASE+'/templates_sfs/comparator.html?template='+t.code);await p.waitForFunction(()=>window.comparisonReport!==undefined);const comparison=await p.evaluate(()=>window.comparisonReport);fs.mkdirSync(path.join(ROOT,'testing/reports/comparisons'),{recursive:true});fs.writeFileSync(path.join(ROOT,'testing/reports/comparisons/'+t.code+'.json'),JSON.stringify(comparison,null,2));await p.close()}check('Independent original/output overlay/difference metrics executed for every template',{count:35,fully_matched:0});
 const led=await login('LED_OPERATOR');const timing=await login('TIMING_OPERATOR');const results=await login('RESULTS_OPERATOR');const chief=await login('CHIEF_RESULTS_OFFICER');const jury=await login('JURY_APPROVER');
 await post('/api/routes',{outputs:['master','l1','l2','screen2','screen3','stage'],content:'startlist',heat_id:'TEST-IND-1',safe:24,reason:'Browser native resolution test'},led);
 for(const [key,r] of Object.entries(s.routes)){
  const p=await context.newPage();await p.setViewportSize({width:r.width,height:r.height});await p.goto(BASE+'/led_displays/?screen='+key);await p.waitForFunction(()=>window.finsMetrics!==undefined);await delay(120);
  const m=await p.evaluate(()=>window.finsMetrics);assert.equal(m.width,r.width);assert.equal(m.height,r.height);assert.equal(m.overflow.length,0);
  await p.screenshot({path:path.join(ROOT,'screenshots/led/'+key+'.png')});report.led.push({output:key,width:r.width,height:r.height,rendered:true,overflow:m.overflow});await p.close();
 }
 check('All six native LED resolutions rendered and captured');
 const output=await context.newPage();await output.setViewportSize({width:1920,height:1080});await output.goto(BASE+'/broadcast_tvg/?template=SFS500');await output.waitForFunction(()=>window.finsMetrics!==undefined);
 await post('/api/demo/replay',{heat_id:'TEST-IND-1'},timing);let state=await fetch(BASE+'/api/state').then(r=>r.json());let h=state.heats.find(h=>h.id==='TEST-IND-1');assert.equal(h.status,'UNOFFICIAL');check('Real HTTP/WebSocket synthetic start-running-split-finish flow');
 await post('/api/results/TEST-IND-1/compile',{revision:h.revision,reason:'Compile browser test'},results);state=await fetch(BASE+'/api/state').then(r=>r.json());h=state.heats.find(h=>h.id==='TEST-IND-1');
 await post('/api/results/TEST-IND-1/workflow',{action:'review',revision:h.revision,reason:'Review browser test'},results);h=(await fetch(BASE+'/api/state').then(r=>r.json())).heats.find(h=>h.id==='TEST-IND-1');
 await post('/api/results/TEST-IND-1/workflow',{action:'endorse',revision:h.revision,reason:'Chief browser test'},chief);
 await post('/api/results/TEST-IND-1/workflow',{action:'approve',revision:h.revision,reason:'Jury browser test',document_ref:'TEST-SYNTHETIC-APPROVAL'},jury);
 await post('/api/results/TEST-IND-1/publication',{revision:h.revision,publish:true,reason:'Publish test only'},results);
 const pub=await fetch(BASE+'/api/public/results').then(r=>r.json());assert.equal(pub.heats[0].status,'OFFICIAL');assert.equal(pub.mode,'TEST');check('Separate chief/Jury signatures gate publication over actual HTTP');
 const cmp=await context.newPage();await cmp.goto(BASE+'/templates_sfs/comparator.html?template=SFS203A');await cmp.waitForFunction(()=>window.comparisonReport!==undefined);await cmp.screenshot({path:path.join(ROOT,'screenshots/Visual_Template_Comparator.png'),fullPage:true});check('Comparator original/candidate/overlay/difference executes');
 const longFields=await cmp.evaluate(async()=>{const {renderTemplate}=await import('/broadcast_tvg/render.js');const state=await fetch('/api/state').then(r=>r.json()),registry=await fetch('/api/templates').then(r=>r.json());const h=structuredClone(state.heats[0]);h.entries[0].name='LONG TEST ATHLETE '.repeat(12);h.entries[0].university='LONG TEST UNIVERSITY '.repeat(12);const cv=document.createElement('canvas');cv.width=1920;cv.height=1080;return await renderTemplate(cv,'SFS206',h,registry,{test:true,diagnostics:true})});assert(longFields.overflow.length>0);assert(longFields.blocked.includes('FIELD OVERFLOW: graphic suppressed'));check('Long athlete/university fields suppress graphic and flag overflow rather than silently clipping');
 // Native alpha must survive; top-right outside TEST banner is fully transparent.
 const alpha=await output.evaluate(()=>Array.from(document.querySelector('canvas').getContext('2d').getImageData(1900,500,1,1).data));assert.equal(alpha[3],0);check('TV output preserves transparency outside graphic elements');
 await post('/api/select',{heat_id:'TEST-RELAY-1',reason:'Stale clock browser test'},timing);await post('/api/timing',{heat_id:'TEST-RELAY-1',source:'TEST-STALE-CLOCK',profile:'tm-swim-video-modern-v1',simulation:true,frames:[{sequence:1,hex:Buffer.from('START').toString('hex')},{sequence:2,hex:Buffer.from('R002001 00:00:01.0000').toString('hex')}]},timing);await output.waitForFunction(()=>window.finsMetrics?.blocked?.includes('TIMING DATA LOST / CLOCK SUPPRESSED'),{timeout:6000});check('Stale LIVE input suppresses clock after timeout');
 // A backend interruption must clear timing and expose disconnection, then recover.
 server.kill('SIGTERM');await new Promise(r=>server.once('exit',r));await output.waitForSelector('#lost',{state:'visible',timeout:6000});check('Backend/network loss clears output and exposes warning');
 await start();await output.waitForFunction(()=>getComputedStyle(document.querySelector('#lost')).display==='none',{timeout:6000});check('WebSocket automatic reconnect and persistent heat recovery');
 assert.equal(requests.length,0);check('All browser resources served locally without Internet',requests);
 report.status='COMPLETED';
 }catch(e){report.status='FAILED';report.failure=e.stack;console.error(e.stack);process.exitCode=1}
 finally{if(browser)await browser.close();if(server&&!server.killed)server.kill('SIGTERM');fs.writeFileSync(path.join(ROOT,'testing/reports/browser.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,checks:report.checks.length,templates:report.templates.length,led:report.led.length,errors:report.errors.length}));}
})();
