"""Create isolated test operator accounts and fixture. No fixed or shared passwords."""
import json,os,secrets
from results_backend.store import Store,ROOT,ROLES
mode=os.getenv('FINS_MODE','TEST')
if mode!='TEST':raise SystemExit('TEST setup only. Provision VENUE users individually via CLI.')
s=Store(ROOT/'runtime/test.sqlite3','TEST');credentials=[]
for role in sorted(ROLES-{'SINGLE_OPERATOR'}):
 user={'TIMING_OPERATOR':'timing','RESULTS_OPERATOR':'results','CHIEF_RESULTS_OFFICER':'chief','JURY_APPROVER':'jury','BROADCAST_OPERATOR':'broadcast','LED_OPERATOR':'led','SYSTEM_ADMINISTRATOR':'admin'}[role]
 with s.db(False) as c:exists=c.execute('SELECT 1 FROM users WHERE id=?',(user,)).fetchone()
 if exists:continue
 password=secrets.token_urlsafe(16);s.create_user(user,role,password);credentials.append(f'{user}\t{role}\t{password}')
if credentials:
 p=ROOT/'runtime/TEST_OPERATOR_CREDENTIALS.txt';p.write_text('TEST ACCOUNTS ONLY - keep private on control LAN\nUSER\tROLE\tPASSWORD\n'+'\n'.join(credentials)+'\n',encoding='utf-8')
 try:p.chmod(0o600)
 except OSError:pass
 print('Test account credentials saved in runtime/TEST_OPERATOR_CREDENTIALS.txt')
with s.db(False) as c:n=c.execute('SELECT COUNT(*) FROM heats').fetchone()[0]
if n==0:s.import_meet({'id':'bootstrap','role':'SYSTEM_ADMINISTRATOR'},json.loads((ROOT/'testing/fixtures/meet.json').read_text()))
print('TEST database ready. Do not use these accounts or database for official operation.')
