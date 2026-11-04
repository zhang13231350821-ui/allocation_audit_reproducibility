"""Reproduce descriptive summaries, fitted models, framing and paired-history estimates."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from package_runtime import paths
ROOT,DATA,RESULTS,OPTIONS=paths()
import json
import numpy as np,pandas as pd,statsmodels.api as sm,statsmodels.formula.api as smf
from scipy.special import expit
from scipy.stats import norm,chi2
from statsmodels.stats.multitest import multipletests
from patsy import build_design_matrices
OUT=RESULTS/'analysis';OUT.mkdir(parents=True,exist_ok=True)
df=pd.read_csv(DATA);assert len(df)==20000 and df.valid.sum()==19865
v=df[df.valid].copy();h0=v[v.H==0].copy();h1=v[v.H==1].copy();h0['lg']=np.log(h0.g)
def agg(frame,keys):
 g=frame.groupby(keys,observed=True).Y.agg(['size','sum']).reset_index().rename(columns={'size':'n','sum':'B'});g['p']=g.B/g.n;z=norm.ppf(.975);den=1+z*z/g.n;mid=(g.p+z*z/(2*g.n))/den;half=z*np.sqrt(g.p*(1-g.p)/g.n+z*z/(4*g.n*g.n))/den;g['wilson_low']=mid-half;g['wilson_high']=mid+half;return g
cells=agg(v,['H','D','Delta','g']);cells['planned']=50;cells['invalid']=50-cells.n;cells.to_csv(OUT/'cells.csv',index=False)
overall=agg(v,['H','D']);overall.to_csv(OUT/'overall.csv',index=False)
agg(v,['H','D','Delta']).to_csv(OUT/'by_delta.csv',index=False);agg(v,['H','D','g']).to_csv(OUT/'by_gap.csv',index=False)
finger=v.groupby(['H','D','system_fingerprint']).Y.agg(['size','sum']).reset_index();finger.to_csv(OUT/'fingerprints.csv',index=False)
def canonical_saturated(result,data):
 # The cell-indicator representation is algebraically identical to saturated OLS.
 # Computing score sums before the basis change preserves structural zero variances.
 ds=sorted(data.Delta.unique());gs=sorted(data.g.unique())
 grid=pd.DataFrame([(D,d,g) for D in [0,1] for d in ds for g in gs],columns=['D','Delta','g'])
 design=np.asarray(build_design_matrices([result.model.data.design_info],grid)[0])
 transform=np.rint(np.linalg.inv(design)).astype(int)
 assert np.array_equal(transform@design,np.eye(200))
 cell=np.array([int(r.D)*100+ds.index(r.Delta)*10+gs.index(r.g) for r in data.itertuples()])
 count=np.bincount(cell,minlength=200);means=np.bincount(cell,weights=data.Y,minlength=200)/count
 path=pd.Categorical(data.path_cluster,categories=sorted(data.path_cluster.unique())).codes
 scores=np.zeros((1000,200));np.add.at(scores,(path,cell),(data.Y.to_numpy()-means[cell])/count[cell])
 factor=1000/999*(len(data)-1)/(len(data)-200)
 coefficient_scores=scores@transform.T
 covariance=factor*coefficient_scores.T@coefficient_scores
 result._results.params=transform@means
 result._results.cov_params_default=covariance
 result._results._cache.clear()
 result.cell_means=means;result.cell_covariance=factor*scores.T@scores
 return result

models={};fits=[];coefs=[];tests=[]
for name,formula in [('M1','Y ~ D + Delta + lg + D:Delta + D:lg'),('M2','Y ~ D + C(Delta) + C(g)'),('M3','Y ~ D * C(Delta) * C(g)')]:
 m=smf.ols(formula,data=h0).fit(cov_type='cluster',cov_kwds={'groups':h0.path_cluster})
 if name=='M3':m=canonical_saturated(m,h0)
 assert np.isfinite(m.params).all();models[name]=m
 fits.append(dict(model=name,formula=formula,n=len(h0),paths=h0.path_cluster.nunique(),parameters=len(m.params),loglik=m.llf,deviance=float(m.ssr),AIC=m.aic,converged=True,max_abs_coef=abs(m.params).max()))
 for term,b,se,p in zip(m.params.index,m.params,m.bse,m.pvalues):
  boundary=not np.isfinite(se) or se<1e-12
  coefs.append(dict(model=name,term=term,beta=b,cluster_se=0.0 if boundary else se,p=None if boundary else p,low=None if boundary else b-1.96*se,high=None if boundary else b+1.96*se,variance_status='boundary_no_empirical_variation' if boundary else 'estimated'))
 print(name,fits[-1],flush=True)
m=models['M3'];terms=list(m.params.index)
pd.DataFrame(fits).to_csv(OUT/'model_fit.csv',index=False);pd.DataFrame(coefs).to_csv(OUT/'coefficients.csv',index=False);pd.DataFrame(tests).to_csv(OUT/'interaction_tests.csv',index=False)
ds=sorted(df.Delta.unique());gs=sorted(df.g.unique());grid=pd.DataFrame([(D,d,g) for D in [0,1] for d in ds for g in gs],columns=['D','Delta','g'])
X=np.eye(200);mu=m.cell_means;cov=m.cell_covariance;grid['pred']=mu
grad=X;se=np.sqrt(np.maximum(0,np.einsum('ij,jk,ik->i',grad,cov,grad)));grid['low']=np.maximum(0,mu-1.96*se);grid['high']=np.minimum(1,mu+1.96*se);grid.to_csv(OUT/'model_predictions.csv',index=False)
effects=[];marginal_grads={}
for scope,key in [('overall',None),('delta','Delta'),('gap','g')]:
 for value in ([None] if key is None else (ds if key=='Delta' else gs)):
  idx0=np.where((grid.D==0)&(True if key is None else grid[key]==value))[0];idx1=idx0+100
  diff=float(np.mean(mu[idx1]-mu[idx0]));gg=np.mean(grad[idx1]-grad[idx0],axis=0);ss=float(np.sqrt(max(0,gg@cov@gg)));pv=2*norm.sf(abs(diff/ss)) if ss>1e-10 else None;marginal_grads[scope,value]=gg;effects.append(dict(scope=scope,value=value,difference=diff,se=ss,low=diff-1.96*ss,high=diff+1.96*ss,p=pv))
for scope in ['delta','gap']:
 ix=[i for i,r in enumerate(effects) if r['scope']==scope];adj=multipletests([effects[i]['p'] if effects[i]['p'] is not None else 1 for i in ix],method='holm')[1]
 for i,pval in zip(ix,adj):effects[i]['holm_p']=pval
for scope,levels in [('delta',ds),('gap',gs)]:
 R=np.asarray([marginal_grads[scope,val]-marginal_grads[scope,levels[0]] for val in levels[1:]])
 z=R@mu;vc=R@cov@R.T;stat=float(z@np.linalg.solve(vc,z))
 tests.append(dict(test='framing_'+scope,chi2=stat,df=len(R),p=float(chi2.sf(stat,len(R)))))
for r,pv in zip(tests,multipletests([r['p'] for r in tests],method='holm')[1]):r['holm_p']=pv
pd.DataFrame(tests).to_csv(OUT/'interaction_tests.csv',index=False)
pd.DataFrame(effects).to_csv(OUT/'model_marginal_effects.csv',index=False)
# Saturated cell means and shared-index bootstrap used for the exploratory reanalysis.
arrays=np.zeros((2,2,10,10,50,2))
for _,r in v.iterrows():arrays[int(r.H),int(r.D),ds.index(r.Delta),gs.index(r.g),int(r.r)-1]+= [r.Y,1]
rng=np.random.default_rng(20261030);B=5000;boot=np.empty((B,2,2,10,10));counts=rng.multinomial(50,np.ones(50)/50,size=B)
for h in [0,1]:
 for D in [0,1]:
  num=np.einsum('br,dgr->bdg',counts,arrays[h,D,:,:,:,0]);den=np.einsum('br,dgr->bdg',counts,arrays[h,D,:,:,:,1]);boot[:,h,D]=num/den
raw=arrays.sum(axis=4);pr=raw[...,0]/raw[...,1];fd=pr[0,1]-pr[0,0];bd=boot[:,0,1]-boot[:,0,0];radius=np.quantile(np.max(abs(bd-fd),axis=(1,2)),.95)
fr=[dict(Delta=d,g=g,blind=pr[0,0,i,j],disclosed=pr[0,1,i,j],difference=fd[i,j],point_low=np.quantile(bd[:,i,j],.025),point_high=np.quantile(bd[:,i,j],.975),simult_low=max(-1,fd[i,j]-radius),simult_high=min(1,fd[i,j]+radius)) for i,d in enumerate(ds) for j,g in enumerate(gs)]
pd.DataFrame(fr).to_csv(OUT/'framing_cell_differences.csv',index=False)
# Paired history comparison uses only pairs with both valid, not separately pooled valid means.
pairs=v.pivot(index='pair_id',columns='H',values='Y').dropna();meta=v.drop_duplicates('pair_id').set_index('pair_id')[['D','Delta','g','r']];pairs=pairs.join(meta);pairs['diff']=pairs[1]-pairs[0]
hist=[]
for D in [0,1]:
 for scope,key,vals in [('overall',None,[None]),('gap','g',gs),('delta','Delta',ds)]:
  for value in vals:
   sub=pairs[(pairs.D==D)&(True if key is None else pairs[key]==value)];nums=sub.groupby('r')['diff'].sum().reindex(range(1,51),fill_value=0).to_numpy();dens=sub.groupby('r')['diff'].size().reindex(range(1,51),fill_value=0).to_numpy();draw=(counts@nums)/(counts@dens);hist.append(dict(D=D,scope=scope,value=value,n=len(sub),difference=sub['diff'].mean(),low=np.quantile(draw,.025),high=np.quantile(draw,.975)))
pd.DataFrame(hist).to_csv(OUT/'paired_history.csv',index=False)
# Fingerprint and transport sensitivities: descriptive only, no adjustment can identify unobserved backend state.
agg(v[v.retry_count==0],['H','D']).to_csv(OUT/'no_retry.csv',index=False)
agg(v[v.system_fingerprint=='fp_bbfb354875'],['H','D','g']).to_csv(OUT/'main_fingerprint.csv',index=False)
agg(v[v.system_fingerprint=='fp_eef51934d2'],['H','D','g']).to_csv(OUT/'second_fingerprint.csv',index=False)

print('Descriptive summaries, fitted models and paired-history estimates complete.')
