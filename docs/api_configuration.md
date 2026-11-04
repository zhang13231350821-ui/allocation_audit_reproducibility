# Recorded collection protocol and optional new experiments

## Recorded configuration

- Interface: Azure OpenAI `/openai/v1/chat/completions`; direct HTTPS requests, without an SDK retry layer.
- Deployment name used in the recorded run: `gpt-4o`. Returned model identifier: `gpt-4o-2024-11-20`.
- Collection: 23–24 October 2026. Temperature=0, top_p=1, max_tokens=128, n=1, store=false, stream=false.
- Sequential calls; concurrency=1; timeout=120 seconds; at most two additional transport attempts. Invalid final outcomes remain scheduled records.
- Local design seed=41; no API sampling seed. The current analysis bootstrap uses 5,000 resamples and seed=20261030.
- Each request contains exactly one system and one user message. No server conversation or previous_response_id is used. H1 history is explicitly supplied in the user content; H0 has no history.
- Equal allocation is Option A and unequal allocation is Option B throughout the recorded protocol. The recorded prompts and option mapping are fixed.

Full public settings and template/design hashes are in `data/metadata/run_metadata.json`. Exact prompt components are in `prompts/`. `src/experiment/run_experiment.py` is the joint H0/H1 collection entry point; `experiment_core.py` supplies prompts, parsing and transport. `resume_experiment.py` documents continuation using a complete private original run state.

Module/file names were made neutral; collection logic was preserved. Original and distributed source hashes are recorded in `collection_code_provenance.json`. Original collection analysis helpers document that implementation; the manuscript's current analysis is executed by `run_all.py` and `src/analysis/`.

## Inspect without model calls

```bash
python src/experiment/run_experiment.py --phase formal --preview
```

This prints the design and prompt examples without network requests or output files. The offline protocol-check step independently verifies all supplied message/payload records using the collection functions.

## Optional independent collection

A new collection requires the researcher's own compatible Azure deployment and the environment variables `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_DEPLOYMENT`. The package supplies no credentials. After configuring those variables locally:

```bash
python src/experiment/run_experiment.py --phase formal --framing both --seed 41 --model-condition independent_replication --output-root new_model_runs
```

This command sends paid model requests and is separate from offline reproduction. Future model/deployment availability and service-side behavior can change, so new outputs need not match the recorded choices. Public projections are not a substitute for the complete private state required to resume an interrupted original collection.

