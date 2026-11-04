# Reproduction guide

## Run order

Run `python run_all.py` from the package root after installing `requirements.txt` in Python 3.11. The default input is `data/processed/formal_trials.csv` and the default output is `results/`. The command also works when invoked from another working directory: relative input/output arguments are interpreted relative to the package root.

| Step | Script | Inputs | Main outputs |
|---|---|---|---|
| 0 | `src/verification/smoke_check.py` | Manifest and formal CSV | Hash, grid, validity and count checks |
| 1 | `src/analysis/01_prepare_data.py` | Scheduled-record JSONL | Reconstructed formal/seed CSVs in `prepared_data/`; equality with supplied CSVs |
| 2 | `src/analysis/02_fit_models.py` | Formal CSV | Cell proportions, Wilson intervals, M1/M2/M3 fits and coefficients, marginal/cell contrasts, paired history |
| 3 | `src/analysis/03_uncertainty_and_strata.py` | Formal CSV | Matched CR1/bootstrap intervals, Wald diagnostics, selected cells, fingerprint and collection-phase summaries |
| 4 | `src/analysis/04_verify_protocol.py` | Scheduled/attempt JSONL, prompts, original collection functions | Exact prompt/history/payload checks and targeted retry/missingness summaries |
| 5 | `src/analysis/05_export_tables.py` | Recomputed estimates and documented settings | Tables 1–3 and S1–S8 as individual CSVs, plus `manuscript_tables.csv` |
| 6 | `src/figures/plot_figures.py` | Recomputed estimates and Fig1 asset | Seven figure-source CSVs and reproduced figure assets |
| 7 | `src/verification/verify_results.py` | Generated outputs and frozen references | `verification_report.json`; nonzero exit on mismatch |

The runner invokes these scripts through `src/offline_executor.py`, which blocks network connections. It never runs model collection. The sole input to outcome analysis is the formal-trial CSV; seed rows document H1 construction and are excluded from formal outcome denominators.

## Expected assertions

- 20,000 scheduled formal records; 19,865 valid and 135 invalid outcomes.
- Valid H0=9,931; valid H1=9,934. The four condition counts match the README.
- Each H × D × Delta × g cell has 50 scheduled choices.
- Paired valid H0/H1 comparisons: 4,962 Blind and 4,965 Disclosed pairs.
- Standardized H0 framing difference −20.85 percentage points.
- Selected cells a/b/c: 13/49→49/50, 0/50→32/50 and 20/50→43/50; differences +71.47/+64.00/+46.00 points.
- Cases a/c are positive in one major fingerprint and zero in the other; b is positive in both.
- All 11 manuscript tables, five Dataset CSVs and seven figure-source tables agree with the reference values within stated rounding/tolerances.
- Wald covariance rank=9 for each nine-contrast test; 141 zero-variance H0 cells; full-grid sensitivity radius=0.28.
- 21,000 scheduled records and 21,365 attempts pass protocol/payload checks. Target checks reproduce 1,500 trials, 1,533 attempts, 1,487 HTTP-200 outcomes and 46 SSL errors.

## Figure and table mapping

| Article item | Evidence | Source/output |
|---|---|---|
| Fig1 | Equal versus positive-sum unequal alternatives and framing | `figures/Fig1.png`, `results/figure_data/Fig1_task_structure.csv` |
| Fig2, FigS1 | H0/H1 cell B-choice proportions | Dataset 1; `Fig2_cells.csv`, `FigS1_cells.csv` |
| Fig3, Fig5 | Equally weighted payoff/gap marginal profiles | `Fig3_marginal_probabilities.csv`, `Fig5_marginal_probabilities.csv` |
| Fig4, Table S7 | Cell framing contrasts; selected pooled positive differences | Dataset 3; `Fig4_cell_contrasts.csv`; `audit/cell_framing_audit.csv` |
| FigS2, Table 3 | Matched H1-minus-H0 contrasts | Dataset 4; `FigS2_paired_history.csv` |
| Tables 1, S1 | Scheduled/valid/invalid outcome accounting | Formal CSV and `manuscript_tables.csv` |
| Table 2, Table S8 | Standardized framing contrasts and matched intervals | `audit/estimand_sensitivity.csv` |
| Table S2 | Recorded API settings | `data/metadata/run_metadata.json`; payload checks in step 4 |
| Table S3 | Target-gap counts within returned fingerprints | Formal CSV; protocol and metadata analyses |
| Table S4 | Restricted/saturated model sample fit | Generated `analysis/model_fit.csv` |
| Tables S5–S6 | Fingerprint and collection-phase strata | `audit/framing_strata_sensitivity.csv` |

## Output and troubleshooting

`run_all.py` prints the current stage and writes details to `results/logs/run.log`. Missing dependencies should be installed using the same Python interpreter that runs the pipeline. If a verification step fails, retain the log and inspect the failing dataset/table; do not replace reported values manually.

Use `--output another_results` to create an independent output folder. Inputs, scripts, supplied images and frozen references are not overwritten. `MANIFEST.sha256` describes the delivered files; smoke verification checks the immutable subset because generated results can change after execution.

The data table retains all scheduled outcomes. Empty invalid Y values must not be filled with zero. Treating gaps as equally spaced sampled categories in figures does not impose a continuous response model. Zero empirical variance is not evidence of future invariance.

