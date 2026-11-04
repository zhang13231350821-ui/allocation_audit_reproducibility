# Data dictionary and units

`data_dictionary.csv` defines every column in the supplied formal and seed CSVs. It uses UTF-8 with a byte-order mark so Chinese descriptions display correctly in spreadsheet applications.

## Tables and identifiers

- `data/processed/formal_trials.csv`: 20,000 scheduled formal outcomes, including invalid records. Each row represents one model decision request after its final transport attempt.
- `data/processed/seed_trials.csv`: 1,000 H1 seed outcomes used to construct later history. Seeds are excluded from all formal sample counts.
- `trial_id` is a unique local scheduled-decision key, not a provider request identifier.
- `path_id` groups ten formal projects at a fixed Delta, D and shared index r. `path_cluster` additionally includes H. Paths are design groupings, not separate model identities.
- `pair_id` joins H0 and H1 for the same current project. Paired estimates include only pairs where both formal outcomes are valid.
- `r` is the shared path index 1–50 and the bootstrap block. `t` is formal position 1–10. H1 has t preceding records; H0 receives none.
- `source_line` is the one-based scheduled-record position including seed records. Formal records span 1001–21000; positions up to 8550 define the original collection prefix.

## Coding and units

H=0/1: no supplied history/explicit supplied history. D=0/1: Blind/Disclosed. Y=0/1: Option A/B. `valid=False` has empty Y and choice, and is excluded from binary denominators.

P=5; Delta and g are in units of RMB 10,000. Option A=(P,P); Option B=(P+Delta,P+Delta+g), with the decision maker listed first. The `g` parameter changes both the gap and the colleague's absolute payoff.

Dataset interval/difference fields and figure source values use probabilities unless a column explicitly says `pp`. `results/manuscript_tables.csv` uses the manuscript's displayed units and rounding. Wilson intervals describe cell proportions. CR1 and shared-index bootstrap intervals address the specified design dependence. Positive framing differences mean Disclosed minus Blind is positive; positive history differences mean H1 minus H0 is positive.

## Public JSONL projections

`scheduled_decisions.jsonl.gz` contains one JSON object per scheduled outcome, with trial/design keys, stage, final choice/validity, exact allocation amounts, timestamps, returned model/fingerprint, attempt links, exact messages/history and message/template hashes. `history_records_sent` and `messages_sent` retain the experimental input. `raw_output` contains the recorded response, not hidden model reasoning.

`request_attempts.jsonl.gz` contains one JSON object per attempt: local attempt ID/number, trial context, request JSON, HTTP status, parsed output, returned metadata, timing, usage and error category. It omits private service request identifiers, endpoint hosts, raw errors and authentication information. Local identifiers link the two projections.

The projections can reconstruct the processed CSVs and validate retry/missingness counts. They do not recreate the private service configuration or permit resuming the original run from public files alone.

## Derived datasets

1. Dataset 1: H × D × Delta × g counts, invalid totals, B proportions and Wilson intervals.
2. Dataset 2: M1/M2/M3 treatment-coded coefficients and CR1 inference fields. Structural zero-variance M3 terms have empty inference fields; all normalization changes are recorded in metadata.
3. Dataset 3: separate marginal and cell-contrast CSVs. Marginal families have Holm-adjusted tests; cell tables include pointwise intervals and a full-grid sensitivity band.
4. Dataset 4: paired H1-minus-H0 differences for overall, payoff-specific and gap-specific scopes, with valid-pair counts and pointwise bootstrap intervals.

`data/metadata/manuscript_tables.json` freezes the current displayed table values for independent comparison. `manuscript_snapshot.json` records manuscript/supplement and supplied-image hashes without local filenames or paths. The underlying documents are submitted separately and are not duplicated in this code/data package.

