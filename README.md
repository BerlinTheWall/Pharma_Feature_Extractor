# Pharma Feature Extractor

Turning Health Canada drug product monographs from PDFs into structured,
queryable clinical data, using LLMs that run locally to read what regulatory
documents actually say, rather than parsing them by rule.

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
| PDF files | 1,435, from Health Canada's Drug Product Database (January 2026) |
| Distinct monographs | 1,434 (one monograph was filed under two drugs) |
| Rows in the released dataset | 1,433 (one scanned monograph could not be read) |
| Therapeutic classes | 19 |
| Generic drugs | 53 |
| Manufacturers | 62 |
| Fields per monograph | 23, from 14 extractors |

Four other monographs are scanned PDFs with almost no text. They are in the
dataset but marked, since most of their list fields did not come from the
document.

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
Field-specific prompt  ──►  local LLM (Ollama)
     │                        │
     │              categorical fields → constrained to a fixed category set
     │              list fields        → comma-separated list of short terms
     ▼
Structured record (23 fields)
```

Each field gets its own prompt rather than one prompt for the whole document.
Categorical fields (dose adjustment in liver and kidney impairment, pregnancy
and breastfeeding recommendation) are constrained to a fixed set of allowed
answers. Lists such as adverse events and drug interactions are returned as
short terms, and an answer that is prose instead of a list is rejected and
asked again.

### Everything runs locally

All models run on a local [Ollama](https://ollama.com) server. No monograph text
is sent to a hosted API and no API key is needed.

| Model | Used for |
|---|---|
| Llama 3.1 8B | Producing the released dataset; evaluation |
| Mistral 7B | Evaluation; default model of this repository |
| Qwen 2.5 7B | Evaluation |

For the evaluation runs, each model was given a 32,768-token context and a
2,048-token answer limit (`paper/heldout/runs/modelfiles/`).

### Two versions of the pipeline

- **Original pipeline:** the package at the root of this repository (tag
  `paper-original`). It finds each field's section by keyword search, and it
  produced the released dataset.
- **Final version:** [`paper/v3/`](paper/v3/). It locates sections from the PDF
  bookmarks and splits long sections before sending them to the model, for the
  nine evaluated fields. Its code was frozen on November 6, 2026, before the
  held-out evaluation, and `paper/v3/FROZEN.txt` holds the SHA-256 of each file.

## Evaluation

Nine fields were evaluated against manually annotated gold standards:

- **Categorical:** liver and kidney dose adjustment, pregnancy and
  breastfeeding recommendation
- **Lists:** indications, contraindications, serious warnings and precautions,
  adverse events, drug interactions

Two sets of 20 monographs were annotated, each with one monograph per
therapeutic class plus a second from the largest class:

- a **development set**, used while building the final version;
- a **held-out test set**, drawn at random with a fixed seed (20261005) after
  excluding the development monographs, other strengths of the same products and
  unreadable files.

List items are matched to the gold standard semantically, using PubMedBERT
embeddings. Results are reported with 95% confidence intervals (bootstrap over
monographs for lists, Wilson intervals for categorical accuracy), with paired
comparisons of the two pipeline versions, and with recall on clinically
critical items checked at three matching thresholds. The scripts are in
[`paper/results_ci/`](paper/results_ci/).

## Findings

The full results are in the paper (in preparation). In short:

- **The original pipeline misses part of the listed items.** Adverse events,
  contraindications, drug interactions and indications all lose some of the
  items listed in the monograph.
- **Serious warnings had a low recall** in the original pipeline, because it read
  them from two fixed pages of each monograph.
- **The final version has a higher recall.** Locating sections from the PDF
  bookmarks and splitting long sections are what changed.

## Limitations

- Each evaluation set has 20 monographs, so individual percentages carry wide
  confidence intervals.
- Only 9 of the 23 fields were evaluated.
- The released dataset comes from the original pipeline, not the final version.
- Scanned monographs give the pipeline almost no text to read.

## Repository layout

```
run.py                entry point (CLI)
pipeline.py           orchestration, resume and checkpointing
checkpoint.py         crash-safe JSONL record store
api_client.py         LLM API layer
pdf_utils.py          PyPDF2 text extraction
prompts.py            field-specific prompts
*_extractor.py        one extractor per field category
output_format.py      builds the output spreadsheet
config.py.example     configuration template, all env-overridable (copy to config.py)
notify.py             completion beep, no-op where unsupported
run_extraction.bat    supervised unattended launcher (Windows)
RUNNING_LONG_JOBS.md  procedure for a full-corpus run on another machine
paper/                code behind the paper's results, including the final version
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
`output/`. To use another local model, set `PHARMA_EXTRACTOR_MODEL`, for example
`PHARMA_EXTRACTOR_MODEL=llama3.1:8b`.

### Long runs

A full-corpus pass is about 20,000 model calls (14 per PDF) and takes days.
Every finished PDF is checkpointed to JSONL before the next begins, so an
interrupted run resumes rather than restarting: rerun the same command and it
skips what is done.

For an unattended run on a dedicated machine, including the supervised
auto-restart launcher, see **[RUNNING_LONG_JOBS.md](RUNNING_LONG_JOBS.md)**.

## Data

The monographs are public Health Canada regulatory filings and are not included
in this repository. The released dataset and its description are built by the
scripts in [`paper/release/`](paper/release/DATA_README.md).

The data was extracted automatically and contains errors. It is for research
only and must not be used for clinical decisions.

## License

The code is released under the [MIT License](LICENSE).
