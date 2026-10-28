import argparse,getpass,json,os,sqlite3
from pathlib import Path
from .store import Store,ROOT,ROLES

def main():
    p=argparse.ArgumentParser();p.add_argument('--db');p.add_argument('--mode',choices=['TEST','VENUE'],default=os.getenv('FINS_MODE','TEST'))
    s=p.add_subparsers(dest='cmd',required=True)
    u=s.add_parser('user');u.add_argument('id');u.add_argument('role',choices=sorted(ROLES));u.add_argument('--password-env')
    s.add_parser('seed-test')
    r=s.add_parser('restore');r.add_argument('backup');r.add_argument('--confirm-stopped',action='store_true')
    a=p.parse_args();store=Store(a.db or ROOT/'runtime'/f'{a.mode.lower()}.sqlite3',a.mode)
    if a.cmd=='user':
        password=os.environ[a.password_env] if a.password_env else getpass.getpass('New password (12+ characters): ')
        store.create_user(a.id,a.role,password);print('User created:',a.id,a.role)
    elif a.cmd=='seed-test':
        if a.mode!='TEST':p.error('Test fixtures cannot be loaded into VENUE')
        fixture=json.loads((ROOT/'testing/fixtures/meet.json').read_text())
        print(store.import_meet({'id':'bootstrap','role':'SYSTEM_ADMINISTRATOR'},fixture))
    elif a.cmd=='restore':
        if not a.confirm_stopped:p.error('Stop the service and pass --confirm-stopped')
        source=sqlite3.connect(Path(a.backup).resolve())
        if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':p.error('Backup integrity check failed')
        if source.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0]!=a.mode:p.error('Mode mismatch')
        # Restore with SQLite backup API, never copying a live WAL file.
        with sqlite3.connect(store.path) as target:source.backup(target)
        source.close()
        with store.db() as c:
            c.execute('DELETE FROM tokens');c.execute('UPDATE heats SET recovery_hold=1')
            c.execute('UPDATE routes SET blackout=1');c.execute("UPDATE graphics SET program=NULL,preview=NULL,held=0")
            store.audit(c,'restore-cli','RESTORE',str(a.backup),None,{'outputs':'blackout'},'local backup','Service stopped restore; all sessions revoked')
        print('Restored. Outputs blacked out; log in and verify heat state before release.')
if __name__=='__main__':main()
