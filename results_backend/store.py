"""Transactional SQLite competition store, timing provenance and approval boundary."""
import contextlib, hashlib, json, os, secrets, sqlite3, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ROLES={'TIMING_OPERATOR','RESULTS_OPERATOR','CHIEF_RESULTS_OFFICER','JURY_APPROVER','BROADCAST_OPERATOR','LED_OPERATOR','SYSTEM_ADMINISTRATOR','SINGLE_OPERATOR'}
SCREENS={
 'master':{'name':'Master Screen','width':3072,'height':1024},
 'l1':{'name':'L1 Slide','width':1408,'height':256},
 'l2':{'name':'L2 Slide','width':1280,'height':256},
 'screen2':{'name':'Screen 2','width':1792,'height':768},
 'screen3':{'name':'Screen 3','width':1536,'height':1024},
 'stage':{'name':'Stage Screen','width':1536,'height':512},
}
J=lambda x:json.dumps(x,ensure_ascii=False,separators=(',',':'))

class DomainError(Exception):
    def __init__(self,message,status=400):self.status=status;super().__init__(message)

class Store:
    def __init__(self,path,mode='TEST',operator_mode=None):
        self.operator_mode=operator_mode or os.getenv('FINS_OPERATOR_MODE','MULTI')
        if self.operator_mode not in ('SINGLE','MULTI'):raise ValueError('Invalid operator mode')
        if mode not in ('TEST','VENUE'):raise ValueError('Mode must be TEST or VENUE')
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.mode=mode
        with self.db() as c:
            c.executescript((ROOT/'results_backend/schema.sql').read_text())
            previous=c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
            if previous and previous[0]!=mode:raise ValueError('Database mode mismatch; use a separate VENUE database')
            c.execute("INSERT OR IGNORE INTO meta VALUES('mode',?)",(mode,))
            c.execute("INSERT OR IGNORE INTO meta VALUES('selected_heat','')")
            c.execute("INSERT OR IGNORE INTO meta VALUES('revision','0')")
            for k in SCREENS:c.execute('INSERT OR IGNORE INTO routes(output,content) VALUES(?,?)',(k,'idle'))
            c.execute("INSERT OR IGNORE INTO graphics VALUES('tv',NULL,NULL,0)")
            # A server restart never resumes an authoritative live clock by extrapolation.
            c.execute("UPDATE heats SET recovery_hold=1 WHERE status='LIVE'")
    @contextlib.contextmanager
    def db(self,write=True):
        c=sqlite3.connect(self.path,timeout=10);c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=10000')
        try:
            if write:c.execute('BEGIN IMMEDIATE')
            yield c
            if write:c.commit()
        except: c.rollback();raise
        finally:c.close()
    def audit(self,c,user,action,entity,old,new,source,reason):
        if not reason or not source:raise DomainError('Change source and reason required')
        c.execute('INSERT INTO audit(at,user_id,action,entity,old_value,new_value,source,reason) VALUES(?,?,?,?,?,?,?,?)',(time.time(),user,action,entity,J(old),J(new),source,reason))
        c.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
    def create_user(self,user,role,password):
        if role not in ROLES or len(password)<12:raise DomainError('Valid role and password of at least 12 characters required')
        if not user or len(user)>100:raise DomainError('User ID required, max 100 characters')
        salt=secrets.token_hex(16);digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
        with self.db() as c:
            c.execute('INSERT INTO users(id,role,salt,password_hash) VALUES(?,?,?,?)',(user,role,salt,digest))
            self.audit(c,'bootstrap','USER_CREATE',user,None,{'role':role},'local CLI','Operator provisioning')
    def login(self,user,password):
        with self.db() as c:
            row=c.execute('SELECT * FROM users WHERE id=? AND enabled=1',(user,)).fetchone()
            # Scrypt also runs for unknown users to limit account enumeration via timing.
            salt=bytes.fromhex(row['salt']) if row else b'\0'*16
            digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex()
            if not row or not secrets.compare_digest(digest,row['password_hash']):raise DomainError('Invalid credentials',401)
            if self.operator_mode=='SINGLE' and row['role']!='SINGLE_OPERATOR':raise DomainError('Use the single operator account in this mode',403)
            if self.operator_mode=='MULTI' and row['role']=='SINGLE_OPERATOR':raise DomainError('Single operator mode is not enabled',403)
            token=secrets.token_urlsafe(32);c.execute('DELETE FROM tokens WHERE expires<?',(time.time(),))
            c.execute('INSERT INTO tokens VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user,time.time()+8*3600))
            return {'token':token,'user':user,'role':row['role'],'expires_in':28800}
    def identity(self,token):
        with self.db(False) as c:
            r=c.execute('SELECT users.id,users.role FROM tokens JOIN users ON users.id=tokens.user_id WHERE tokens.hash=? AND tokens.expires>? AND users.enabled=1',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
            if not r:raise DomainError('Authentication required',401)
            if (self.operator_mode=='SINGLE') != (r['role']=='SINGLE_OPERATOR'):raise DomainError('Session mode changed; sign in again',401)
            return dict(r)
    def logout(self,token):
        with self.db() as c:c.execute('DELETE FROM tokens WHERE hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def require(self,actor,*roles):
        if self.operator_mode=='SINGLE' and actor['role']=='SINGLE_OPERATOR':return
        if actor['role'] not in roles:raise DomainError('Role not authorised for this action',403)
    def heat(self,c,heat_id,expected=None):
        r=c.execute('SELECT * FROM heats WHERE id=?',(heat_id,)).fetchone()
        if not r:raise DomainError('Unknown heat',404)
        r=dict(r)
        if expected is not None and expected!=r['revision']:raise DomainError('Revision conflict; refresh before retrying',409)
        return r
    def invalidate(self,c,heat_id):
        c.execute('UPDATE approvals SET revoked=1 WHERE heat_id=?',(heat_id,))
        c.execute('UPDATE heats SET published=0 WHERE id=?',(heat_id,))
        # A held result must never survive a reopened/revised heat.
        g=c.execute("SELECT * FROM graphics WHERE id='tv'").fetchone()
        for col in ('preview','program'):
            if g[col]:
                scene=json.loads(g[col])
                if scene.get('heat_id')==heat_id and (scene.get('template','').startswith(('SFS3','SFS9')) or scene.get('frozen_heat')):
                    c.execute(f"UPDATE graphics SET {col}=NULL,held=0 WHERE id='tv'")
    def import_meet(self,actor,payload):
        self.require(actor,'RESULTS_OPERATOR','SYSTEM_ADMINISTRATOR')
        if payload.get('data_mode')!=self.mode:raise DomainError('Data mode mismatch')
        if not payload.get('source') or not payload.get('reason'):raise DomainError('Source and reason required')
        heats=payload.get('heats',[])
        if not 1<=len(heats)<=200:raise DomainError('Expected 1..200 heats')
        with self.db() as c:
            cid=payload['championship_id'];c.execute('INSERT OR IGNORE INTO championships VALUES(?,?,?,?)',(cid,payload['name'],self.mode,payload['source']))
            for h in heats:
                if self.mode=='TEST' and not h['id'].startswith('TEST-'):raise DomainError('TEST heat IDs must start TEST-')
                if h['gender'] not in ('MEN','WOMEN','MIXED'):raise DomainError('Invalid gender')
                c.execute('INSERT OR IGNORE INTO sessions VALUES(?,?,?,?,?,?)',(h['session_id'],cid,h.get('session_name','Session'),h.get('date'),h.get('session_start'),payload['source']))
                c.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)',(h['event_id'],h['session_id'],h['name'],h['discipline'],h['gender'],h['round'],int(h.get('relay',False))))
                c.execute('INSERT INTO heats(id,event_id,timing_event,timing_heat,status) VALUES(?,?,?,?,?)',(h['id'],h['event_id'],h['timing_event'],h['timing_heat'],'READY'))
                lanes=set()
                for a in h['entries']:
                    lane=a['lane']
                    if not isinstance(lane,int) or lane in lanes or not 0<=lane<=12:raise DomainError('Duplicate or invalid lane')
                    lanes.add(lane)
                    if h.get('relay'):
                        team=a['team'];members=team['members']
                        if len(members)!=4 or [m['gender'] for m in members]!=['MEN','WOMEN','MEN','WOMEN']:raise DomainError('Mixed relay order must be M-W-M-W (Technical Handbook p5)')
                        if len({m['id'] for m in members})!=4:raise DomainError('Duplicate relay athlete')
                        c.execute('INSERT INTO teams VALUES(?,?,?,?)',(team['id'],team['name'],team['country'],int(team.get('fisu_team',False))))
                        for i,m in enumerate(members):
                            self.insert_athlete(c,m);c.execute('INSERT INTO relay_members VALUES(?,?,?)',(team['id'],i+1,m['id']))
                        c.execute('INSERT INTO entries VALUES(?,?,?,?,?)',(h['id'],lane,None,team['id'],a.get('seed_ticks')))
                    else:
                        self.insert_athlete(c,a['athlete']);c.execute('INSERT INTO entries VALUES(?,?,?,?,?)',(h['id'],lane,a['athlete']['id'],None,a.get('seed_ticks')))
            selected=c.execute("SELECT value FROM meta WHERE key='selected_heat'").fetchone()[0]
            if not selected:c.execute("UPDATE meta SET value=? WHERE key='selected_heat'",(heats[0]['id'],))
            self.audit(c,actor['id'],'IMPORT_MEET',cid,None,payload,payload['source'],payload['reason'])
        return {'imported_heats':len(heats)}
    def insert_athlete(self,c,a):
        for k in ('id','name','country','university_id','university','gender'):
            if not isinstance(a.get(k),str) or not a[k] or len(a[k])>200:raise DomainError('Missing/oversize athlete '+k)
        if not a['country'].isalpha() or len(a['country'])!=3:raise DomainError('Three-letter country code required')
        c.execute('INSERT OR IGNORE INTO universities VALUES(?,?)',(a['university_id'],a['university']))
        if c.execute('SELECT name FROM universities WHERE id=?',(a['university_id'],)).fetchone()[0]!=a['university']:raise DomainError('University identity conflict; reconcile before import')
        prior=c.execute('SELECT * FROM athletes WHERE id=?',(a['id'],)).fetchone()
        row=(a['id'],a['name'],a['country'],a['university_id'],a['gender'])
        if prior and tuple(prior)!=row:raise DomainError('Athlete identity conflict; reconcile before import')
        c.execute('INSERT OR IGNORE INTO athletes VALUES(?,?,?,?,?)',row)
    def entries(self,c,h):
        rows=c.execute('''SELECT e.*,a.name,a.country,u.name AS university,t.name AS team_name,t.country AS team_country,t.fisu_team,
          r.ticks,r.rank,r.irm,r.qualification,r.record,r.medal,r.source AS result_source
          FROM entries e LEFT JOIN athletes a ON a.id=e.athlete_id LEFT JOIN universities u ON u.id=a.university_id
          LEFT JOIN teams t ON t.id=e.team_id LEFT JOIN results r ON r.heat_id=e.heat_id AND r.lane=e.lane WHERE e.heat_id=? ORDER BY e.lane''',(h,)).fetchall()
        out=[]
        for a in rows:
            a=dict(a)
            if a['team_id']:
                a['members']=[dict(m) for m in c.execute('SELECT rm.position,a.*,u.name AS university FROM relay_members rm JOIN athletes a ON a.id=rm.athlete_id JOIN universities u ON u.id=a.university_id WHERE rm.team_id=? ORDER BY rm.position',(a['team_id'],))]
                a['name']=a['team_name'];a['country']=a['team_country'];a['university']=a['team_name']
            a['timings']=[dict(t) for t in c.execute('SELECT kind,touch,ticks,raw_id FROM timings WHERE heat_id=? AND lane=? AND active=1 ORDER BY id',(h,a['lane']))]
            out.append(a)
        return out
    def snapshot(self):
        now=time.time()
        with self.db(False) as c:
            # Explicit read transaction gives one consistent revision across all queries.
            c.execute('BEGIN')
            meta={r['key']:r['value'] for r in c.execute('SELECT * FROM meta')}
            hs=[dict(r) for r in c.execute('SELECT h.*,e.name,e.discipline,e.gender,e.round,e.relay,s.date,s.session_start FROM heats h JOIN events e ON e.id=h.event_id JOIN sessions s ON s.id=e.session_id ORDER BY s.date,h.timing_event,h.timing_heat')]
            for h in hs:
                h['entries']=self.entries(c,h['id']);h['approvals']=[dict(r) for r in c.execute('SELECT stage,user_id,at,revision FROM approvals WHERE heat_id=? AND revoked=0',(h['id'],))]
                h['timing_age_ms']=round((now-h['last_timing'])*1000) if h['last_timing'] else None
                h['data_stale']=h['status']=='LIVE' and (h['recovery_hold'] or not h['last_timing'] or now-h['last_timing']>2)
            gateways=[{**dict(r),'connected':now-r['heartbeat']<3 and r['hardware_connected']==1} for r in c.execute('SELECT * FROM gateways')]
            clients=[{**dict(r),'online':now-r['heartbeat']<6} for r in c.execute('SELECT * FROM output_clients')]
            routes={r['output']:{**dict(r),**SCREENS[r['output']],'playlist':json.loads(r['playlist'])} for r in c.execute('SELECT * FROM routes')}
            g=dict(c.execute("SELECT * FROM graphics WHERE id='tv'").fetchone())
            for k in ('preview','program'):g[k]=json.loads(g[k]) if g[k] else None
            return {'version':'0.7.0','operator_mode':self.operator_mode,'mode':self.mode,'server_time':now,'revision':int(meta['revision']),'selected_heat':meta['selected_heat'],
              'heats':hs,'routes':routes,'graphics':g,'gateways':gateways,'outputs':clients,
              'notice':json.loads(meta['notice']) if meta.get('notice') else None,
              'production_approved':False,'hardware_verified':False,'warnings':['ENGINEERING BUILD: FIELD TEST AND FISU APPROVAL PENDING','ALGE profile must be verified against venue firmware']}
    def ingest(self,actor,batch):
        self.require(actor,'TIMING_OPERATOR')
        from alge_gateway.protocol import parse_frame
        source=batch['source'];profile=batch['profile'];frames=batch['frames'];heat_id=batch['heat_id']
        if not source or len(source)>100 or not 1<=len(frames)<=200:raise DomainError('Invalid timing batch')
        if self.mode=='VENUE' and batch.get('simulation',True):raise DomainError('Simulation cannot enter VENUE database')
        outcomes=[]
        with self.db() as c:
            h=self.heat(c,heat_id)
            if h['status']=='OFFICIAL':raise DomainError('Official heat locked; jury must reopen with evidence',409)
            for item in frames:
                seq=item['sequence'];raw=bytes.fromhex(item['hex'])
                if not isinstance(seq,int) or seq<0 or len(raw)>256:raise DomainError('Invalid sequence/frame')
                previous=c.execute('SELECT id FROM raw_messages WHERE source=? AND sequence=?',(source,seq)).fetchone()
                if previous:outcomes.append({'sequence':seq,'disposition':'DUPLICATE'});continue
                latest=c.execute('SELECT MAX(sequence) FROM raw_messages WHERE source=?',(source,)).fetchone()[0]
                reason='';parsed=None
                try:parsed=parse_frame(raw,profile)
                except (ValueError,UnicodeError) as e:reason='PARSE_REJECTED: '+str(e)
                if latest is not None and seq<=latest:reason='OUT_OF_ORDER'
                if parsed and not reason:
                    if parsed.event is not None and (parsed.event!=h['timing_event'] or parsed.heat!=h['timing_heat']):reason='EVENT_HEAT_MISMATCH'
                    if parsed.lane is not None and not c.execute('SELECT 1 FROM entries WHERE heat_id=? AND lane=?',(heat_id,parsed.lane)).fetchone():reason='UNMAPPED_LANE'
                    if parsed.kind=='RUNNING' and h['clock_ticks'] is not None and parsed.ticks<h['clock_ticks']:reason='REGRESSIVE_CLOCK'
                    if parsed.kind=='RUNNING' and h['status'] not in ('READY','LIVE'):reason='UNEXPECTED_RUNNING_STATE'
                    if parsed.kind=='START' and h['status'] not in ('READY','SCHEDULED'):reason='UNEXPECTED_START'
                    if parsed.kind in ('FINISH','SPLIT','DELETE','REACTION') and h['status'] not in ('LIVE','UNOFFICIAL','UNDER REVIEW'):reason='UNEXPECTED_TIMING_STATE'
                    if parsed.kind=='SWIMMER_ID':reason='IDENTITY_REVIEW_ONLY' # Never replace roster from a display feed.
                    if parsed.kind=='IDENTITY':reason='IDENTITY_CONFIRMED'
                    if parsed.kind in ('FINISH','SPLIT','REACTION'):
                        prior=c.execute('SELECT ticks FROM timings WHERE heat_id=? AND lane=? AND kind=? AND touch=? AND active=1 ORDER BY id DESC LIMIT 1',(heat_id,parsed.lane,parsed.kind,parsed.touch)).fetchone()
                        if prior:reason='SEMANTIC_DUPLICATE' if prior['ticks']==parsed.ticks else 'CONFLICT_REQUIRES_DELETE'
                    if parsed.kind in ('FINISH','SPLIT') and not reason:
                        last=c.execute("SELECT MAX(touch),MAX(ticks) FROM timings WHERE heat_id=? AND lane=? AND kind IN ('FINISH','SPLIT') AND active=1",(heat_id,parsed.lane)).fetchone()
                        if last[0] is not None and parsed.touch<last[0]:reason='STALE_TOUCH'
                        elif last[1] is not None and parsed.ticks<last[1]:reason='TIMING_REGRESSION'
                disposition=reason or 'ACCEPTED'
                rid=c.execute('INSERT INTO raw_messages(received,source,profile,sequence,frame_hex,parsed,disposition) VALUES(?,?,?,?,?,?,?)',(time.time(),source,profile,seq,raw.hex(),J(parsed.__dict__) if parsed else None,disposition)).lastrowid
                outcomes.append({'sequence':seq,'disposition':disposition,'raw_id':rid})
                if disposition not in ('ACCEPTED','IDENTITY_CONFIRMED'):continue
                if disposition=='IDENTITY_CONFIRMED':continue
                if parsed.kind!='RUNNING':self.invalidate(c,heat_id)
                if parsed.kind=='START':
                    c.execute("UPDATE heats SET status='LIVE',clock_ticks=0,recovery_hold=0 WHERE id=?",(heat_id,));h.update(status='LIVE',clock_ticks=0)
                elif parsed.kind=='RUNNING':
                    if h['status'] not in ('READY','LIVE'):continue
                    c.execute("UPDATE heats SET status='LIVE',clock_ticks=?,recovery_hold=0 WHERE id=?",(parsed.ticks,heat_id));h.update(status='LIVE',clock_ticks=parsed.ticks)
                else:
                    if parsed.kind=='DELETE':
                        # Deactivate only the specific touch and time; preserve other splits.
                        c.execute("UPDATE timings SET active=0 WHERE heat_id=? AND lane=? AND touch=? AND ticks=? AND kind IN ('FINISH','SPLIT','REACTION')",(heat_id,parsed.lane,parsed.touch,parsed.ticks))
                    c.execute('INSERT INTO timings(heat_id,lane,kind,touch,ticks,raw_id) VALUES(?,?,?,?,?,?)',(heat_id,parsed.lane,parsed.kind,parsed.touch,parsed.ticks,rid))
                    c.execute('DELETE FROM results WHERE heat_id=?',(heat_id,))
                    n=c.execute('SELECT COUNT(*) FROM entries WHERE heat_id=?',(heat_id,)).fetchone()[0]
                    finished=c.execute("SELECT COUNT(DISTINCT lane) FROM timings WHERE heat_id=? AND kind='FINISH' AND active=1",(heat_id,)).fetchone()[0]
                    status='UNOFFICIAL' if finished==n else 'LIVE'
                    c.execute('UPDATE heats SET status=? WHERE id=?',(status,heat_id));h['status']=status
                c.execute('UPDATE heats SET last_timing=?,revision=revision+1 WHERE id=?',(time.time(),heat_id))
            self.audit(c,actor['id'],'TIMING_BATCH',heat_id,None,outcomes,source,'Read-only timing feed; raw frames retained')
        return {'outcomes':outcomes}
    def compile_results(self,actor,heat_id,revision,reason):
        self.require(actor,'RESULTS_OPERATOR')
        with self.db() as c:
            h=self.heat(c,heat_id,revision)
            if h['status'] not in ('UNOFFICIAL','UNDER REVIEW'):raise DomainError('Complete timings required before compilation')
            lanes=[r[0] for r in c.execute('SELECT lane FROM entries WHERE heat_id=?',(heat_id,))]
            finishes=[]
            for lane in lanes:
                t=c.execute("SELECT * FROM timings WHERE heat_id=? AND lane=? AND kind='FINISH' AND active=1 ORDER BY touch DESC,id DESC LIMIT 1",(heat_id,lane)).fetchone()
                if not t:raise DomainError('Missing finish on lane '+str(lane))
                finishes.append(dict(t))
            self.invalidate(c,heat_id);c.execute('DELETE FROM results WHERE heat_id=?',(heat_id,))
            finishes.sort(key=lambda r:r['ticks']//100)
            for t in finishes:
                fisu=c.execute('SELECT t.fisu_team FROM entries e LEFT JOIN teams t ON t.id=e.team_id WHERE e.heat_id=? AND e.lane=?',(heat_id,t['lane'])).fetchone()[0]
                eligible=[x for x in finishes if not c.execute('SELECT t.fisu_team FROM entries e LEFT JOIN teams t ON t.id=e.team_id WHERE e.heat_id=? AND e.lane=?',(heat_id,x['lane'])).fetchone()[0]]
                rank=None if fisu else 1+sum(x['ticks']//100<t['ticks']//100 for x in eligible)
                c.execute('INSERT INTO results(heat_id,lane,ticks,rank,source,reason) VALUES(?,?,?,?,?,?)',(heat_id,t['lane'],t['ticks'],rank,'RAW_TIMING:'+str(t['raw_id']),reason))
            c.execute("UPDATE heats SET status='UNOFFICIAL',revision=revision+1 WHERE id=?",(heat_id,))
            self.audit(c,actor['id'],'COMPILE_UNOFFICIAL',heat_id,None,finishes,'raw timing + handbook p5 (hundredth ties)',reason)
        return {'compiled':len(finishes)}
    def workflow(self,actor,heat_id,action,revision,reason,document_ref='',authority_name=''):
        with self.db() as c:
            h=self.heat(c,heat_id,revision)
            if action=='review':
                self.require(actor,'RESULTS_OPERATOR','CHIEF_RESULTS_OFFICER')
                if h['status']!='UNOFFICIAL':raise DomainError('UNOFFICIAL required')
                n=c.execute('SELECT COUNT(*) FROM entries WHERE heat_id=?',(heat_id,)).fetchone()[0]
                if c.execute('SELECT COUNT(*) FROM results WHERE heat_id=?',(heat_id,)).fetchone()[0]!=n:raise DomainError('Compile a complete result first')
                c.execute("UPDATE heats SET status='UNDER REVIEW',revision=revision+1 WHERE id=?",(heat_id,))
            elif action in ('endorse','approve'):
                if self.operator_mode=='SINGLE':
                    if not document_ref.strip() or not 3<=len(authority_name.strip())<=200:raise DomainError('Named external Chief/Jury authority and approval document reference required')
                    reason=reason+' | EXTERNAL AUTHORITY: '+authority_name.strip()+' | DOCUMENT: '+document_ref.strip()
                self.require(actor,'CHIEF_RESULTS_OFFICER' if action=='endorse' else 'JURY_APPROVER')
                if h['status']!='UNDER REVIEW':raise DomainError('UNDER REVIEW required')
                if action=='approve':
                    chief=c.execute("SELECT * FROM approvals WHERE heat_id=? AND revision=? AND stage='CHIEF' AND revoked=0",(heat_id,revision)).fetchone()
                    if not chief or (chief['user_id']==actor['id'] and self.operator_mode!='SINGLE'):raise DomainError('Separate Chief endorsement of this exact revision required')
                    if not document_ref:raise DomainError('Jury approval document/reference required')
                    c.execute('INSERT INTO jury_decisions(heat_id,user_id,at,reason,document_ref) VALUES(?,?,?,?,?)',(heat_id,actor['id'],time.time(),reason,document_ref))
                    c.execute("UPDATE heats SET status='OFFICIAL' WHERE id=?",(heat_id,))
                stage='CHIEF' if action=='endorse' else 'JURY'
                if c.execute('SELECT 1 FROM approvals WHERE heat_id=? AND revision=? AND stage=? AND revoked=0',(heat_id,revision,stage)).fetchone():raise DomainError('Already signed')
                c.execute('INSERT INTO approvals(heat_id,revision,stage,user_id,at,reason) VALUES(?,?,?,?,?,?)',(heat_id,revision,stage,actor['id'],time.time(),reason))
            elif action=='reopen':
                self.require(actor,'JURY_APPROVER')
                if h['status']!='OFFICIAL' or not document_ref:raise DomainError('Official heat and jury document reference required')
                self.invalidate(c,heat_id);c.execute("UPDATE heats SET status='UNDER REVIEW',revision=revision+1 WHERE id=?",(heat_id,))
                c.execute('INSERT INTO jury_decisions(heat_id,user_id,at,reason,document_ref) VALUES(?,?,?,?,?)',(heat_id,actor['id'],time.time(),reason,document_ref))
            elif action=='swimoff':
                self.require(actor,'JURY_APPROVER')
                if h['status']!='UNDER REVIEW' or not document_ref:raise DomainError('Review and jury document required')
                self.invalidate(c,heat_id);c.execute("UPDATE heats SET status='SWIM-OFF REQUIRED',revision=revision+1 WHERE id=?",(heat_id,))
            elif action=='resume_review':
                self.require(actor,'JURY_APPROVER')
                if h['status']!='SWIM-OFF REQUIRED' or not document_ref:raise DomainError('Swim-off decision reference required')
                c.execute("UPDATE heats SET status='UNDER REVIEW',revision=revision+1 WHERE id=?",(heat_id,))
            else:raise DomainError('Unknown workflow action')
            self.audit(c,actor['id'],action.upper(),heat_id,h,self.heat(c,heat_id),'authenticated results workflow',reason)
        return {'status':self.snapshot()['heats'][next(i for i,h in enumerate(self.snapshot()['heats']) if h['id']==heat_id)]['status']}
    def correction(self,actor,heat_id,payload):
        self.require(actor,'JURY_APPROVER')
        if not payload.get('document_ref') or not payload.get('source') or not payload.get('reason'):raise DomainError('Approved evidence, source and reason required')
        with self.db() as c:
            h=self.heat(c,heat_id,payload['revision'])
            if h['status']!='UNDER REVIEW':raise DomainError('Reopen to UNDER REVIEW before correcting')
            row=c.execute('SELECT * FROM results WHERE heat_id=? AND lane=?',(heat_id,payload['lane'])).fetchone()
            if not row:raise DomainError('Result lane missing')
            old=dict(row);fields={k:payload[k] for k in ('ticks','rank','qualification','record','medal','irm') if k in payload}
            if 'ticks' in fields and (not isinstance(fields['ticks'],int) or not 0<=fields['ticks']<3600000000):raise DomainError('Invalid integer timing ticks')
            if 'rank' in fields and fields['rank'] is not None and (not isinstance(fields['rank'],int) or not 1<=fields['rank']<=12):raise DomainError('Invalid rank')
            if fields.get('irm'):
                allowed=json.loads((ROOT/'deployment/approved_rule_codes.json').read_text())
                if fields['irm'] not in allowed['codes'] or not allowed['approval_ref']:raise DomainError('IRM code not approved in configured technical rules')
            fisu=c.execute('SELECT t.fisu_team FROM entries e LEFT JOIN teams t ON t.id=e.team_id WHERE e.heat_id=? AND e.lane=?',(heat_id,payload['lane'])).fetchone()[0]
            if fisu and any(fields.get(k) for k in ('rank','qualification','record','medal')):raise DomainError('FISU Teams excluded from final standings and medals (Handbook p6)')
            if fields.get('medal') not in (None,'','GOLD','SILVER','BRONZE'):raise DomainError('Invalid medal')
            if not fields:raise DomainError('No correction fields')
            self.invalidate(c,heat_id)
            for k,v in fields.items():c.execute(f'UPDATE results SET {k}=?,source=?,reason=? WHERE heat_id=? AND lane=?',(v,payload['source'],payload['reason'],heat_id,payload['lane']))
            c.execute('UPDATE heats SET revision=revision+1 WHERE id=?',(heat_id,))
            c.execute('INSERT INTO jury_decisions(heat_id,user_id,at,reason,document_ref) VALUES(?,?,?,?,?)',(heat_id,actor['id'],time.time(),payload['reason'],payload['document_ref']))
            self.audit(c,actor['id'],'JURY_CORRECTION',heat_id,old,{**old,**fields},payload['source'],payload['reason'])
        return {'corrected':True}
