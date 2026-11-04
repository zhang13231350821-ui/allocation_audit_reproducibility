"""Estimate matched CR1/bootstrap intervals, covariance diagnostics and metadata strata."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from package_runtime import paths
ROOT,DATA,RESULTS,OPTIONS=paths()
import json, shutil, hashlib
import numpy as np
import pandas as pd
from scipy.stats import norm, chi2
from statsmodels.stats.multitest import multipletests

A=RESULTS/'audit';A.mkdir(parents=True,exist_ok=True)
df=pd.read_csv(DATA); v=df[df.valid].copy(); h=v[v.H==0].copy()
assert len(df)==20000 and len(h)==9931 and len(v[v.H==1])==9934
ds=sorted(df.Delta.unique()); gs=sorted(df.g.unique())
h['cell']=[int(r.D)*100+ds.index(r.Delta)*10+gs.index(r.g) for r in h.itertuples()]
n=np.bincount(h.cell,minlength=200); b=np.bincount(h.cell,weights=h.Y,minlength=200); mu=b/n
assert n.min()==48 and n.max()==50
# Cell-indicator parameterization gives the same fitted values and covariance as
# the saturated treatment-coded OLS model, without a poorly conditioned coding.
paths=sorted(h.path_cluster.unique()); scores=np.zeros((1000,200))
for r in h.itertuples():scores[paths.index(r.path_cluster),r.cell]+=(r.Y-mu[r.cell])/n[r.cell]
cr1=1000/999*(9931-1)/(9931-200)
cov=cr1*scores.T@scores
arr=np.zeros((2,10,10,50,2))
for r in h.itertuples(): arr[int(r.D),ds.index(r.Delta),gs.index(r.g),int(r.r)-1]+=[r.Y,1]
counts=np.random.default_rng(20261030).multinomial(50,np.ones(50)/50,size=5000)
boot=np.stack([np.einsum('br,dgr->bdg',counts,arr[D,:,:,:,0])/np.einsum('br,dgr->bdg',counts,arr[D,:,:,:,1]) for D in [0,1]],axis=1)
bootdiff=boot[:,1]-boot[:,0]; diff=(mu[100:]-mu[:100]).reshape(10,10)
radius=float(np.quantile(np.max(abs(bootdiff-diff),axis=(1,2)),.95))
L=np.concatenate([-np.eye(100),np.eye(100)],axis=1)
estimands=[]; grads={}
for scope,levels in [('overall',[None]),('delta',ds),('gap',gs)]:
    for i,level in enumerate(levels):
        ix=np.arange(100) if scope=='overall' else (np.arange(i*10,i*10+10) if scope=='delta' else np.arange(i,100,10))
        g=L[ix].mean(axis=0); grads[scope,level]=g
        est=float(g@mu); se=float(np.sqrt(max(0,g@cov@g)))
        draws=bootdiff.reshape(5000,100)[:,ix].mean(axis=1)
        lo,hi=np.quantile(draws,[.025,.975]); p=2*norm.sf(abs(est/se)) if se>1e-12 else np.nan
        estimands.append(dict(scope=scope,value=level,difference=est,cr1_se=se,cr1_low=est-1.96*se,cr1_high=est+1.96*se,cr1_p=p,bootstrap_low=lo,bootstrap_high=hi))
ef=pd.DataFrame(estimands)
for scope in ['delta','gap']:
    ix=ef.scope==scope;ef.loc[ix,'holm_p']=multipletests(ef.loc[ix,'cr1_p'].fillna(1),method='holm')[1]
ef.to_csv(A/'estimand_sensitivity.csv',index=False)
wald=[]
for scope,levels in [('delta',ds),('gap',gs)]:
    rr=np.array([grads[scope,x]-grads[scope,levels[0]] for x in levels[1:]])
    vv=rr@cov@rr.T; eig=np.linalg.eigvalsh(vv); rank=int(np.linalg.matrix_rank(vv))
    z=rr@mu; stat=float(z@np.linalg.solve(vv,z))
    pinv_stat=float(z@np.linalg.pinv(vv)@z)
    wald.append(dict(scope=scope,rank=rank,df=9,eigen_min=float(eig.min()),eigen_max=float(eig.max()),condition_number=float(np.linalg.cond(vv)),chi2=stat,p=float(chi2.sf(stat,rank)),solve_pinv_difference=abs(stat-pinv_stat)))
pd.DataFrame(wald).to_csv(A/'wald_rank_audit.csv',index=False)
cell=[]
for i,d in enumerate(ds):
    for j,gap in enumerate(gs):
        k=i*10+j; se=float(np.sqrt(max(0,L[k]@cov@L[k])))
        lo,hi=np.quantile(bootdiff[:,i,j],[.025,.975])
        cell.append(dict(Delta=d,g=gap,blind_B=int(b[k]),blind_n=int(n[k]),disclosed_B=int(b[k+100]),disclosed_n=int(n[k+100]),difference=float(diff[i,j]),cr1_se=se,cr1_low=float(diff[i,j]-1.96*se),cr1_high=float(diff[i,j]+1.96*se),point_low=float(lo),point_high=float(hi),simult_low=max(-1,float(diff[i,j]-radius)),simult_high=min(1,float(diff[i,j]+radius))))
cf=pd.DataFrame(cell);cf.to_csv(A/'cell_framing_audit.csv',index=False)
old=pd.read_csv(ROOT/'data/derived/Supplementary_Dataset_3_cell_framing.csv')
assert np.allclose(cf.difference,old.difference) and np.allclose(cf.point_low,old.point_low)
# Original source_line is a one-based line in the full archive, including seeds.
assert df.source_line.min()==1001 and df.source_line.max()==21000
h['collection_phase']=np.where(h.source_line<=8550,'initial_prefix','continuation')
h['collection_date_utc']=pd.to_datetime(h.started_utc).dt.strftime('%Y-%m-%d')
fp=h.groupby(['D','system_fingerprint']).Y.agg(['size','sum','mean']).reset_index()
fp.to_csv(A/'h0_fingerprint_by_framing.csv',index=False)
h.groupby(['collection_phase','D','system_fingerprint']).Y.agg(['size','sum','mean']).reset_index().to_csv(A/'h0_phase_fingerprint.csv',index=False)
h.groupby(['collection_date_utc','D','system_fingerprint']).Y.agg(['size','sum','mean']).reset_index().to_csv(A/'h0_date_fingerprint.csv',index=False)
# Compare like numerical cells within each fingerprint/phase. Sparse shared support
# is explicitly retained; these are descriptive subsets, not adjusted causal effects.
strata=[]
cell_strata=[]
for key in ['system_fingerprint','collection_phase']:
    for label,sub in h.groupby(key):
        cells=sub.groupby(['D','Delta','g']).Y.agg(['size','sum','mean']).reset_index()
        pv=cells.pivot(index=['Delta','g'],columns='D',values='mean').dropna()
        for (d,gap),one in cells.groupby(['Delta','g']):
            dd=one.set_index('D')
            if 0 in dd.index and 1 in dd.index:
                cell_strata.append(dict(stratum_type=key,stratum=label,Delta=d,g=gap,blind_B=int(dd.loc[0,'sum']),blind_n=int(dd.loc[0,'size']),disclosed_B=int(dd.loc[1,'sum']),disclosed_n=int(dd.loc[1,'size']),difference=float(dd.loc[1,'mean']-dd.loc[0,'mean'])))
        rows={D:sub[sub.D==D] for D in [0,1]}
        strata.append(dict(stratum_type=key,stratum=label,blind_n=len(rows[0]),disclosed_n=len(rows[1]),blind_B=int(rows[0].Y.sum()),disclosed_B=int(rows[1].Y.sum()),shared_cells=len(pv),shared_cell_mean_difference=float((pv[1]-pv[0]).mean()) if len(pv) else np.nan))
pd.DataFrame(strata).to_csv(A/'framing_strata_sensitivity.csv',index=False)
pd.DataFrame(cell_strata).to_csv(A/'framing_cell_strata.csv',index=False)
# Dependence-aware adjacent differences document the observed downward reversals.
adj=[]
for D,a,bx in [(0,1.,2.),(0,4.9,5.),(1,3.,4.)]:
    ia,ib=ds.index(a),ds.index(bx)
    draw=boot[:,D,ib,:].mean(axis=1)-boot[:,D,ia,:].mean(axis=1)
    lo,hi=np.quantile(draw,[.025,.975])
    adj.append(dict(D=D,delta_from=a,delta_to=bx,difference=float(mu.reshape(2,10,10)[D,ib].mean()-mu.reshape(2,10,10)[D,ia].mean()),low=float(lo),high=float(hi)))
pd.DataFrame(adj).to_csv(A/'payoff_reversal_audit.csv',index=False)
result=dict(N=len(h),paths=1000,cell_parameters=200,zero_variance_cells=int(np.sum(np.diag(cov)<1e-16)),cr1_factor=cr1,bootstrap_B=5000,bootstrap_seed=20261030,simultaneous_radius=radius,wald=wald,source_sha256=hashlib.sha256((DATA).read_bytes()).hexdigest())
(A/'audit_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('ESTIMANDS\n'+ef.to_string(index=False))
print('WALD\n'+pd.DataFrame(wald).to_string(index=False))
print('POSITIVE CELLS\n'+cf[cf.difference>0].sort_values('difference',ascending=False).head(12).to_string(index=False))
print('FINGERPRINTS\n'+fp.to_string(index=False))
print('STRATA\n'+pd.DataFrame(strata).to_string(index=False))
print('REVERSALS\n'+pd.DataFrame(adj).to_string(index=False))
print('SUMMARY\n'+json.dumps(result,indent=2))
