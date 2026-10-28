import hashlib
import json
from pathlib import Path
import shutil
import socket
import time

import pytest
from fastapi.testclient import TestClient
from results_backend.app import create_app
from results_backend.store import ROOT
from alge_gateway.swimtime_network import FeedState, SwimTimeNetwork, CAPTURE, CAPTURE_SHA256, display_ticks

EXPECTED = {10:'0:53.14',9:'0:54.95',8:'0:55.90',7:'0:56.61',6:'0:57.53',5:'0:58.15',4:'0:58.84',3:'0:59.51',2:'1:00.69',1:'1:02.00'}


def frame(kind='RunningTime', value=531404, channel=1, lap=1):
    return f'Time\t{channel}\t{kind}\t{value}\tRank\t1\tLap\t{lap}\tPoints\t50.00\r'.encode()


def fixture_rows():
    p = ROOT/'evidence/swimtime'/CAPTURE
    assert hashlib.sha256(p.read_bytes()).hexdigest() == CAPTURE_SHA256
    return [json.loads(x) for x in p.read_text().splitlines() if '"hex"' in x]


def test_recorded_capture_matches_ten_source_screen_values():
    s = FeedState('10.227.186.112')
    rows = fixture_rows()
    for r in rows:
        assert s.consume(bytes.fromhex(r['hex']), (r['sender_ip'],r['sender_port']),r['received_at_unix'])['accepted']
    snap = s.snapshot(rows[-1]['received_at_unix'], replay=True)
    assert snap['counts']['datagrams'] == snap['counts']['accepted'] == 2754
    assert snap['counts']['LaneTime'] == 24
    assert {r['channel']:r['display_time'] for r in snap['channels']} == EXPECTED
    assert all(r['source_lap']=='1' for r in snap['channels'])
    assert snap['clock_display'] is None and snap['clock_code'] == -1
    assert not any(snap[k] for k in ('hardware_verified','official_result','results_written','finish_detection_verified','channel_lane_mapping_verified'))


def test_truncation_and_negative_codes_never_become_times_or_decisions():
    assert display_ticks(531404) == '0:53.14'
    assert display_ticks(9999) == '0:00.99'
    assert display_ticks(600000) == '1:00.00'
    for value in (-1,-3,-4):
        s = FeedState('127.0.0.1')
        s.consume(frame('LaneTime',value),('127.0.0.1',9),100)
        row = s.snapshot(100,listening=True)['channels'][0]
        assert row['raw_value'] == value and row['display_time'] is None
        assert row['meaning'] == 'UNINTERPRETED NEGATIVE CODE'


def test_clock_stale_idle_ready_and_stopped_are_suppressed():
    s = FeedState('127.0.0.1')
    s.consume(frame(),('127.0.0.1',9),100)
    assert s.snapshot(100,listening=True)['clock_display'] == '0:53.14'
    assert s.snapshot(102.1,listening=True)['clock_display'] is None
    assert s.snapshot(103.1,listening=True)['state'] == 'STALE / DATA LOST'
    assert s.snapshot(100,listening=False)['clock_display'] is None
    s.consume(frame(value=-1),('127.0.0.1',9),104)
    assert s.snapshot(104,listening=True)['clock_display'] is None
    s.consume(frame(),('127.0.0.1',9),105)
    s.consume(frame('Ready',0),('127.0.0.1',9),105.1)
    assert s.snapshot(105.1,listening=True)['clock_display'] is None


def test_source_pin_malformed_frame_and_repeat_content():
    s = FeedState('127.0.0.1')
    assert not s.consume(frame(),('127.0.0.2',9),100)['accepted']
    assert not s.consume(b'not a SwimTime frame',('127.0.0.1',9),100)['accepted']
    first = s.consume(frame(),('127.0.0.1',9),101)
    second = s.consume(frame(),('127.0.0.1',9),102)
    assert not first['duplicate_payload_within_2s'] and second['duplicate_payload_within_2s']
    assert s.snapshot(104,listening=True)['receiving']
    assert s.raw.counts['other_source'] == s.raw.counts['unparsed'] == 1


def test_repeated_identical_clock_is_not_kept_live_indefinitely():
    s=FeedState('127.0.0.1')
    for at in (100,101,102,103):s.consume(frame(),('127.0.0.1',9),at)
    snap=s.snapshot(103,listening=True)
    assert snap['receiving'] and snap['clock_display'] is None
    s.consume(frame(value=532404),('127.0.0.1',9),104)
    assert s.snapshot(104,listening=True)['clock_display']=='0:53.24'


def test_unknown_layout_cannot_restore_clock_until_supported_layout():
    s = FeedState('127.0.0.1')
    s.consume(frame(),('127.0.0.1',9),100)
    assert not s.consume(b'Layout\tRankOriented',('127.0.0.1',9),101)['accepted']
    s.consume(frame(value=600000),('127.0.0.1',9),102)
    assert s.snapshot(102,listening=True)['clock_display'] is None
    assert s.snapshot(102,listening=True)['warning']
    s.consume(b'Layout\tLaneOriented',('127.0.0.1',9),103)
    s.consume(frame(value=700000),('127.0.0.1',9),104)
    assert s.snapshot(104,listening=True)['clock_display'] == '1:10.00'


def test_unannounced_clock_regression_is_held_with_raw_data_retained():
    s = FeedState('127.0.0.1')
    s.consume(frame(value=100000),('127.0.0.1',9),100)
    row = s.consume(frame(value=50000),('127.0.0.1',9),101)
    assert row['accepted'] and bytes.fromhex(row['hex']) == frame(value=50000)
    assert s.snapshot(101,listening=True)['clock_display'] is None
    assert s.snapshot(101,listening=True)['warning']
    s.consume(frame('Ready',0),('127.0.0.1',9),102)
    s.consume(frame(value=60000),('127.0.0.1',9),103)
    assert s.snapshot(103,listening=True)['clock_display'] == '0:06.00'


@pytest.fixture
def api(tmp_path,monkeypatch):
    monkeypatch.setenv('FINS_OPERATOR_MODE','SINGLE')
    app=create_app(tmp_path/'test.sqlite3','TEST')
    app.state.swimtime.root=tmp_path
    evidence=tmp_path/'evidence/swimtime';evidence.mkdir(parents=True)
    shutil.copy2(ROOT/'evidence/swimtime'/CAPTURE,evidence/CAPTURE)
    store=app.state.store
    store.create_user('operator','SINGLE_OPERATOR','TEST_password_12345')
    store.import_meet({'id':'operator','role':'SINGLE_OPERATOR'},json.loads((ROOT/'testing/fixtures/meet.json').read_text()))
    with TestClient(app) as client:
        token=client.post('/api/login',json={'user':'operator','password':'TEST_password_12345'}).json()['token']
        yield app,client,{'Authorization':'Bearer '+token},tmp_path


def tables(store):
    with store.db(False) as c:
        return {t:[tuple(row) for row in c.execute('SELECT * FROM '+t)] for t in ('heats','entries','timings','results','approvals','graphics','routes')}


def wait_state(client,predicate):
    for _ in range(100):
        s=client.get('/api/swimtime').json()
        if predicate(s):return s
        time.sleep(.01)
    raise AssertionError('Timed out waiting for UDP delivery to the API')


def test_real_udp_api_websocket_raw_log_and_results_boundary(api):
    app,c,auth,tmp=api
    before=tables(app.state.store)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as pick:
        pick.bind(('127.0.0.1',0));port=pick.getsockname()[1]
    assert c.post('/api/swimtime/start',json={'source_ip':'127.0.0.1','port':port}).status_code==401
    assert c.post('/api/swimtime/start',headers=auth,json={'source_ip':'127.0.0.1','port':port}).status_code==200
    raw=frame()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
        sender.sendto(raw,('127.0.0.1',port))
        sender.sendto(frame('LaneTime'),('127.0.0.1',port))
    s=wait_state(c,lambda s:s['counts'].get('accepted',0)==2)
    assert s['clock_display']=='0:53.14' and s['channels'][0]['display_time']=='0:53.14'
    with c.websocket_connect('/ws') as ws:
        msg=ws.receive_json()
        assert msg['swimtime']['receiving'] and msg['swimtime']['channels'][0]['raw_value']==531404
    assert c.post('/api/swimtime/replay',headers=auth,json={}).status_code==409
    assert c.post('/api/swimtime/stop',headers=auth,json={}).status_code==200
    assert c.get('/api/swimtime').json()['clock_display'] is None
    lines=[json.loads(x) for p in (tmp/'runtime/swimtime').glob('*.jsonl') for x in p.read_text().splitlines()]
    assert any(r.get('hex')==raw.hex() for r in lines)
    assert lines[-1]['type']=='summary'
    assert tables(app.state.store)==before


def test_recorded_replay_does_not_publish_or_change_competition(api):
    app,c,auth,_=api
    before=tables(app.state.store)
    r=c.post('/api/swimtime/replay',headers=auth,json={})
    assert r.status_code==200
    s=r.json()
    assert s['replay'] and not s['receiving'] and not s['clock_fresh']
    assert {r['channel']:r['display_time'] for r in s['channels']}==EXPECTED
    assert c.get('/api/public/results').json()['heats']==[]
    assert tables(app.state.store)==before


def test_busy_udp_port_is_a_visible_failure_not_a_connection(api):
    app,c,auth,_=api
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as other:
        other.bind(('0.0.0.0',0));port=other.getsockname()[1]
        result=c.post('/api/swimtime/start',headers=auth,json={'source_ip':'127.0.0.1','port':port})
    assert result.status_code==409
    assert not app.state.swimtime.snapshot()['listening']


def test_restart_starts_with_no_retained_live_clock(tmp_path):
    old=SwimTimeNetwork(tmp_path)
    old.replay=True
    old.data.consume(frame(),('10.227.186.112',9),time.time())
    fresh=SwimTimeNetwork(tmp_path)
    assert fresh.snapshot()['clock_display'] is None
    assert fresh.snapshot()['channels']==[] and fresh.snapshot()['state']=='STOPPED'


def test_venue_mode_disables_observed_profile_and_replay(tmp_path):
    app=create_app(tmp_path/'venue.sqlite3','VENUE')
    app.state.store.create_user('timing','TIMING_OPERATOR','TEST_password_12345')
    with TestClient(app) as c:
        token=c.post('/api/login',json={'user':'timing','password':'TEST_password_12345'}).json()['token']
        auth={'Authorization':'Bearer '+token}
        assert c.post('/api/swimtime/start',headers=auth,json={}).status_code==409
        assert c.post('/api/swimtime/replay',headers=auth,json={}).status_code==409
        assert not c.get('/api/swimtime').json()['enabled']


def old_project(tmp_path):
    import sqlite3
    target=tmp_path/'old-project'
    (target/'results_backend').mkdir(parents=True)
    (target/'runtime').mkdir()
    (target/'assets_original').mkdir()
    (target/'results_backend/app.py').write_text("version='0.7.0'\n")
    (target/'results_backend/schema.sql').write_text('-- test schema')
    (target/'runtime/SINGLE_TEST_CREDENTIALS.txt').write_text('PRIVATE TEST PLACEHOLDER')
    (target/'assets_original/KEEP.bin').write_bytes(b'ORIGINAL-ASSET-TEST')
    with sqlite3.connect(target/'runtime/single_test.sqlite3') as c:
        c.execute('CREATE TABLE keep(value TEXT)')
        c.execute("INSERT INTO keep VALUES('TEST preserved')")
    return target


def test_upgrade_preserves_database_credentials_and_assets(tmp_path):
    import sqlite3
    from deployment.apply_v08 import update
    target=old_project(tmp_path)
    old_db=(target/'runtime/single_test.sqlite3').read_bytes()
    report=update(target,check_services=False)
    assert "version='0.8.0'" in (target/'results_backend/app.py').read_text()
    assert (target/'runtime/single_test.sqlite3').read_bytes()==old_db
    assert (target/'runtime/SINGLE_TEST_CREDENTIALS.txt').read_text()=='PRIVATE TEST PLACEHOLDER'
    assert (target/'assets_original/KEEP.bin').read_bytes()==b'ORIGINAL-ASSET-TEST'
    assert (Path(report['backup'])/'code/results_backend/app.py').read_text()=="version='0.7.0'\n"
    with sqlite3.connect(Path(report['backup'])/'single_test.sqlite3') as c:
        assert c.execute('SELECT value FROM keep').fetchone()[0]=='TEST preserved'


def test_upgrade_rolls_back_replaced_code_after_copy_failure(tmp_path,monkeypatch):
    from deployment import apply_v08
    target=old_project(tmp_path)
    original=apply_v08.shutil.copy2
    def fail_second(source,dest,*args,**kwargs):
        if str(dest).endswith('swimtime_network.py.v08-new'):
            Path(dest).write_bytes(b'PARTIAL TEST COPY')
            raise OSError('Injected TEST copy failure')
        return original(source,dest,*args,**kwargs)
    monkeypatch.setattr(apply_v08.shutil,'copy2',fail_second)
    with pytest.raises(OSError):apply_v08.update(target,check_services=False)
    assert (target/'results_backend/app.py').read_text()=="version='0.7.0'\n"
    assert not list(target.rglob('*.v08-new'))
    assert not (target/'alge_gateway/swimtime_network.py').exists()


def test_auto_complete_heat_on_race_end_and_zero_lanes(tmp_path):
    calls = []
    net = SwimTimeNetwork(tmp_path)
    net.sync_config.update({'api_base_url': 'https://example.test/v2/api', 'bearer_token': 'tok', 'auto_sync': True})

    def fake_http(method, url, body=None):
        calls.append((method, url, body))
        if method == 'GET':
            return 200, {'data': [{'_id': 'heat123', 'heatNumber': 1, 'status': 'ONGOING', 'competition': '100m SF'}]}
        if method == 'POST':
            return 200, {'message': 'Results recorded'}
        if method == 'PATCH':
            return 200, {'message': 'Heat marked COMPLETED'}
        return 200, {}

    net._http_json = fake_http
    # Scenario 1: Race starts, lane 2 finishes, SwimTime sends LaneTime -1 wipe then Ready 0
    net.data.consume(b'Heat\tHeatNumber\t1\rHeat\tLaps\t2\r', ('10.227.186.112', 9), 100.0)
    r_start = net.data.consume(frame('RunningTime', 10000, channel=1, lap=1), ('10.227.186.112', 9), 101.0)
    assert r_start.get('trigger_race_start') is True
    net._sync_worker(force=False, check_only=True, reason='auto_race_start')
    r_touch = net.data.consume(frame('LaneTime', 355448, channel=2, lap=2), ('10.227.186.186', 9), 102.0)
    assert not r_touch['accepted']  # wrong source IP ignored
    r_touch = net.data.consume(frame('LaneTime', 355448, channel=2, lap=2), ('10.227.186.112', 9), 102.0)
    assert r_touch.get('trigger_external_sync') is True
    net._sync_worker(force=False, check_only=False, reason='auto_lane_touch')
    # SwimTime wipes channels with -1 right before Ready
    net.data.consume(frame('LaneTime', -1, channel=2, lap=0), ('10.227.186.112', 9), 103.0)
    r_end = net.data.consume(frame('Ready', 0, channel=1, lap=0), ('10.227.186.112', 9), 103.1)
    snap = r_end.get('trigger_race_end')
    assert snap is not None and len(snap['finished_channels']) == 1
    net._sync_worker(force=True, check_only=False, reason='auto_race_end', complete_heat=True, end_snapshot=snap)
    assert sum(1 for m, _, _ in calls if m == 'GET') == 1
    assert ('POST', 'https://example.test/v2/api/heats/heat123/results', {
        'results': [{'lane': 2, 'timeMs': 35540, 'resultStatus': 'PENDING', 'athleteStatus': 'PENDING'}]
    }) in calls
    assert ('PATCH', 'https://example.test/v2/api/heats/heat123/status', {'status': 'COMPLETED', 'startNextHeat': True}) in calls
    assert net.sync_status['state'] == 'COMPLETED'
    assert net.active_heat_id is None

    # Scenario 2: Race starts after Layout\tStartlist in 800m Final (16 laps), touch on Lap 1 still syncs, and stops
    calls.clear()
    net.last_completed_heat_id = None
    net.data.consume(b'Layout\tStartlist', ('10.227.186.112', 9), 199.0)
    net.data.consume(b'Heat\tHeatNumber\t1\rHeat\tHeatName\tFinal\rHeat\tLaps\t16\r', ('10.227.186.112', 9), 199.5)
    net.data.consume(frame('RunningTime', 20000, channel=1, lap=1), ('10.227.186.112', 9), 200.0)
    r_stop = net.data.consume(frame('RunningTime', -1, channel=1, lap=0), ('10.227.186.112', 9), 205.0)
    snap2 = r_stop.get('trigger_race_end')
    assert snap2 is not None and snap2['finished_channels'] == []
    net._sync_worker(force=True, check_only=False, reason='auto_race_end', complete_heat=True, end_snapshot=snap2)
    assert ('PATCH', 'https://example.test/v2/api/heats/heat123/status', {'status': 'COMPLETED', 'startNextHeat': True}) in calls
    assert not any(m == 'POST' for m, _, _ in calls)

    # Scenario 3: 800m Final (Heat.Laps = 16) with Lap=1 touch immediately triggers POST
    calls.clear()
    net.last_completed_heat_id = None
    net.data.consume(b'Layout\tStartlist', ('10.227.186.112', 9), 300.0)
    net.data.consume(frame('RunningTime', 30000, channel=1, lap=1), ('10.227.186.112', 9), 301.0)
    r_lap1 = net.data.consume(frame('LaneTime', 57923, channel=1, lap=1), ('10.227.186.112', 9), 302.0)
    assert r_lap1.get('trigger_external_sync') is True
    net._sync_worker(force=False, check_only=False, reason='auto_lane_touch')
    assert ('POST', 'https://example.test/v2/api/heats/heat123/results', {
        'results': [{'lane': 1, 'timeMs': 5790, 'resultStatus': 'PENDING', 'athleteStatus': 'PENDING'}]
    }) in calls


