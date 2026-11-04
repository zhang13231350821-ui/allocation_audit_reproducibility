# Allocation audit reproducibility package

Supporting materials for *Economic Incentives and Fairness Framing in GPT-4o Allocation Decisions: An Exploratory Behavioral Audit*.

**中文使用入口：**先查看根目录的 `FILE_GUIDE.csv`，其中逐项说明每个文件的作用和对应论文位置。安装依赖后执行下面的一键复现命令。此包为本地核对版本，尚未上传；作者引用信息、开放许可和固定发布链接将在作者确认后补齐。

## Quick start

Tested with **Python 3.11.7** in a fresh virtual environment, with the exact package versions in `requirements.txt`.

```bash
python -m venv .venv
```

Activate `.venv` using `.venv\Scripts\activate` on Windows, or `source .venv/bin/activate` on macOS/Linux. Then run:

```bash
python -m pip install -r requirements.txt
python run_all.py --smoke-test
python run_all.py --data data/processed/formal_trials.csv --output results
```

The smoke check uses only the Python standard library and checks immutable file hashes, the grid, record counts and invalid-outcome coding. The complete workflow reconstructs processed data, fits the models, computes CR1/bootstrap estimates, verifies exact prompts/history and archived request payloads, exports tables, recreates figures and checks the results.

**No model/API requests are made by `run_all.py`.** Network connections are disabled in every offline step. Installing dependencies initially requires access to the package index, unless packages are already available locally. The complete analysis is normally a few minutes; runtime depends on hardware.

## Contents

| Directory or file | Contents |
|---|---|
| `data/raw/` | De-identified public projections: 21,000 scheduled outcomes and 21,365 request attempts, including exact experimental messages and recorded A/B outputs |
| `data/processed/` | 20,000 formal rows and a separate 1,000-row seed table |
| `data/derived/` | Supplementary Datasets 1–4; Dataset 3 has separate marginal and cell-contrast CSVs |
| `data/metadata/` | Recorded configuration, manuscript table/image snapshots, collection-source hashes and zero-variance normalization provenance |
| `prompts/` | System, Blind, Disclosed and H1-history templates, with exact original components in JSON |
| `src/experiment/` | Original collection/continuation logic, with neutral module names |
| `src/analysis/` | Data preparation, fitted models, uncertainty, metadata/transport sensitivity and table export |
| `src/figures/` | Figure generation from reproduced data; Fig1 uses its supplied schematic asset |
| `src/verification/` | Smoke checks and assertions against reported results |
| `figures/` | The seven PNG images actually embedded in the current manuscript and supplement |
| `results/` | Verified table compilation, figure-source CSVs, sensitivity outputs and verification report |
| `docs/` | Data dictionary, reproduction guide, API configuration and review status |
| `FILE_GUIDE.csv` | Chinese explanation of every delivered file |
| `MANIFEST.sha256` | SHA-256 hashes of the delivered files, excluding the manifest itself |

## Numerical checks

| Condition | Scheduled | Valid | Invalid | Option B |
|---|---:|---:|---:|---:|
| H0 Blind | 5,000 | 4,963 | 37 | 3,960 |
| H0 Disclosed | 5,000 | 4,968 | 32 | 2,932 |
| H1 Blind | 5,000 | 4,965 | 35 | 3,807 |
| H1 Disclosed | 5,000 | 4,969 | 31 | 2,912 |

The equally weighted H0 framing difference is −20.85 percentage points. The three selected local contrasts are +71.47, +64.00 and +46.00 points. The complete checks also cover all numerical fields in Tables 1–3 and S1–S8, Datasets 1–4, covariance ranks, matched CR1/bootstrap intervals, missingness, paired histories and fingerprint/collection-phase strata.

H=0/1 means no supplied history/explicit supplied history; D=0/1 means Blind/Disclosed; Y=0/1 means A/B. Invalid Y is missing. P=5; P, Delta and g use units of RMB 10,000. Difference/interval fields generally use probability units; exported manuscript tables use percentage points. Column definitions are in `docs/data_dictionary.csv`.

## Outputs and figures

The small delivered `results/` subset contains the numerical outputs needed for inspection. Running the complete workflow also creates `results/analysis/`, `results/prepared_data/`, `results/tables/`, `results/figures/` and `results/logs/`. Reconstructed CSVs and fitted-model internals are generated on demand. The consolidated table file is `results/manuscript_tables.csv`.

The supplied `figures/` PNGs are preserved byte-for-byte. Statistical figure scripts reproduce their numerical content in `results/figures/`; font or layout details may differ from manuscript artwork. Figure 1 is a schematic supplied as an image asset and is copied exactly, rather than estimated from outcomes. No older editable approximation is presented as its final source.

Additional vector exports can be requested when needed:

```bash
python run_all.py --output results --figure-formats png pdf svg eps
```

Only one copy of each manuscript image is included in this review package. Numerical figure-source CSVs are in `results/figure_data/`.

## Protocol, scope and provenance

The public records retain experimental choices, exact prompt/history content, local trial/attempt keys and relevant model metadata. Private service URLs, credentials, account/resource identifiers, service request/response identifiers and raw error messages are excluded. Public records are de-identified projections of the archived records, rather than unmodified private service logs.

Current analysis uses the saturated cell-mean representation, path-CR1 covariance and a 5,000-resample shared-index bootstrap with seed 20261030. The sensitivity band describes the specified resampling scheme; it is not a family-wise guarantee under arbitrary hidden backend dependence. Fixed option mapping and fingerprint limitations are retained in the manuscript.

Dataset 2 has consistent empty inference fields for structural zero-variance M3 coefficients. The normalization provenance records every changed field; coefficient point estimates and manuscript table numbers are unchanged. This avoids interpreting floating-point covariance artefacts as nonzero empirical variation.

For an optional new model experiment, see `docs/api_configuration.md`. Collection requires independent deployment access. Model availability and service-side outputs may change. The original collection modules retain their contemporaneous analysis helpers; the current manuscript estimates are reproduced by `src/analysis/`, not by those older collection helpers.

Only the current official-API study supports this package's analysis. Historical temperature, cross-model, third-party and organizational-pilot datasets are excluded. The package contains no manuscript drafts, environments, caches or internal revision reports.

