#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
DOC_DIR=ROOT/'evals/fixtures/docs'

def run(cmd): return subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
def scan_phrase(path):
    p=run(['python3','scripts/banned_phrase_scan.py',str(path.relative_to(ROOT))])
    try: data=json.loads(p.stdout)
    except Exception: data={'violations':[],'total_violations':999}
    return p,data
def scan_struct(path):
    p=run(['python3','scripts/structure_scan.py',str(path.relative_to(ROOT))])
    try: data=json.loads(p.stdout)
    except Exception: data={'flags':[],'flagged':{}}
    return p,data

def main():
    ok=True
    for manifest in sorted(DOC_DIR.glob('*_manifest.json')):
        slug=manifest.name[:-14]
        seeded=DOC_DIR/f'{slug}_seeded.md'; clean=DOC_DIR/f'{slug}_clean.md'
        expected=json.loads(manifest.read_text())['expected']
        _,pdata=scan_phrase(seeded); _,sdata=scan_struct(seeded)
        cats={v.get('category') for v in pdata.get('violations',[])} | set(sdata.get('flagged',{}).keys())
        missing=[e['category'] for e in expected if e['category'] not in cats]
        if missing:
            ok=False; print(f'{slug}: missing {missing}; saw {sorted(cats)}')
        cp,cpdata=scan_phrase(clean); cs,_=scan_struct(clean)
        if cp.returncode!=0 or cpdata.get('total_violations')!=0 or cs.returncode!=0:
            ok=False; print(f'{slug}: clean twin failed phrase={cpdata.get("total_violations")} structure_exit={cs.returncode}')
    if ok: print('seeded docs ok')
    return 0 if ok else 1
if __name__=='__main__': sys.exit(main())
