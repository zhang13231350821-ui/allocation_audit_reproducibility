"""Check immutable package hashes, input design and scheduled outcome counts."""
from pathlib import Path
import csv,hashlib,json,sys
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from package_runtime import paths

ROOT,DATA,RESULTS,OPTIONS=paths()
manifest=ROOT/'MANIFEST.sha256'
checked=0
if manifest.exists():
    for line in manifest.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('#'):continue
        digest,relative=line.split('  ',1)
        if relative.startswith('results/'):continue
        path=(ROOT/relative).resolve()
        assert path.is_relative_to(ROOT) and path.is_file(),relative
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,'Changed immutable file: '+relative
        checked+=1
else:
    raise SystemExit('MANIFEST.sha256 is missing; use the complete distributed package.')
with DATA.open(encoding='utf-8-sig',newline='') as f:
    rows=list(csv.DictReader(f))
assert len(rows)==20000
assert len({x['trial_id'] for x in rows})==20000
counts=Counter((int(x['H']),int(x['D']),x['valid'].lower()=='true') for x in rows)
expected={(0,0):(4963,37,3960),(0,1):(4968,32,2932),(1,0):(4965,35,3807),(1,1):(4969,31,2912)}
for (h,d),(valid,invalid,b) in expected.items():
    assert counts[h,d,True]==valid and counts[h,d,False]==invalid,(h,d)
    assert sum(float(x['Y']) for x in rows if int(x['H'])==h and int(x['D'])==d and x['valid'].lower()=='true')==b
for x in rows:
    if x['valid'].lower()=='false':assert x['Y']=='' and x['choice']==''
assert {float(x['Delta']) for x in rows}=={1,2,3,4,4.5,4.6,4.7,4.8,4.9,5}
assert {float(x['g']) for x in rows}=={.5,2,4,8,20,50,100,200,500,1000}
assert min(int(x['source_line']) for x in rows)==1001
assert max(int(x['source_line']) for x in rows)==21000
assert len(Counter((x['H'],x['D'],x['Delta'],x['g']) for x in rows))==400
assert all(n==50 for n in Counter((x['H'],x['D'],x['Delta'],x['g']) for x in rows).values())
report={'passed':True,'immutable_files_checked':checked,'formal_rows':20000,'valid_rows':19865,
        'invalid_rows':135,'network_access':'disabled by offline executor',
        'input_sha256':hashlib.sha256(DATA.read_bytes()).hexdigest()}
(RESULTS/'smoke_check.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))

