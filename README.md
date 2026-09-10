# Pharma Feature Extractor

Turning 1,435 Health Canada drug product monographs from PDFs into structured,
queryable clinical data — using LLMs to read what regulatory documents actually
say, rather than parsing them by rule.

Monographs are the authoritative source for what a drug is indicated for, who
must not take it, what it interacts with, and how dosing changes in liver or
kidney impairment. That information is locked in prose across thousands of
documents, in inconsistent formats, from dozens of manufacturers. This pipeline
unlocks it.

> Part of MSc research at Western University. Two papers in preparation.

## The project

| Repository | Role |
|---|---|
| **Pharma_Feature_Extractor** *(this repo)* | **Extraction.** This pipeline |
| [pharma_pattern_models](https://github.com/BerlinTheWall/pharma_pattern_models) | **Experiments.** Clustering, prediction and anomaly detection over the output |
| [Pharma_Monograph_Visualization](https://github.com/BerlinTheWall/Pharma_Monograph_Visualization) | **The product.** Flask API and interactive D3.js explorer |

## Scale

| | |
|---|---|
| Source monographs | 1,435 PDFs |
| Structured records produced | ~1,434 |
| Therapeutic classes | 19 |
| Generic drugs | 53 |
| Manufacturers | 62 |
| Extracted field categories | 13 |

## How it works

```
Monograph PDF
     │
     ▼
PyPDF2 text extraction
     │
     ▼
Keyword and section search  ──►  locate the region for each field
     │
     ▼
Field-specific prompt  ──►  LLM
     │                        │
     │              categorical fields → constrained to a fixed category set
     │              list fields        → open-ended, comma-separated
     ▼
Structured record (13 field categories)
```

Each field gets its own prompt rather than one prompt for the whole document.
Categorical fields — dose adjustment in hepatic impairment, pregnancy
recommendation — are constrained to a fixed set of allowed outputs. Open-ended
fields like adverse events and drug interactions are extracted as free lists.

### Models

| Model | Inference |
|---|---|
| Llama 3.1-8B | Cerebras-hosted |
| Mistral 7B | Local |
| Qwen 2.5 7B | Local |

## Evaluation

Output was compared against a manually reviewed gold standard.

### Categorical field accuracy

| Field | Llama 3.1-8B (Cerebras) | Mistral 7B | Qwen 2.5 7B |
|---|---|---|---|
| Liver dose adjustment | 40.0% | **45.0%** | 25.0% |
| Kidney dose adjustment | **55.0%** | 45.0% | 40.0% |
| Pregnancy recommendation | **30.0%** | 20.0% | **30.0%** |
| Breastfeeding recommendation | 16.7% | **22.2%** | **22.2%** |

### Critical-item recall

The gap between recall on a clinically important subset and recall overall.
Positive means important items are caught *more* reliably than average.

| System | Adverse events | Contraindications |
|---|---|---|
| Llama 3.1-8B (Cerebras) | +4.8pp | +9.5pp |
| Mistral 7B | **+11.3pp** | +9.4pp |
| Qwen 2.5 7B | −6.0pp | +7.3pp |
| Qwen 2.5 7B (v2 pipeline) | **−10.7pp** | **+14.3pp** |

## Findings

**Categorical extraction is not yet reliable enough for clinical use.** Accuracy
ranges from 16.7% to 55%. No configuration reaches what a regulatory application
would require. This is the central result, and it is a useful one — it
establishes that general-purpose 7–8B models with prompt-based extraction are not
sufficient for this task without further work.

**No single model wins.** Llama leads on kidney dose adjustment, Mistral on liver
dose and breastfeeding, pregnancy is a tie. Model choice is field-dependent,
which argues for per-field selection rather than one model for the whole
pipeline.

**A local model matches a hosted one.** Mistral 7B, running locally at no
per-token cost, performs comparably to Cerebras-hosted Llama 3.1-8B and has the
best critical-item recall of anything tested. Where sending regulatory data to a
third-party API is not acceptable — which is common in this domain — that
matters more than a small accuracy difference.

**Qwen under-catches clinically important adverse events.** Both variants score
negative on adverse-event critical recall, −6.0pp and −10.7pp. The items that
matter most clinically are the ones most likely to be missed. In a
pharmacovigilance context that is a safety characteristic, not a performance
detail.

**Contraindication recall is reassuring.** Every system catches important
contraindications more reliably than average. Where overall contraindication
extraction drops, the loss falls on low-importance items rather than critical
ones.

## Limitations

Accuracy is measured against a manually reviewed subset, not the full corpus.
The subset is small, so individual percentages should be read as indicative —
the direction of differences between models is more trustworthy than their exact
size.

Interpreting the numbers also requires the number of categories each field
admits, which sets the chance baseline. On pregnancy and breastfeeding in
particular, observed accuracies are close enough to plausible chance levels that
the margin above random is not established by this evaluation alone.

A larger annotated evaluation set is the clearest next step.

## Repository layout

```
run.py                entry point (CLI)
pipeline.py           orchestration, resume and checkpointing
checkpoint.py         crash-safe JSONL record store
api_client.py         LLM API layer
pdf_utils.py          PyPDF2 text extraction
prompts.py            field-specific prompts
config.py             configuration, all env-overridable
notify.py             completion beep, no-op where unsupported
run_extraction.bat    supervised unattended launcher (Windows)
RUNNING_LONG_JOBS.md  procedure for a full-corpus run on another machine
```

## Running it

```bash
git clone https://github.com/BerlinTheWall/Pharma_Feature_Extractor.git
cd Pharma_Feature_Extractor
pip install -r requirements.txt

# Default backend is a local Ollama server -- no API key, nothing leaves the machine
ollama pull mistral

python run.py "path/to/Product monograph" --limit 2   # smoke test
python run.py "path/to/Product monograph"             # full run
```

The target folder is walked recursively, so one invocation covers the whole
`<class>/<generic>/*.pdf` corpus. Output and a resume checkpoint go to
`output/`.

To use a hosted OpenAI-compatible provider instead, set the endpoint in the
environment rather than editing any file:

```bash
PHARMA_EXTRACTOR_BASE_URL=... PHARMA_EXTRACTOR_API_KEY=... \
PHARMA_EXTRACTOR_MODEL=... python run.py "path/to/Product monograph"
```

### Long runs

A full-corpus pass is ~20,000 model calls and takes days. Every finished PDF is
checkpointed to JSONL before the next begins, so an interrupted run resumes
rather than restarting — rerun the same command and it skips what is done.

For an unattended run on a dedicated machine, including the supervised
auto-restart launcher, see **[RUNNING_LONG_JOBS.md](RUNNING_LONG_JOBS.md)**.

## Data

Source documents are public Health Canada regulatory filings.

<!--
  BEFORE PUBLISHING, add if you have them:
  - number of categories per categorical field (sets the chance baseline)
  - size of the gold-standard set and who labelled it
  - whether accuracy is exact-match or semantic
  - what the "v2 pipeline" changed
  - absolute recall for adverse events and contraindications, not just the gap
-->
