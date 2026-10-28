"""Upgrade the local v0.7 code only; preserve its databases, credentials and assets."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import time

SOURCE = Path(__file__).resolve().parents[1]
FILES = [
    'results_backend/app.py', 'alge_gateway/swimtime_network.py',
    'alge_gateway/swimtime_observed.py',
    'control_dashboard/src/main.tsx', 'control_dashboard/src/SwimTimePanel.tsx',
    'control_dashboard/src/style.css', 'control_dashboard/package.json',
    'control_dashboard/package-lock.json', 'control_dashboard/dist/app.js',
    'control_dashboard/dist/app.css', 'control_dashboard/dist/index.html',
    'RUN_SWIMTIME_TEST_LAN.cmd', 'docs/README_v08_AR.html',
    'docs/SwimTime_v08_Verification.md', 'deployment/RELEASE_NOTES_v08.md',
]


def update(target, source=SOURCE, check_services=True):
    target, source = Path(target).resolve(), Path(source).resolve()
    if target == source:
        raise ValueError('Select the existing v0.7 project folder, not this downloaded v0.8 folder.')
    app = target/'results_backend/app.py'
    if not app.is_file() or not (target/'results_backend/schema.sql').is_file():
        raise ValueError('Target is not a FINS2026_LIVE_RESULTS project folder.')
    if not any(v in app.read_text(encoding='utf-8') for v in ("version='0.7.0'", "version='0.8.0'")):
        raise ValueError('Only the reviewed v0.7/v0.8 application can be updated.')
    if check_services:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
            sock.settimeout(.3)
            if sock.connect_ex(('127.0.0.1',8765)) == 0:
                raise ValueError('Stop the FINS server on TCP 8765 before applying the update.')
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            try:sock.bind(('0.0.0.0',26))
            except OSError as exc:raise ValueError('Close RUN_FINS_MONITOR and any UDP 26 listener before updating.') from exc
    files = FILES + [str(p.relative_to(source)).replace('\\','/') for p in (source/'evidence/swimtime').iterdir() if p.is_file()]
    for name in files:
        if not (source/name).is_file():
            raise ValueError('Update source is incomplete: '+name)
        if not (target/name).resolve().is_relative_to(target):
            raise ValueError('Refusing a target path outside the selected project: '+name)
    backup = target/'backups'/('v08-update-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()))
    backup.mkdir(parents=True)
    # Use the SQLite backup API so any retained WAL content is included.
    for db in (target/'runtime').glob('*.sqlite3'):
        if db.is_file():
            with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as old:
                with sqlite3.connect(backup/db.name) as saved:old.backup(saved)
    existed={name:(target/name).is_file() for name in files}
    for name in files:
        if existed[name]:
            (backup/'code'/name).parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target/name,backup/'code'/name)
    changed=[]
    try:
        for name in files:
            dest=target/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            temporary=dest.with_name(dest.name+'.v08-new')
            shutil.copy2(source/name,temporary)
            temporary.replace(dest)
            changed.append(name)
    except OSError:
        for name in reversed(changed):
            if existed[name]:shutil.copy2(backup/'code'/name,target/name)
            else:(target/name).unlink(missing_ok=True)
        for name in files:
            dest=target/name
            dest.with_name(dest.name+'.v08-new').unlink(missing_ok=True)
        raise
    report={'version':'0.8.0','files_updated':files,'databases_preserved':True,
            'credentials_preserved':True,'assets_changed':False,'backup':str(backup),
            'windows_runtime_acceptance':'PENDING'}
    (backup/'update_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',required=True,type=Path)
    args=parser.parse_args()
    try:
        report=update(args.target)
        print('Update complete. Databases, operator credentials and original assets preserved.')
        print('Backup:',report['backup'])
        print('Run RUN_SWIMTIME_TEST_LAN.cmd in the existing project and open the SwimTime TEST tab.')
    except (OSError,ValueError,sqlite3.Error) as exc:
        print('UPDATE STOPPED:',exc)
        raise SystemExit(1)
