"""Provision one named local operator with a unique password; never print it."""
import json,os,secrets
from results_backend.store import Store,ROOT

mode=os.getenv('FINS_MODE','TEST')
path=os.getenv('FINS_DB',str(ROOT/'runtime'/('single_'+mode.lower()+'.sqlite3')))
s=Store(path,mode,operator_mode='SINGLE')
with s.db(False) as c:exists=c.execute("SELECT 1 FROM users WHERE id='operator'").fetchone()
if not exists:
    password=secrets.token_urlsafe(18)
    s.create_user('operator','SINGLE_OPERATOR',password)
    p=ROOT/'runtime'/('SINGLE_'+mode+'_CREDENTIALS.txt')
    p.write_text('PRIVATE - DO NOT SHARE WITH OBS PLAYERS\nUSER: operator\nPASSWORD: '+password+'\nMODE: '+mode+'\n',encoding='utf-8')
    try:p.chmod(0o600)
    except OSError:pass
    print('Unique account saved in runtime/'+p.name)
else:
    with s.db(False) as c:
        if c.execute("SELECT role FROM users WHERE id='operator'").fetchone()[0]!='SINGLE_OPERATOR':raise SystemExit('Existing operator ID belongs to another role. No account overwritten.')
    print('Existing operator preserved; use its existing password.')
if mode=='TEST':
    with s.db(False) as c:n=c.execute('SELECT COUNT(*) FROM heats').fetchone()[0]
    if n==0:s.import_meet({'id':'operator','role':'SINGLE_OPERATOR'},json.loads((ROOT/'testing/fixtures/meet.json').read_text()))
    with s.db() as c:c.execute('UPDATE routes SET safe=24 WHERE safe=32')
print('Single operator ready; '+mode+' database remains separate from other modes.')
