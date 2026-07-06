#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
PAIR_DIR=ROOT/'evals/fixtures/pairs'

def run(cmd):
    return subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)

def words(p):
    return len(p.read_text().split())

def main():
    manifest=json.loads((PAIR_DIR/'manifest.json').read_text())
    rows=[]; ok=True
    for slug,info in manifest.items():
        ext='md' if slug.startswith('macro_') else 'txt'
        wp=PAIR_DIR/f'{slug}_with.{ext}'; np=PAIR_DIR/f'{slug}_without.{ext}'
        if not wp.exists() or not np.exists():
            print(f'MISSING {slug}'); ok=False; continue
        wcw,wcn=words(wp),words(np)
        diff=abs(wcw-wcn)/max(wcw,wcn,1)
        if diff>0.25:
            ok=False
        b_without=run(['python3','scripts/banned_phrase_scan.py',str(np.relative_to(ROOT))])
        try: b_data=json.loads(b_without.stdout)
        except Exception: b_data={'total_violations':999,'violations':[]}
        s_without=run(['python3','scripts/structure_scan.py',str(np.relative_to(ROOT))])
        without_clean=(b_without.returncode==0 and b_data.get('total_violations')==0 and s_without.returncode==0)
        if not without_clean: ok=False
        if info['kind']=='structure':
            with_proc=run(['python3','scripts/structure_scan.py',str(wp.relative_to(ROOT))])
            try: data=json.loads(with_proc.stdout)
            except Exception: data={}
            hit=bool(data.get('flagged',{}).get(info['target']))
            desc=','.join(data.get('flagged',{}).keys()) or '-'
        else:
            with_proc=run(['python3','scripts/banned_phrase_scan.py',str(wp.relative_to(ROOT))])
            try: data=json.loads(with_proc.stdout)
            except Exception: data={}
            cats=[v.get('category') for v in data.get('violations',[])]
            hit=info['target'] in cats
            desc=','.join(cats) or '-'
        if not hit: ok=False
        rows.append((slug,info['target'],desc,'yes' if without_clean else 'no'))
    print('| slug | family | with-violations | without-clean |')
    print('|---|---|---|---|')
    for r in rows:
        print('| ' + ' | '.join(r) + ' |')
    return 0 if ok else 1
if __name__=='__main__': sys.exit(main())
