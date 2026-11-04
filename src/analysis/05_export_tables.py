"""Export the main and supplementary tables from reproduced estimates."""
from pathlib import Path
import csv,json,sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from package_runtime import paths

ROOT,DATA,RESULTS,OPTIONS=paths()
df=pd.read_csv(DATA);v=df[df.valid];h=v[v.H==0]
ref=json.loads((ROOT/'data/metadata/manuscript_tables.json').read_text(encoding='utf-8'))
out=RESULTS/'tables';out.mkdir(parents=True,exist_ok=True)
es=pd.read_csv(RESULTS/'audit/estimand_sensitivity.csv')
cf=pd.read_csv(RESULTS/'audit/cell_framing_audit.csv')
hist=pd.read_csv(RESULTS/'analysis/paired_history.csv')
strata=pd.read_csv(RESULTS/'audit/framing_strata_sensitivity.csv')
fits=pd.read_csv(RESULTS/'analysis/model_fit.csv')
def emit(name,rows):
    with (out/(name+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(ref[name]['rows'][0]);w.writerows(rows)
def signed(x,plus=False,digits=2):
    s=f'{x:+.{digits}f}' if plus else f'{x:.{digits}f}'
    return s.replace('-','−')
def ci(x,a,b,plus=False):return signed(x[a]*100,plus)+' to '+signed(x[b]*100,plus)
def effect(scope,value=None):
    s=es[es.scope==scope]
    if value is not None:s=s[np.isclose(s.value,float(value))]
    return s.iloc[0]
rows=[]
for H in [0,1]:
    for D in [0,1]:
        s=df[(df.H==H)&(df.D==D)]
        rows.append([f'H{H} '+['blind','disclosed'][D],s.path_cluster.nunique(),len(s),int(s.valid.sum()),int((~s.valid).sum())])
emit('Table_1',rows)
rows=[]
for r in ref['Table_2']['rows'][1:]:
    scope={'Overall':'overall','Δ':'delta','g':'gap'}[r[0]]
    x=effect(scope,None if scope=='overall' else r[1].replace(',',''))
    p='—' if scope=='overall' else ('< .001' if x.holm_p<.001 else f'{x.holm_p:.3f}'.lstrip('0'))
    rows.append([r[0],r[1],signed(x.difference*100),ci(x,'cr1_low','cr1_high'),p])
emit('Table_2',rows)
rows=[]
for D in [0,1]:
    x=hist[(hist.D==D)&(hist.scope=='overall')].iloc[0]
    rows.append([['Blind','Disclosed'][D],int(x.n),signed(x.difference*100),ci(x,'low','high')])
emit('Table_3',rows)
rows=[]
for H in [0,1]:
    for D in [0,1]:
        s=df[(df.H==H)&(df.D==D)];valid=s[s.valid]
        rows.append([f'H{H}',['Blind','Disclosed'][D],int((valid.Y==0).sum()),int(valid.Y.sum()),int((~s.valid).sum()),len(s)])
emit('Table_S1',rows)
# The API configuration table is a documented protocol table, verified against all archived payloads by step 04.
emit('Table_S2',ref['Table_S2']['rows'][1:])
rows=[]
for fp in [r[0] for r in ref['Table_S3']['rows'][1:]]:
    row=[fp]
    for gap in [20,200]:
        s=v[(v.H==0)&(v.D==1)&(v.g==gap)&(v.system_fingerprint==fp)]
        row.append(f'{int(s.Y.sum())} / {len(s)}')
    rows.append(row)
emit('Table_S3',rows)
sst=((h.Y-h.Y.mean())**2).sum();rows=[]
for r in ref['Table_S4']['rows'][1:]:
    x=fits[fits.model==r[0]].iloc[0]
    rows.append([r[0],r[1],int(x.parameters),f'{x.deviance:,.2f}',f'{1-x.deviance/sst:.3f}'])
emit('Table_S4',rows)
for table in ['Table_S5','Table_S6']:
    rows=[]
    for r in ref[table]['rows'][1:]:
        key={'Continuation':'continuation','Original prefix':'initial_prefix'}.get(r[0],r[0])
        x=strata[strata.stratum==key].iloc[0]
        rows.append([r[0],f'{int(x.blind_B):,}/{int(x.blind_n):,}',f'{int(x.disclosed_B):,}/{int(x.disclosed_n):,}',int(x.shared_cells),signed(100*x.shared_cell_mean_difference)])
    emit(table,rows)
rows=[]
for label,d,g in [('a',3,1000),('b',4.5,500),('c',5,500)]:
    x=cf[np.isclose(cf.Delta,d)&np.isclose(cf.g,g)].iloc[0]
    rows.append([f'{label}: {d:g}, {g:g}',f'{int(x.blind_B)}/{int(x.blind_n)}',f'{int(x.disclosed_B)}/{int(x.disclosed_n)}',signed(x.difference*100,True),ci(x,'point_low','point_high',True),ci(x,'simult_low','simult_high',True)])
emit('Table_S7',rows)
rows=[]
for r in ref['Table_S8']['rows'][1:]:
    scope='overall' if r[0]=='Overall' else ('delta' if r[0].startswith('Δ') else 'gap')
    x=effect(scope,None if scope=='overall' else r[0].split('=')[1])
    rows.append([r[0],signed(x.difference*100),ci(x,'cr1_low','cr1_high'),ci(x,'bootstrap_low','bootstrap_high')])
emit('Table_S8',rows)
with (RESULTS/'manuscript_tables.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f);writer.writerow(['table','row_index','column_1','column_2','column_3','column_4','column_5','column_6'])
    for name in ref:
        with (out/(name+'.csv')).open(encoding='utf-8-sig',newline='') as source:
            for i,row in enumerate(csv.reader(source)):
                writer.writerow([name,i,*row,*(['']*(6-len(row)))])
print('Exported Table 1–3 and Supplementary Tables S1–S8.')
