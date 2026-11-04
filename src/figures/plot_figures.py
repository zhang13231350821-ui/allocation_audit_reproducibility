"""Recreate current-numbered statistical figures; make no model/API requests.

The exact images used in the manuscript remain in figures/.
Recreated figures are written under the selected results directory.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from package_runtime import paths
ROOT,DATA,RESULTS,OPTIONS=paths()
import shutil
import numpy as np
import pandas as pd
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.colors import LinearSegmentedColormap

A=RESULTS/'analysis';V=RESULTS/'audit'
F=RESULTS/'figures';S=RESULTS/'figure_data'
F.mkdir(parents=True,exist_ok=True);S.mkdir(parents=True,exist_ok=True)
mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','DejaVu Sans'],'font.size':9,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
CM=LinearSegmentedColormap.from_list('official_probability',['#276ABB','#E9E4E4','#AD343C'])
DC=LinearSegmentedColormap.from_list('official_contrast',['#276ABB','#F5F5F5','#AD343C'])
df=pd.read_csv(DATA);v=df[df.valid]
ds=sorted(df.Delta.unique());gs=sorted(df.g.unique())
cells=pd.read_csv(A/'cells.csv')
def save(fig,name):
    # pcolormesh produces actual vector rectangles in the heatmap exports;
    # EPS files therefore do not embed the original 49-MB raster grids.
    for ext in dict.fromkeys(['png',*OPTIONS.figure_formats]):
        fig.savefig(F/f'{name}.{ext}',dpi=600,bbox_inches='tight',facecolor='white')
    plt.close(fig)
def axis_labels(ax):
    ax.set(xticks=range(10),xticklabels=[f'{g:g}' for g in gs],yticks=range(10),yticklabels=[f'{d:g}' for d in ds],xlabel='Inequality gap g')
    ax.tick_params(axis='x',labelrotation=55,labelsize=7)
    ax.set_xlim(-.5,9.5);ax.set_ylim(-.5,9.5)
def mesh(ax,values,cmap,lo,hi):
    return ax.pcolormesh(np.arange(11)-.5,np.arange(11)-.5,values,cmap=cmap,vmin=lo,vmax=hi,edgecolors='white',linewidth=.5,shading='flat',rasterized=False)

# Figure 1 is an editorial schematic. Its supplied bitmap is the source asset,
# not an outcome estimated from trial data; no fictitious vector source is made.
shutil.copy2(ROOT/'figures/Fig1.png',F/'Fig1.png')
pd.DataFrame([{'option':'A','decision_maker_payoff':'P','colleague_payoff':'P','baseline_P':5,'amount_unit':'RMB 10,000'},
              {'option':'B','decision_maker_payoff':'P + Delta','colleague_payoff':'P + Delta + g','baseline_P':5,'amount_unit':'RMB 10,000'}]).to_csv(S/'Fig1_task_structure.csv',index=False)
for H,name in [(0,'Fig2'),(1,'FigS1')]:
    sub=cells[cells.H==H];sub.to_csv(S/f'{name}_cells.csv',index=False)
    fig,axes=plt.subplots(1,2,figsize=(11,4.3),layout='constrained',sharey=True)
    for D,ax in enumerate(axes):
        table=sub[sub.D==D].pivot(index='Delta',columns='g',values='p').reindex(index=ds,columns=gs)
        im=mesh(ax,table.to_numpy(),CM,0,1)
        for i in range(10):
            for j in range(10):
                x=table.iloc[i,j]
                ax.text(j,i,f'{x:.2f}',ha='center',va='center',fontsize=7,fontweight='bold',color='white' if abs(x-.5)>.27 else 'black')
        axis_labels(ax);ax.text(0,1.04,chr(97+D),transform=ax.transAxes,fontweight='bold')
        fig.colorbar(im,ax=ax,label='Observed P(Option B)',fraction=.035,pad=.04)
    axes[0].set_ylabel('Additional payoff Δ');save(fig,name)

arr=np.zeros((2,10,10,50,2))
for r in v[v.H==0].itertuples():arr[int(r.D),ds.index(r.Delta),gs.index(r.g),int(r.r)-1]+=[r.Y,1]
counts=np.random.default_rng(20261030).multinomial(50,np.ones(50)/50,size=5000)
raw=arr.sum(axis=3);prob=raw[...,0]/raw[...,1]
boot=np.stack([np.einsum('br,dgr->bdg',counts,arr[D,:,:,:,0])/np.einsum('br,dgr->bdg',counts,arr[D,:,:,:,1]) for D in [0,1]],axis=1)
for axis,levels,name,label,factor in [(1,ds,'Fig3','Additional payoff Δ','Delta'),(0,gs,'Fig5','Inequality gap g','g')]:
    fig,ax=plt.subplots(figsize=(6.85,3),layout='constrained');rows=[]
    for D,color,marker in [(0,'#2166AC','o'),(1,'#B2182B','s')]:
        y=prob[D].mean(axis=axis);draw=boot[:,D].mean(axis=axis+1);lo,hi=np.quantile(draw,[.025,.975],axis=0)
        ax.errorbar(range(10),y,yerr=[np.maximum(0,y-lo),np.maximum(0,hi-y)],marker=marker,color=color,capsize=2,label=['Blind','Disclosed'][D],linewidth=1)
        rows.extend(dict(D=D,framing=['Blind','Disclosed'][D],**{factor:float(level)},probability=float(p),point_low=float(l),point_high=float(h)) for level,p,l,h in zip(levels,y,lo,hi))
    pd.DataFrame(rows).to_csv(S/f'{name}_marginal_probabilities.csv',index=False)
    ax.set(xticks=range(10),xticklabels=[f'{x:g}' for x in levels],xlabel=label,ylabel='Grid-standardized P(Option B)',ylim=(-.03,1.04));ax.legend(frameon=False);ax.grid(axis='y',color='#DDDDDD',linewidth=.7);save(fig,name)

fr=pd.read_csv(V/'cell_framing_audit.csv');fr.to_csv(S/'Fig4_cell_contrasts.csv',index=False)
mat=fr.pivot(index='Delta',columns='g',values='difference').reindex(index=ds,columns=gs)
fig,ax=plt.subplots(figsize=(7.4,4.55),layout='constrained');im=mesh(ax,mat.to_numpy(),DC,-1,1)
for i in range(10):
    for j in range(10):
        x=mat.iloc[i,j];ax.text(j,i,f'{x:+.2f}',ha='center',va='center',fontsize=8.5,color='white' if abs(x)>.55 else '#111111')
for d,g,label in [(3,1000,'a'),(4.5,500,'b'),(5,500,'c')]:
    i,j=ds.index(d),gs.index(g)
    ax.add_patch(Rectangle((j-.48,i-.48),.96,.96,fill=False,ec='black',lw=1.7))
    ax.text(j-.39,i+.31,label,fontsize=8,fontweight='bold',color='black',bbox=dict(facecolor='white',edgecolor='none',pad=.5))
axis_labels(ax);ax.set_ylabel('Additional payoff Δ');fig.colorbar(im,ax=ax,label='Disclosed − blind P(Option B)',fraction=.046,pad=.04);save(fig,'Fig4')

hist=pd.read_csv(A/'paired_history.csv');sub=hist[hist.scope=='gap'];sub.to_csv(S/'FigS2_paired_history.csv',index=False)
fig,ax=plt.subplots(figsize=(6.85,3),layout='constrained')
for D,color in [(0,'#2166AC'),(1,'#B2182B')]:
    q=sub[sub.D==D].sort_values('value');ax.errorbar(np.arange(10)+(D-.5)*.12,q.difference,yerr=[q.difference-q.low,q.high-q.difference],fmt='o',color=color,label=['Blind','Disclosed'][D],capsize=2)
ax.axhline(0,color='gray',lw=.7);ax.set(xticks=range(10),xticklabels=[f'{x:g}' for x in gs],xlabel='Inequality gap g',ylabel='Paired H1 − H0 probability');ax.legend(frameon=False);save(fig,'FigS2')
print('Seven figure assets and seven source-data tables prepared; exact manuscript images preserved.')
