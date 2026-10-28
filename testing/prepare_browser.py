import json,sys
from pathlib import Path
from results_backend.store import Store,ROOT,ROLES
p=Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True)
for suffix in ('','-wal','-shm'):
 q=Path(str(p)+suffix)
 if q.exists():q.unlink()
s=Store(p)
for r in ROLES:s.create_user('TEST_'+r,r,'Browser_TEST_password_123')
s.import_meet({'id':'bootstrap','role':'SYSTEM_ADMINISTRATOR'},json.loads((ROOT/'testing/fixtures/meet.json').read_text()))
print('Isolated browser test database prepared')
