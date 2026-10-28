"""Isolated synthetic browser fixture; never provision venue accounts."""
import json,sys
from pathlib import Path
from results_backend.store import Store,ROOT
p=Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True)
for suffix in ('','-wal','-shm'):Path(str(p)+suffix).unlink(missing_ok=True)
s=Store(p,operator_mode='SINGLE');s.create_user('TEST_SINGLE_OPERATOR','SINGLE_OPERATOR','Browser_TEST_password_123')
s.import_meet({'id':'TEST_SINGLE_OPERATOR','role':'SINGLE_OPERATOR'},json.loads((ROOT/'testing/fixtures/meet.json').read_text()))
with s.db() as c:c.execute('UPDATE routes SET safe=24')
print('Isolated SINGLE TEST fixture ready')
