# Pharma Feature Extractor

Turning Health Canada drug product monographs from PDFs into structured,
queryable clinical data, using LLMs to read what regulatory documents actually
say, rather than parsing them by rule.

Monographs are the authoritative source for what a drug is indicated for, who
must not take it, what it interacts with, and how dosing changes in liver or
kidney impairment. That information is locked in prose across more than a
thousand documents, in inconsistent formats, from dozens of manufacturers.

> Part of MSc research at Western University. Two papers in preparation.

## The project

| Repository | Role |
|---|---|
| **Pharma_Feature_Extractor** *(this repo)* | **Extraction.** This pipeline |
| [pharma_pattern_models](https://github.com/BerlinTheWall/pharma_pattern_models) | **Experiments.** Clustering, prediction and anomaly detection over the output |
| [Pharma_Monograph_Visualization](https://github.com/BerlinTheWall/Pharma_Monograph_Visualization) | **The interface.** Flask API and interactive D3.js explorer |

## Corpus

| | |
|---|---|
| Monographs | 1,433, from Health Canada's Drug Product Database (January 2026) |
| Therapeutic classes | 19 |
| Generic drugs | 53 |
| Manufacturers | 62 |
| Fields per monograph | 23, from 14 extractors |

Four monographs are scanned PDFs with almost no text. They are in the dataset
but marked, since most of their list fields did not come from the document.

## How it works

```
Monograph PDF
     │
     ▼
PyPDF2 text extraction
     │
     ▼
Locate the section for each field
     │
     ▼
Field-specific prompt  ──►  LLM (local Ollama by default)
     │                        │
     │              categorical fields → constrained to a fixed category set
     │              list fields        → comma-separated list of short terms
     ▼
Structured record (23 fields)
```

Each extractor has its own prompt rather than one prompt for the whole
document. Categorical fields (dose adjustment in liver and kidney impairment,
pregnancy and breastfeeding recommendation) are constrained to a fixed set of
allowed answers. Lists such as adverse events and drug interactions are
returned as short terms, and an answer that is prose instead of a list is
rejected and asked again. Drug class and generic name come from the folder
structure, and metabolism (CYP enzymes) is found by text search, without a
model call.

### Models

By default the pipeline talks to a local [Ollama](https://ollama.com) server,
so no monograph text leaves the machine and no API key is needed. Any
OpenAI-compatible endpoint can be set instead (`PHARMA_EXTRACTOR_BASE_URL`).

| Model | Used for |
|---|---|
| Llama 3.1 8B | Producing the released dataset; evaluation |
| Mistral 7B | Evaluation; default model of this repository |
| Qwen 2.5 7B | Evaluation |

The released dataset was produced with Llama 3.1 8B on a hosted service
(Cerebras). All evaluation runs were local, on Ollama, with a 32,768-token
context and a 2,048-token answer limit (`paper/heldout/runs/modelfiles/`).

### Two versions of the pipeline

- **Original pipeline:** the package at the root of this repository, as tagged
  `paper-original`. It finds each field's section through the table of contents
  and keyword search, and it produced the released dataset. The `main` branch
  has since added checkpointing, an input-length cap and list validation; these
  were not used for any reported result.
- **Improved version:** [`paper/v3/`](paper/v3/) (tag `paper-final`). It locates
  sections from the PDF bookmarks and splits long sections before sending them
  to the model, for the nine evaluated fields. Its code was frozen on
  November 6, 2026, before the test-set runs, and `paper/v3/FROZEN.txt` holds
  the SHA-256 of each file.

## Evaluation

Nine fields were evaluated against manually annotated correct answers:

- **Categorical:** liver and kidney dose adjustment, pregnancy and
  breastfeeding recommendation
- **Lists:** indications, contraindications, serious warnings and precautions,
  adverse events, drug interactions

Two sets of 20 monographs were annotated, each with one monograph per
therapeutic class plus a second from the largest class:

- a **development set**, used while building the improved version;
- a **test set**, drawn at random with a fixed seed (20261005) after excluding
  the development monographs, other strengths of the same products and
  unreadable files.

List items are matched to the correct answers semantically, using PubMedBERT
embeddings. Results are reported with 95% confidence intervals (bootstrap over
monographs for lists, Wilson intervals for categorical accuracy), with paired
comparisons of the two pipeline versions, and with recall on clinically
critical items checked at three matching thresholds. The scripts are in
[`paper/results_ci/`](paper/results_ci/).

## Findings

The full results are in the paper (in preparation). The points below come from
the development set; the test-set results are not final yet.

- **The original pipeline misses part of the listed items.** Adverse events,
  contraindications, drug interactions and indications all lose some of the
  items listed in the monograph.
- **Serious warnings had a low recall** in the original pipeline, because it read
  them from two fixed pages of each monograph.
- **The improved version has a higher recall.** Locating sections from the PDF
  bookmarks and splitting long sections are what changed.

## Limitations

- Each evaluation set has 20 monographs, so individual percentages carry wide
  confidence intervals.
- Only 9 of the 23 fields were evaluated.
- The released dataset comes from the original pipeline, not the improved
  version.
- Scanned monographs give the pipeline almost no text to read.

## Repository layout

```
run.py                entry point (CLI)
pipeline.py           orchestration, resume and checkpointing
checkpoint.py         crash-safe JSONL record store
api_client.py         LLM API layer, list validation and retry
pdf_utils.py          PyPDF2 text extraction
prompts.py            field-specific prompts
*_extractor.py        one extractor per field category
output_format.py      builds the output spreadsheet
config.py.example     configuration template, all env-overridable (copy to config.py)
notify.py             completion beep, no-op where unsupported
run_extraction.bat    supervised unattended launcher (Windows)
RUNNING_LONG_JOBS.md  procedure for a full-corpus run on another machine
requirements.txt      Python dependencies
LICENSE               MIT License
paper/                code behind the paper's results, including the improved version
```

## Running it

```bash
git clone https://github.com/BerlinTheWall/Pharma_Feature_Extractor.git
cd Pharma_Feature_Extractor
pip install -r requirements.txt
cp config.py.example config.py   # Windows: copy config.py.example config.py

ollama pull mistral

python run.py "path/to/Product monograph" --limit 2   # smoke test
python run.py "path/to/Product monograph"             # full run
```

The target folder is walked recursively, so one invocation covers the whole
`<class>/<generic>/*.pdf` corpus. Output and a resume checkpoint go to
`output/`. To use another model, set `PHARMA_EXTRACTOR_MODEL`, for example
`PHARMA_EXTRACTOR_MODEL=llama3.1:8b`. Ollama's default context is 4,096 tokens;
see the notes in `config.py.example` before raising the input length.

### Long runs

A full-corpus pass is about 20,000 model calls and takes days. Every finished
PDF is checkpointed to JSONL before the next begins, so an interrupted run
resumes rather than restarting: rerun the same command and it skips what is
done.

For an unattended run on a dedicated machine, including the supervised
auto-restart launcher, see **[RUNNING_LONG_JOBS.md](RUNNING_LONG_JOBS.md)**.

## Data

The monographs are public Health Canada regulatory filings and are not included
in this repository. The released dataset is not in this repository either; it
will be published separately under CC BY 4.0. The scripts that build it and its
description are in [`paper/release/`](paper/release/DATA_README.md).

The data was extracted automatically and contains errors. It is for research
only and must not be used for clinical decisions.

## License

The code is released under the [MIT License](LICENSE).
