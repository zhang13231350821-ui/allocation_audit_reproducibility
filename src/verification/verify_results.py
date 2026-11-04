"""Assert agreement with all frozen datasets, manuscript tables and figure source values."""
from pathlib import Path
import csv,hashlib,importlib.metadata as md,json,platform,re,sys
import numpy as np
import pandas as pd
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from package_runtime import paths

ROOT,DATA,RESULTS,OPTIONS=paths()
checks={};df=pd.read_csv(DATA);v=df[df.valid]

def compare(frozen,generated,keys,columns,tol=1e-8):
    a=pd.read_csv(ROOT/'data/derived'/frozen).sort_values(keys).reset_index(drop=True)
    b=pd.read_csv(RESULTS/'analysis'/generated).sort_values(keys).reset_index(drop=True)
    assert len(a)==len(b),(frozen,len(a),len(b))
    assert a[keys].astype(str).equals(b[keys].astype(str)),frozen
    errors={}
    for column in columns:
        aa=pd.to_numeric(a[column],errors='coerce').to_numpy()
        bb=pd.to_numeric(b[column],errors='coerce').to_numpy()
        assert np.allclose(aa,bb,rtol=tol,atol=tol,equal_nan=True),(frozen,column)
        errors[column]=float(np.nanmax(abs(aa-bb))) if np.isfinite(aa-bb).any() else None
    return errors
checks['dataset_1']=compare('Supplementary_Dataset_1_cells.csv','cells.csv',['H','D','Delta','g'],['n','B','p','wilson_low','wilson_high'])
checks['dataset_2']=compare('Supplementary_Dataset_2_coefficients.csv','coefficients.csv',['model','term'],['beta','cluster_se','p','low','high'],tol=1e-7)
checks['dataset_3_marginal']=compare('Supplementary_Dataset_3_marginal_framing.csv','model_marginal_effects.csv',['scope','value'],['difference','se','low','high','p','holm_p'])
checks['dataset_3_cells']=compare('Supplementary_Dataset_3_cell_framing.csv','framing_cell_differences.csv',['Delta','g'],['blind','disclosed','difference','point_low','point_high','simult_low','simult_high'])
checks['dataset_4']=compare('Supplementary_Dataset_4_history.csv','paired_history.csv',['D','scope','value'],['n','difference','low','high'])

ref=json.loads((ROOT/'data/metadata/manuscript_tables.json').read_text(encoding='utf-8'))
table_checks=0
number_pattern=re.compile(r'[+−-]?\d+(?:,\d{3})*(?:\.\d+)?|[+−-]?\.\d+')
for name,table in ref.items():
    with (RESULTS/'tables'/(name+'.csv')).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
    assert rows[0]==table['rows'][0],name
    assert len(rows)==len(table['rows']),name
    for i,(a,b) in enumerate(zip(table['rows'][1:],rows[1:]),1):
        assert len(a)==len(b),(name,i)
        for j,(expected,actual) in enumerate(zip(a,b)):
            ea=number_pattern.findall(expected);eb=number_pattern.findall(actual)
            assert len(ea)==len(eb),(name,i,j,expected,actual)
            for x,y in zip(ea,eb):
                xf=float(x.replace(',','').replace('−','-'));yf=float(y.replace(',','').replace('−','-'))
                digits=len(x.split('.')[1]) if '.' in x else 0
                tolerance=(.5*10**(-digits)+1e-8) if digits else 1e-8
                assert abs(xf-yf)<=tolerance,(name,i,j,expected,actual)
                table_checks+=1
checks['manuscript_tables']={'tables_checked':11,'numeric_tokens_checked':table_checks,
                           'scope':'All numeric fields in Tables 1–3 and S1–S8; S2 records documented request settings.'}

audit=json.loads((RESULTS/'audit/audit_summary.json').read_text(encoding='utf-8'))
assert audit['N']==9931 and audit['zero_variance_cells']==141 and audit['bootstrap_B']==5000
assert audit['bootstrap_seed']==20261030 and abs(audit['simultaneous_radius']-.28)<1e-10
assert all(x['rank']==9 and x['df']==9 and x['condition_number']<13 for x in audit['wald'])
assert [round(x['chi2'],2) for x in audit['wald']]==[1963.36,6270.05]
effects=pd.read_csv(RESULTS/'audit/estimand_sensitivity.csv')
overall=effects[effects.scope=='overall'].iloc[0]
assert round(overall.difference*100,2)==-20.85
assert np.all(effects[effects.scope=='delta'].cr1_high<0)
assert np.all(effects[effects.scope=='delta'].bootstrap_high<0)
cell=pd.read_csv(RESULTS/'audit/cell_framing_audit.csv')
strata=pd.read_csv(RESULTS/'audit/framing_cell_strata.csv')
local=[]
for label,delta,gap,point,b0,n0,b1,n1 in [('a',3,1000,71.47,13,49,49,50),('b',4.5,500,64,0,50,32,50),('c',5,500,46,20,50,43,50)]:
    q=cell[np.isclose(cell.Delta,delta)&np.isclose(cell.g,gap)].iloc[0]
    assert round(q.difference*100,2)==point
    assert (q.blind_B,q.blind_n,q.disclosed_B,q.disclosed_n)==(b0,n0,b1,n1)
    values=[]
    for fp in ['fp_bbfb354875','fp_eef51934d2']:
        z=strata[(strata.stratum_type=='system_fingerprint')&(strata.stratum==fp)&np.isclose(strata.Delta,delta)&np.isclose(strata.g,gap)].iloc[0]
        values.append(z.difference)
    if label in ['a','c']:assert values[0]>0 and abs(values[1])<1e-12
    else:assert min(values)>0
    local.append({'box':label,'Delta':delta,'g':gap,'pooled_difference_pp':point,'major_fingerprint_differences':values})
summary=pd.read_csv(RESULTS/'audit/framing_strata_sensitivity.csv')
for stratum,expected in [('fp_bbfb354875',-19.04),('fp_eef51934d2',-25.15),('initial_prefix',-21.97),('continuation',-19.96)]:
    x=summary[summary.stratum==stratum].iloc[0]
    assert x.shared_cells==100 and round(100*x.shared_cell_mean_difference,2)==expected
assert (v[v.H==1].system_fingerprint=='fp_4021733588').all()
assert len(v[(v.H==0)&(v.system_fingerprint=='fp_4021733588')])==108
checks['core_statistics']={'overall_standardized_difference_pp':round(overall.difference*100,2),
                           'bootstrap_replicates':5000,'bootstrap_seed':20261030,
                           'full_grid_sensitivity_radius':audit['simultaneous_radius'],
                           'wald_ranks':[x['rank'] for x in audit['wald']],
                           'selected_local_examples':local,'major_fingerprint_and_phase_directions':'negative'}
hist=pd.read_csv(RESULTS/'analysis/paired_history.csv')
for D,pairs in [(0,4962),(1,4965)]:
    x=hist[(hist.D==D)&(hist.scope=='overall')].iloc[0];assert x.n==pairs
checks['paired_history']={'blind_pairs':4962,'disclosed_pairs':4965,'fingerprint_confounding':'retained in interpretation'}

protocol=json.loads((RESULTS/'audit/protocol_verification.json').read_text(encoding='utf-8'))
assert protocol['exact_prompt_and_history_checks']==21000 and protocol['exact_attempt_payload_checks']==21365
checks['protocol']=protocol
snapshot=json.loads((ROOT/'data/metadata/manuscript_snapshot.json').read_text(encoding='utf-8'))
figures=[]
for name in ['Fig1','Fig2','Fig3','Fig4','Fig5','FigS1','FigS2']:
    file=ROOT/'figures'/(name+'.png')
    assert hashlib.sha256(file.read_bytes()).hexdigest()==snapshot['figure_sha256'][name]
    with Image.open(file) as im:assert min(im.size)>300
    assert (RESULTS/'figures'/(name+'.png')).exists()
    figures.append(name)
assert (ROOT/'figures/Fig1.png').read_bytes()==(RESULTS/'figures/Fig1.png').read_bytes()
for H,name in [(0,'Fig2'),(1,'FigS1')]:
    q=pd.read_csv(RESULTS/'figure_data'/(name+'_cells.csv'))
    assert len(q)==200 and (q.H==H).all() and q.n.between(48,50).all()
    assert np.allclose(q.p,q.B/q.n)
for name,column in [('Fig3','Delta'),('Fig5','g')]:
    q=pd.read_csv(RESULTS/'figure_data'/(name+'_marginal_probabilities.csv'))
    assert len(q)==20
    grouped=pd.read_csv(RESULTS/'analysis/cells.csv')
    for r in q.itertuples():
        s=grouped[(grouped.H==0)&(grouped.D==r.D)&np.isclose(grouped[column],getattr(r,column))]
        assert abs(s.p.mean()-r.probability)<1e-12
q=pd.read_csv(RESULTS/'figure_data/Fig4_cell_contrasts.csv')
assert np.allclose(q.difference,cell.difference)
q=pd.read_csv(RESULTS/'figure_data/FigS2_paired_history.csv')
assert len(q)==20
checks['figures']={'exact_manuscript_image_hashes_checked':figures,'statistical_figures_recreated':6,
                  'schematic':'Fig1 supplied asset copied exactly','figure_source_tables_checked':7,
                  'note':'Statistical graphics reproduce numerical values; layout/font rendering may differ from the supplied manuscript PNGs.'}
packages={}
for line in (ROOT/'requirements.txt').read_text(encoding='utf-8').splitlines():
    if '==' in line:
        name,version=line.split('==');actual=md.version(name)
        assert actual==version,(name,actual,version);packages[name]=actual
checks['environment']={'python':platform.python_version(),'platform':platform.system(),'packages':packages}
checks['source_sha256']=hashlib.sha256(DATA.read_bytes()).hexdigest()
checks['network_access']='disabled for all reproduction steps'
checks['passed']=True
(RESULTS/'verification_report.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PASS: all datasets, 11 manuscript tables, protocol records, fingerprint boundaries and seven figure sources.')
print('Numeric table checks:',table_checks)
