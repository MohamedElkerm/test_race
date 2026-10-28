import json,socket,threading,time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from results_backend.store import Store,ROOT,DomainError
from results_backend.app import create_app
from alge_gateway.gen_inspector import inspect_text
from alge_gateway.record_udp import record
from testing.test_system import finish,heat

@pytest.fixture
def single(tmp_path,monkeypatch):
    monkeypatch.setenv('FINS_OPERATOR_MODE','SINGLE')
    s=Store(tmp_path/'single.sqlite3')
    s.create_user('operator','SINGLE_OPERATOR','TEST_password_12345')
    a={'id':'operator','role':'SINGLE_OPERATOR'}
    s.import_meet(a,json.loads((ROOT/'testing/fixtures/meet.json').read_text()))
    c=TestClient(create_app(s.path,'TEST'))
    token=c.post('/api/login',json={'user':'operator','password':'TEST_password_12345'}).json()['token']
    return s,a,c,{'Authorization':'Bearer '+token}

def test_single_account_controls_and_authentication(single):
    s,a,c,h=single
    assert c.get('/api/health').json()['operator_mode']=='SINGLE'
    assert c.post('/api/select',json={'heat_id':'TEST-IND-1','reason':'test'}).status_code==401
    s.create_user('legacy','LED_OPERATOR','TEST_password_12345')
    assert c.post('/api/login',json={'user':'legacy','password':'TEST_password_12345'}).status_code==403
    assert c.post('/api/select',headers=h,json={'heat_id':'TEST-IND-1','reason':'single account selection'}).status_code==200
    assert c.post('/api/routes',headers=h,json={'outputs':['master'],'content':'startlist','heat_id':'TEST-IND-1','safe':24,'reason':'single LED routing'}).status_code==200
    assert c.post('/api/graphics',headers=h,json={'action':'preview','template':'SFS206','heat_id':'TEST-IND-1','reason':'single preview'}).status_code==200
    assert c.post('/api/graphics',headers=h,json={'action':'take','reason':'single take'}).status_code==200
    assert c.get('/api/audit',headers=h).status_code==200

def test_single_approval_requires_external_evidence(single):
    s,a,c,headers=single
    finish(s,{'TIMING_OPERATOR':a,'RESULTS_OPERATOR':a})
    def workflow(action,**extra):return c.post('/api/results/TEST-IND-1/workflow',headers=headers,json={'action':action,'revision':heat(s)['revision'],'reason':'TEST workflow recording',**extra})
    assert workflow('review').status_code==200
    assert workflow('endorse').status_code==400
    assert workflow('endorse',document_ref='TEST-DOC',authority_name='TEST Chief').status_code==200
    assert workflow('approve',document_ref='TEST-DOC').status_code==400
    assert heat(s)['status']=='UNDER REVIEW'
    assert workflow('approve',document_ref='TEST-JURY-DOC',authority_name='TEST Jury').status_code==200
    assert heat(s)['status']=='OFFICIAL'
    logs=c.get('/api/audit',headers=headers).json()
    assert any('TEST Jury' in x['reason'] and 'TEST-JURY-DOC' in x['reason'] for x in logs)
    assert all(x['user_id']=='operator' for x in logs if x['action'] in ('ENDORSE','APPROVE'))

@pytest.mark.parametrize('name,count',[('001-001-12P0001.gen',0),('001-029-01P0001.gen',8),('001-029-01P0002.gen',7),('001-029-02P0001.gen',5),('001-029-03P0001.gen',5)])
def test_five_real_samples_are_only_inspected(single,name,count):
    s,a,c,h=single
    p=ROOT/'testing/fixtures/gen_samples'/name
    before=heat(s)['entries'];r=c.post('/api/integration/gen/inspect',headers=h,json={'filename':name,'text':p.read_bytes().decode()})
    assert r.status_code==200;out=r.json()
    assert out['rows_with_time_like_values']==count
    assert len(out['rows'])==12 and out['adopted_as_results'] is False
    assert out['header_fields'][6]=='2.4.10.1' and heat(s)['entries']==before

def test_inspector_rejects_unrecognised_or_malformed_inputs():
    for text,name in [('x','x.gen'),('29;1;1;P;0;Alge-Timing;9.9\n0;;;;;','x.gen'),('29;1;1;P;0;Alge-Timing;2.4.10.1\n0;;;;','x.gen'),('x','../x.gen')]:
        with pytest.raises(DomainError):inspect_text(text,name)

def test_raw_udp_logger_retains_exact_bytes(tmp_path):
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as pick:pick.bind(('127.0.0.1',0));port=pick.getsockname()[1]
    output=tmp_path/'udp.jsonl';result=[]
    thread=threading.Thread(target=lambda:result.append(record(port,1,output,'127.0.0.1')));thread.start()
    for _ in range(100):
        if output.exists():break
        time.sleep(.01)
    raw=b'\x00TEST-UDP\xff\r\n'
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:sender.sendto(raw,('127.0.0.1',port))
    thread.join(3);assert not thread.is_alive() and result==[1]
    records=[json.loads(x) for x in output.read_text().splitlines()];assert bytes.fromhex(records[1]['hex'])==raw
    assert records[-1]['datagrams']==1 and records[0]['hardware_verified'] is False

def test_windows_launcher_env_names():
    for mode in ('TEST','VENUE'):
        text=(ROOT/f'RUN_SINGLE_{mode}_LAN.cmd').read_text()
        assert 'FINS_OPERATOR_MODE=SINGLE' in text and f'FINS_MODE={mode}' in text
        assert f'runtime\\single_{mode.lower()}.sqlite3' in text
        assert '--host 0.0.0.0' in text
