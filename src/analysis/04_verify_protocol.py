"""Verify public request records, exact prompts/history and targeted missingness results."""
from pathlib import Path
from collections import Counter,defaultdict
from decimal import Decimal
import gzip,hashlib,json,sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from package_runtime import paths

ROOT,DATA,RESULTS,OPTIONS=paths()
sys.path.insert(0,str(ROOT/'src/experiment'))
import run_experiment as protocol
import experiment_core as core

OUT=RESULTS/'audit';OUT.mkdir(parents=True,exist_ok=True)
source_hashes=json.loads((ROOT/'data/metadata/collection_code_provenance.json').read_text(encoding='utf-8'))
for name,record in source_hashes.items():
    assert hashlib.sha256((ROOT/'src/experiment'/name).read_bytes()).hexdigest()==record['package_sha256']
templates=json.loads((ROOT/'prompts/templates.json').read_text(encoding='utf-8'))
assert protocol.prompt_templates()==templates
metadata=json.loads((ROOT/'data/metadata/run_metadata.json').read_text(encoding='utf-8'))
assert core.sha256(templates)==metadata['template_sha256']
assert (ROOT/'prompts/system_prompt.txt').read_text(encoding='utf-8')==templates['system']
for framing,key in [(0,'blind'),(1,'disclosed')]:
    plain=(ROOT/f'prompts/{key}_prompt.txt').read_text(encoding='utf-8')
    assert plain.format(ownPay='6',colleaguePay='8')==core.current_project('1','2',framing)
assert (ROOT/'prompts/history_template.txt').read_text(encoding='utf-8')==templates['history']
forbidden={'request_url','base_url','request_headers','request_id','response_id','response_text','routing','error'}
def fields_ok(value):
    if isinstance(value,dict):
        assert not forbidden.intersection(value),forbidden.intersection(value)
        for v in value.values():fields_ok(v)
    elif isinstance(value,list):
        for v in value:fields_ok(v)

records={};stages=Counter();histories=defaultdict(list);targets={};formal=[]
with gzip.open(ROOT/'data/raw/scheduled_decisions.jsonl.gz','rt',encoding='utf-8') as f:
    for source_line,line in enumerate(f,1):
        x=json.loads(line);fields_ok(x)
        assert x['trial_id'] not in records
        assert x['model_condition']=='official_azure_gpt4o'
        stages[x['stage']]+=1
        for key,expected in [('A_you',Decimal(5)),('A_colleague',Decimal(5)),
                             ('B_you',Decimal(5)+Decimal(x['Delta'])),
                             ('B_colleague',Decimal(5)+Decimal(x['Delta'])+Decimal(x['g']))]:
            assert Decimal(x[key])==expected
        assert x['valid']==(x.get('raw_output') in ['Option A','Option B'])
        if x['valid']:assert x['Y']==int(x['raw_output']=='Option B')
        assert [m['role'] for m in x['messages_sent']]==['system','user']
        if x['H']==1 and x['stage']=='formal':
            prior=histories[x['path_id']]
            assert len(prior)==x['t']==x['history_length']
            assert x['messages_sent']==protocol.build_messages(x['Delta'],x['g'],x['D'],prior)
            assert x['history_records_sent']==prior
        else:
            assert x['messages_sent']==core.build_messages(x['Delta'],x['g'],x['D'])
            assert x['history_length']==0
        assert core.sha256(x['messages_sent'])==x['messages_sha256']
        if x['H']==1:histories[x['path_id']].append(protocol.compact_record(x))
        # Keep only fields needed to check request links, rather than duplicating all prompt strings.
        records[x['trial_id']]={k:x[k] for k in ['final_attempt_id','attempt_ids','messages_sha256','raw_output','valid','H','D','g','stage','status','retry_count']}
        if x['stage']=='formal':
            formal.append({k:x[k] for k in ['trial_id','H','D','Delta','g','r','t','Y','valid','retry_count','history_length']})
            if x['H']==0 and ((x['D']==0 and float(x['g'])==200) or (x['D']==1 and float(x['g']) in [20,200])):
                targets[x['trial_id']]=x
assert stages=={'seed':1000,'formal':20000}
assert len(records)==21000 and all(len(h)==11 for h in histories.values())
attempt_ids=set();seen_final=set();http=Counter();target_http=Counter();target_errors=Counter();attempts_per_trial=Counter()
with gzip.open(ROOT/'data/raw/request_attempts.jsonl.gz','rt',encoding='utf-8') as f:
    for line in f:
        x=json.loads(line);fields_ok(x)
        assert x['attempt_id'] not in attempt_ids
        attempt_ids.add(x['attempt_id']);tid=x['trial']['trial_id'];ref=records[tid]
        attempts_per_trial[tid]+=1
        assert x['attempt_id'] in ref['attempt_ids']
        req=x['request_json'];assert core.sha256(req)==x['request_sha256']
        assert core.sha256(req['messages'])==ref['messages_sha256']
        assert req['temperature']==0 and req['top_p']==1 and req['max_tokens']==128 and req['n']==1
        assert not req['store'] and not req['stream']
        assert 'seed' not in req and 'previous_response_id' not in req
        http[str(x['http_status'])]+=1
        if x['attempt_id']==ref['final_attempt_id']:
            seen_final.add(tid)
            if ref['valid']:assert x['parsed']['raw_output']==ref['raw_output']
        if tid in targets:
            target_http[str(x['http_status'])]+=1
            if x['error_type']:target_errors[x['error_type']]+=1
assert len(attempt_ids)==21365 and len(seen_final)==21000
assert http=={'200':20865,'None':500}
assert all(attempts_per_trial[k]==len(v['attempt_ids'])==v['retry_count']+1 for k,v in records.items())
supplied=pd.read_csv(DATA).set_index('trial_id')
for x in formal:
    row=supplied.loc[x['trial_id']]
    for key in ['H','D','r','t','retry_count','history_length']:assert int(row[key])==int(x[key])
    for key in ['Delta','g']:assert Decimal(str(row[key]))==Decimal(x[key])
    assert bool(row.valid)==x['valid']
    if x['valid']:assert row.Y==x['Y']
assert len(targets)==1500 and sum(target_http.values())==1533
assert target_http=={'200':1487,'None':46} and sum(target_errors.values())==46
retried=[x for x in targets.values() if x['retry_count']>0]
assert len(retried)==19 and sum(x['valid'] for x in retried)==6
rows=[]
for d,g in [(0,200),(1,20),(1,200)]:
    part=[x for x in targets.values() if x['D']==d and float(x['g'])==g]
    valid=[x for x in part if x['valid']];b=sum(x['Y'] for x in valid);invalid=len(part)-len(valid)
    clean=[x for x in valid if x['retry_count']==0]
    rows.append(dict(D=d,g=g,planned=len(part),valid=len(valid),B=b,invalid=invalid,
                     missing_bound_low=b/len(part),missing_bound_high=(b+invalid)/len(part),
                     no_successful_retry_n=len(clean),no_successful_retry_B=sum(x['Y'] for x in clean)))
pd.DataFrame(rows).to_csv(OUT/'targeted_missingness.csv',index=False)
assert (rows[0]['B'],rows[0]['valid'])==(492,492)
assert (rows[1]['B'],rows[1]['valid'])==(19,497)
assert (rows[2]['B'],rows[2]['valid'])==(436,498)
assert (rows[0]['no_successful_retry_B'],rows[0]['no_successful_retry_n'])==(486,486)
report={'scheduled_records':21000,'formal_records':20000,'seed_records':1000,
        'attempts':21365,'http_status_counts':dict(http),
        'exact_prompt_and_history_checks':21000,'exact_attempt_payload_checks':21365,
        'targeted_trials':1500,'targeted_attempts':1533,'targeted_http_200':1487,
        'targeted_ssl_errors':46,'targeted_error_types':dict(target_errors),
        'targeted_retried_trials':19,'targeted_success_after_retry':6,'targeted_final_failures_after_retry':13,
        'privacy_field_whitelist':'passed','collection_source_hashes':'passed',
        'public_projection':'de-identified; private service identifiers omitted',
        'network_access':'disabled'}
(OUT/'protocol_verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))

