"""Reconstruct formal and seed tables from de-identified scheduled records."""
from pathlib import Path
import csv,gzip,json,sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from package_runtime import paths

ROOT,DATA,RESULTS,OPTIONS=paths()
formal_columns=['trial_id','path_id','pair_id','r','Delta','D','H','t','g','status','choice','Y','valid','retry_count','response_model','system_fingerprint','started_utc','ended_utc','history_length','history_contains_invalid_prior','source_line','path_cluster']
seed_columns=['trial_id','path_id','r','Delta','D','H','g','choice','Y','valid','status','retry_count','response_model','system_fingerprint','started_utc','ended_utc','A_you','A_colleague','B_you','B_colleague']
formal=[];seeds=[]
with gzip.open(ROOT/'data/raw/scheduled_decisions.jsonl.gz','rt',encoding='utf-8') as f:
    for source_line,line in enumerate(f,1):
        x=json.loads(line)
        if x['stage']=='formal':
            row={key:x.get(key) for key in formal_columns}
            row['source_line']=source_line
            row['path_cluster']=str(x['H'])+'_'+x['path_id']
            formal.append(row)
        elif x['stage']=='seed':seeds.append({key:x.get(key) for key in seed_columns})
assert len(formal)==20000 and len(seeds)==1000
out=RESULTS/'prepared_data';out.mkdir(parents=True,exist_ok=True)
a=pd.DataFrame(formal,columns=formal_columns);b=pd.DataFrame(seeds,columns=seed_columns)
a.to_csv(out/'formal_trials.csv',index=False);b.to_csv(out/'seed_trials.csv',index=False)
aa=pd.read_csv(out/'formal_trials.csv');bb=pd.read_csv(DATA)
pd.testing.assert_frame_equal(aa,bb,check_dtype=False)
pd.testing.assert_frame_equal(pd.read_csv(out/'seed_trials.csv'),pd.read_csv(ROOT/'data/processed/seed_trials.csv'),check_dtype=False)
print('Reconstructed formal/seed tables match the supplied processed data; immutable inputs unchanged.')
