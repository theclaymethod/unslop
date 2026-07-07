#!/usr/bin/env python3
import json, sys
from _check_support import ROOT

SCRIPTS = ROOT / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import banned_phrase_scan  # noqa: E402
import structure_scan  # noqa: E402

PAIR_DIR=ROOT/'evals/fixtures/pairs'

def words(p):
    return len(p.read_text().split())

def scan_banned(path):
    """In-process equivalent of banned_phrase_scan.py's CLI: (returncode, data)."""
    text = path.read_text()
    violations = banned_phrase_scan.scan_for_violations(text)
    if not violations and not banned_phrase_scan.is_probably_english(text):
        return 0, {'non_english': True, 'total_violations': 0, 'violations': []}
    categories = {}
    by_severity = {'hard': 0, 'soft': 0}
    for v in violations:
        categories[v['category']] = categories.get(v['category'], 0) + 1
        by_severity[v['severity']] = by_severity.get(v['severity'], 0) + 1
    data = {
        'total_violations': len(violations),
        'by_severity': by_severity,
        'by_category': categories,
        'violations': violations,
    }
    return (1 if violations else 0), data

def scan_structure(path):
    """In-process equivalent of structure_scan.py's CLI: (returncode, data)."""
    text = path.read_text()
    result = structure_scan.scan(text)
    if not result.get('flags') and not structure_scan.is_probably_english(text):
        return 0, {'non_english': True, 'violations': [], 'flags': []}
    return (1 if result['flags'] else 0), result

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
        b_rc,b_data=scan_banned(np)
        s_rc,_=scan_structure(np)
        without_clean=(b_rc==0 and b_data.get('total_violations')==0 and s_rc==0)
        if not without_clean: ok=False
        if info['kind']=='structure':
            _,data=scan_structure(wp)
            hit=bool(data.get('flagged',{}).get(info['target']))
            desc=','.join(data.get('flagged',{}).keys()) or '-'
        else:
            _,data=scan_banned(wp)
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
