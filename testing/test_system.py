import copy,json,sqlite3,time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from results_backend.app import create_app
from results_backend.store import Store,DomainError,ROOT,ROLES
from alge_gateway.protocol import parse_frame,FrameBuffer,ticks_from_clock

@pytest.fixture
def system(tmp_path):
 s=Store(tmp_path/'test.sqlite3')
 fixture=json.loads((ROOT/'testing/fixtures/meet.json').read_text())
 s.import_meet({'id':'bootstrap','role':'SYSTEM_ADMINISTRATOR'},fixture)
 actors={}
 for role in ROLES:
  s.create_user(role,role,'TEST_password_12345');actors[role]={'id':role,'role':role}
 return s,actors

def heat(s,h='TEST-IND-1'):return next(x for x in s.snapshot()['heats'] if x['id']==h)
def ingest(s,a,frames,source='TEST',seq=1,h='TEST-IND-1'):
 return s.ingest(a['TIMING_OPERATOR'],{'source':source,'profile':'tm-swim-video-modern-v1','heat_id':h,'simulation':True,'frames':[{'sequence':i+seq,'hex':v.encode().hex()} for i,v in enumerate(frames)]})
def finish(s,a,h='TEST-IND-1',tie=False):
 n=8 if h=='TEST-IND-1' else 2;ev=1 if n==8 else 2
 ingest(s,a,['START',f'R{ev:03}001 00:00:42.0000']+[f'I{i:02}00100:00:20.0000' for i in range(1,n+1)]+[f'F{i:02}00200:00:{43 if tie and i<3 else 42+i:02}.1200' for i in range(1,n+1)],source=h,h=h)
 s.compile_results(a['RESULTS_OPERATOR'],h,heat(s,h)['revision'],'Compile synthetic timing')
def review(s,a,h='TEST-IND-1'):
 s.workflow(a['RESULTS_OPERATOR'],h,'review',heat(s,h)['revision'],'Technical review')
def approve(s,a,h='TEST-IND-1'):
 s.workflow(a['CHIEF_RESULTS_OFFICER'],h,'endorse',heat(s,h)['revision'],'Checked roster and timing')
 s.workflow(a['JURY_APPROVER'],h,'approve',heat(s,h)['revision'],'Jury signed synthetic result','TEST-DOC-1')

@pytest.mark.parametrize('value,ticks',[('00:00:43.1234',431234),('01:02:03.4',37234000),('00:00:00.0000',0)])
def test_clock_exact(value,ticks):assert ticks_from_clock(value)==ticks
@pytest.mark.parametrize('frame,kind',[('START','START'),('R001002 00:00:13.1000','RUNNING'),('I0100200:00:20.1234','SPLIT'),('F1200200:00:42.9999','FINISH'),('C0100200:00:42.9999','DELETE'),('ID1/2/100m SF/MEN','IDENTITY'),('4:TEST ATHLETE/EGY/TEST UNIVERSITY','SWIMMER_ID')])
def test_document_reconstructed_frames(frame,kind):assert parse_frame(frame.encode()).kind==kind
@pytest.mark.parametrize('frame',[b'garbage',b'R001001 00:99:00.0000',b'F1300100:00:10.0000',b'X'*65,b'\xff'])
def test_reject_invalid_protocol(frame):
 with pytest.raises((ValueError,UnicodeError)):parse_frame(frame)
def test_legacy_modern_separation():
 raw=b'F010020100:00:43.1234'
 assert parse_frame(raw,'tm-swim-video-legacy-v1').rank==1
 with pytest.raises(ValueError):parse_frame(raw,'tm-swim-video-modern-v1')
def test_reaction_blank_columns_from_manual():
 e=parse_frame(b'M01001  00:00:00.1234');assert e.kind=='REACTION';assert e.ticks==1234
def test_old_touch_and_regressive_split_quarantine(system):
 s,a=system;r=ingest(s,a,['START','I0100200:00:20.0000','I0100100:00:10.0000','I0100300:00:19.0000'])['outcomes']
 assert r[2]['disposition']=='STALE_TOUCH';assert r[3]['disposition']=='TIMING_REGRESSION'
def test_fragmentation_and_resynchronisation():
 b=FrameBuffer();assert not b.feed(b'STA');assert b.feed(b'RT\r\n')==[b'START'];assert b.feed(b'x'*90+b'\rSTART\r')==[b'START'];assert b.rejected==1

def test_auth_and_api_permissions(system):
 s,a=system;app=create_app(s.path,'TEST');c=TestClient(app)
 assert c.get('/api/health').status_code==200
 assert c.post('/api/select',json={'heat_id':'TEST-IND-1','reason':'test'}).status_code==401
 assert c.post('/api/login',json={'user':'none','password':'bad'}).status_code==401
 token=c.post('/api/login',json={'user':'BROADCAST_OPERATOR','password':'TEST_password_12345'}).json()['token'];headers={'Authorization':'Bearer '+token}
 assert c.post('/api/select',headers=headers,json={'heat_id':'TEST-IND-1','reason':'test'}).status_code==403
 assert c.get('/api/audit',headers=headers).status_code==403
 assert c.post('/api/graphics',headers=headers,json={'action':'take','reason':'Take test'}).status_code==400
 assert c.post('/api/logout',headers=headers,json={}).status_code==200
 assert c.get('/api/me',headers=headers).status_code==401

def test_cross_origin_denied(system):
 s,a=system;c=TestClient(create_app(s.path))
 assert c.post('/api/login',headers={'Origin':'https://attacker.example'},json={}).status_code==403

def test_static_secrets_not_served(system):
 s,a=system;c=TestClient(create_app(s.path))
 for url in ['/runtime/test.sqlite3','/runtime/TEST_OPERATOR_CREDENTIALS.txt','/results_backend/store.py','/backups/foo.sqlite3']:
  assert c.get(url).status_code==404

def test_complete_workflow_and_publish_gate(system):
 s,a=system;finish(s,a);assert heat(s)['status']=='UNOFFICIAL';review(s,a)
 with pytest.raises(DomainError):s.workflow(a['JURY_APPROVER'],'TEST-IND-1','approve',heat(s)['revision'],'Test approval','TEST-DOC')
 approve(s,a);h=heat(s);assert h['status']=='OFFICIAL';assert len(h['approvals'])==2
 with pytest.raises(DomainError):ingest(s,a,['F0100200:00:40.0000'],'late')

def test_ties_are_equal_no_automatic_qualifier_or_medal(system):
 s,a=system;finish(s,a,tie=True);e=heat(s)['entries'];assert e[0]['rank']==e[1]['rank']==1;assert e[2]['rank']==3
 assert all(not x['qualification'] and not x['record'] and not x['medal'] for x in e)

def test_revision_conflicts(system):
 s,a=system;finish(s,a)
 with pytest.raises(DomainError) as e:s.workflow(a['RESULTS_OPERATOR'],'TEST-IND-1','review',0,'Stale request')
 assert e.value.status==409

def test_graphics_cannot_correct_time(system):
 s,a=system;finish(s,a);review(s,a)
 with pytest.raises(DomainError) as e:s.correction(a['BROADCAST_OPERATOR'],'TEST-IND-1',{'revision':heat(s)['revision'],'lane':1,'ticks':100,'document_ref':'X','source':'X','reason':'X'})
 assert e.value.status==403

def test_correction_invalidates_signatures_and_preserves_raw(system):
 s,a=system;finish(s,a);review(s,a);approve(s,a);old=heat(s)['entries'][0]['timings'];s.workflow(a['JURY_APPROVER'],'TEST-IND-1','reopen',heat(s)['revision'],'Documented reopen','TEST-REOPEN')
 s.workflow(a['CHIEF_RESULTS_OFFICER'],'TEST-IND-1','endorse',heat(s)['revision'],'Synthetic endorsement')
 s.correction(a['JURY_APPROVER'],'TEST-IND-1',{'revision':heat(s)['revision'],'lane':1,'ticks':431199,'document_ref':'TEST-CORRECTION','source':'Signed backup timing','reason':'Synthetic jury correction'})
 h=heat(s);assert h['approvals']==[];assert h['published']==0;assert h['entries'][0]['timings']==old;assert h['entries'][0]['ticks']==431199

def test_unapproved_irm_rejected(system):
 s,a=system;finish(s,a);review(s,a)
 with pytest.raises(DomainError):s.correction(a['JURY_APPROVER'],'TEST-IND-1',{'revision':heat(s)['revision'],'lane':1,'irm':'DQ','document_ref':'TEST','source':'TEST','reason':'TEST'})

def test_dedup_out_of_order_and_wrong_heat(system):
 s,a=system;assert ingest(s,a,['START'])['outcomes'][0]['disposition']=='ACCEPTED'
 assert ingest(s,a,['START'])['outcomes'][0]['disposition']=='DUPLICATE'
 assert ingest(s,a,['R001001 00:00:11.0000'],seq=3)['outcomes'][0]['disposition']=='ACCEPTED'
 assert ingest(s,a,['R001001 00:00:12.0000'],seq=2)['outcomes'][0]['disposition']=='OUT_OF_ORDER'
 assert ingest(s,a,['R002001 00:00:12.0000'],seq=4)['outcomes'][0]['disposition']=='EVENT_HEAT_MISMATCH'
 assert ingest(s,a,['R001001 00:00:10.0000'],seq=5)['outcomes'][0]['disposition']=='REGRESSIVE_CLOCK'
 assert heat(s)['clock_ticks']==110000

def test_unmapped_lane_and_identity_quarantine(system):
 s,a=system;res=ingest(s,a,['START','F0900100:00:43.0000','1:REPLACEMENT NAME/EGY/OTHER UNIVERSITY'])['outcomes']
 assert res[1]['disposition']=='UNMAPPED_LANE';assert res[2]['disposition']=='IDENTITY_REVIEW_ONLY';assert heat(s)['entries'][0]['name']=='TEST ATHLETE 01'

def test_delete_correction_protocol(system):
 s,a=system;ingest(s,a,['START','F0100200:00:43.0000','F0100200:00:42.0000','C0100200:00:43.0000','F0100200:00:42.0000'])
 t=heat(s)['entries'][0]['timings'];assert [x['ticks'] for x in t if x['kind']=='FINISH']==[420000]
 with s.db(False) as c:assert c.execute('SELECT COUNT(*) FROM raw_messages').fetchone()[0]==5

def test_incomplete_results_do_not_approve(system):
 s,a=system;ingest(s,a,['START','F0100200:00:43.0000'])
 with pytest.raises(DomainError):s.compile_results(a['RESULTS_OPERATOR'],'TEST-IND-1',heat(s)['revision'],'Incomplete')

def test_restart_freezes_live(system):
 s,a=system;ingest(s,a,['START','R001001 00:00:20.0000']);assert not heat(s)['data_stale']
 reopened=Store(s.path);assert heat(reopened)['data_stale'];assert heat(reopened)['clock_ticks']==200000
 ingest(reopened,a,['R001001 00:00:21.0000'],source='reconnected');assert not heat(reopened)['data_stale']

def test_feed_timeout(system):
 s,a=system;ingest(s,a,['START']);
 with s.db() as c:c.execute('UPDATE heats SET last_timing=?',(time.time()-5,))
 assert heat(s)['data_stale']

def test_test_venue_isolation(tmp_path):
 s=Store(tmp_path/'test.sqlite3','TEST')
 with pytest.raises(ValueError):Store(s.path,'VENUE')
 v=Store(tmp_path/'venue.sqlite3','VENUE')
 with pytest.raises(DomainError):v.import_meet({'id':'x','role':'SYSTEM_ADMINISTRATOR'},json.loads((ROOT/'testing/fixtures/meet.json').read_text()))

def test_relay_order_and_fisu_team_exclusion(system,tmp_path):
 s,a=system;finish(s,a,'TEST-RELAY-1');assert heat(s,'TEST-RELAY-1')['entries'][1]['rank'] is None
 review(s,a,'TEST-RELAY-1');h=heat(s,'TEST-RELAY-1')
 with pytest.raises(DomainError):s.correction(a['JURY_APPROVER'],h['id'],{'revision':h['revision'],'lane':2,'medal':'GOLD','document_ref':'TEST','source':'TEST','reason':'TEST'})
 f=json.loads((ROOT/'testing/fixtures/meet.json').read_text());f['heats']=f['heats'][1:];f['heats'][0]['entries'][0]['team']['members'][0]['gender']='WOMEN'
 n=Store(tmp_path/'relay.sqlite3')
 with pytest.raises(DomainError):n.import_meet({'id':'x','role':'SYSTEM_ADMINISTRATOR'},f)
 assert n.snapshot()['heats']==[]

def test_native_screen_pixel_total(system):
 s,a=system;r=s.snapshot()['routes'];assert len(r)==6;assert sum(x['width']*x['height'] for x in r.values())==7569408

def test_api_routes_blackout_and_official_label_gate(system):
 s,a=system;c=TestClient(create_app(s.path));tokens={}
 for u in ['LED_OPERATOR','BROADCAST_OPERATOR']:
  tokens[u]={'Authorization':'Bearer '+c.post('/api/login',json={'user':u,'password':'TEST_password_12345'}).json()['token']}
 r=c.post('/api/routes',headers=tokens['LED_OPERATOR'],json={'outputs':['l1','master'],'content':'live','heat_id':'TEST-IND-1','safe':24,'reason':'Route test'})
 assert r.status_code==200
 assert c.post('/api/blackout',headers=tokens['LED_OPERATOR'],json={'outputs':['l1'],'enabled':True,'reason':'Blackout test'}).status_code==200
 assert s.snapshot()['routes']['l1']['blackout']==1
 assert c.post('/api/graphics',headers=tokens['BROADCAST_OPERATOR'],json={'action':'preview','template':'SFS302A','heat_id':'TEST-IND-1','result_label':'OFFICIAL','reason':'Test'}).status_code==400

def test_live_program_survives_clock_updates(system):
 s,a=system
 with s.db() as c:c.execute("UPDATE graphics SET program=? WHERE id='tv'",(json.dumps({'template':'SFS500','heat_id':'TEST-IND-1'}),))
 ingest(s,a,['START','R001001 00:00:20.0000']);assert s.snapshot()['graphics']['program']['template']=='SFS500'

def test_audit_and_backup_api(system):
 s,a=system;c=TestClient(create_app(s.path));token=c.post('/api/login',json={'user':'SYSTEM_ADMINISTRATOR','password':'TEST_password_12345'}).json()['token'];h={'Authorization':'Bearer '+token}
 r=c.post('/api/backup',headers=h,json={'reason':'Synthetic backup test'});assert r.status_code==200
 path=ROOT/'backups'/r.json()['backup']
 try:
  with sqlite3.connect(path) as b:assert b.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 finally:path.unlink()
 assert any(x['action']=='BACKUP' for x in c.get('/api/audit',headers=h).json())

def test_websocket_snapshot(system):
 s,a=system
 with TestClient(create_app(s.path)) as c:
  with c.websocket_connect('/ws') as ws:
   d=ws.receive_json();assert d['mode']=='TEST';assert len(d['routes'])==6

def test_publication_api_requires_official(system):
 s,a=system;c=TestClient(create_app(s.path));token=c.post('/api/login',json={'user':'RESULTS_OPERATOR','password':'TEST_password_12345'}).json()['token']
 assert c.post('/api/results/TEST-IND-1/publication',headers={'Authorization':'Bearer '+token},json={'revision':0,'publish':True,'reason':'Try premature publication'}).status_code==400
 assert c.get('/api/public/results').json()['heats']==[]

def test_venue_take_rejects_unapproved_template(tmp_path):
 s=Store(tmp_path/'venue.sqlite3','VENUE');fixture=json.loads((ROOT/'testing/fixtures/meet.json').read_text());fixture['data_mode']='VENUE'
 s.import_meet({'id':'bootstrap','role':'SYSTEM_ADMINISTRATOR'},fixture);s.create_user('broadcast','BROADCAST_OPERATOR','TEST_password_12345');c=TestClient(create_app(s.path,'VENUE'))
 token=c.post('/api/login',json={'user':'broadcast','password':'TEST_password_12345'}).json()['token'];h={'Authorization':'Bearer '+token}
 assert c.post('/api/graphics',headers=h,json={'action':'preview','template':'SFS206','heat_id':'TEST-IND-1','reason':'Venue engineering preview'}).status_code==200
 assert c.post('/api/graphics',headers=h,json={'action':'take','reason':'Try unapproved take'}).status_code==409

def test_restore_cli_revokes_sessions_blacks_outputs_and_holds(system,tmp_path):
 import subprocess,sys
 s,a=system;ingest(s,a,['START','R001001 00:00:12.0000']);token=s.login('LED_OPERATOR','TEST_password_12345')['token']
 backup=tmp_path/'backup.sqlite3'
 with s.db(False) as c:
  with sqlite3.connect(backup) as d:c.backup(d)
 dest=tmp_path/'restored.sqlite3';result=subprocess.run([sys.executable,'-m','results_backend.cli','--db',str(dest),'restore',str(backup),'--confirm-stopped'],cwd=ROOT,capture_output=True,text=True)
 assert result.returncode==0,result.stderr
 restored=Store(dest);snap=restored.snapshot();assert all(r['blackout'] for r in snap['routes'].values());assert snap['graphics']['program'] is None;assert heat(restored)['data_stale']
 with pytest.raises(DomainError):restored.identity(token)

def test_health_does_not_publish_implausible_rss(system):
 s,a=system;h=TestClient(create_app(s.path)).get('/api/health').json();assert h['rss_mb'] is None or h['rss_mb']>=8
