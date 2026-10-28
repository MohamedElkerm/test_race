"""Dependency, native asset, SHA-256 and screen configuration preflight."""
from pathlib import Path
import hashlib,importlib,json,platform,sqlite3,struct,sys
from results_backend.store import ROOT,SCREENS

def main():
    failures=[]
    for name in ['fastapi','uvicorn','serial','websockets','psutil']:
        try:importlib.import_module(name)
        except ImportError:failures.append('Missing dependency: '+name)
    for name in ['control_dashboard/dist/index.html','control_dashboard/dist/app.js','control_dashboard/dist/app.css','templates_sfs/registry.json']:
        if not (ROOT/name).is_file():failures.append('Missing built file: '+name)
    manifest=json.loads((ROOT/'source_audit/asset_manifest.json').read_text())
    for item in manifest:
        p=ROOT/item['path']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:failures.append('Original asset hash mismatch: '+item['path'])
    processed=json.loads((ROOT/'source_audit/processed_manifest.json').read_text()) if (ROOT/'source_audit/processed_manifest.json').exists() else []
    for item in processed:
        p=ROOT/item['path']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:failures.append('Processed asset hash mismatch: '+item['path'])
    assert sum(x['width']*x['height'] for x in SCREENS.values())==7569408
    (ROOT/'runtime').mkdir(exist_ok=True)
    report={'platform':platform.platform(),'python':sys.version,'bits':struct.calcsize('P')*8,'sqlite':sqlite3.sqlite_version,'original_assets_checked':len(manifest),'processed_assets_checked':len(processed),'failures':failures,'production_approved':False,'windows_field_test':'PENDING'}
    (ROOT/'runtime/preflight.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if failures:raise SystemExit(1)
if __name__=='__main__':main()
