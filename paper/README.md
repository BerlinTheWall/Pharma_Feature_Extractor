# Code of the paper

This folder holds the code behind the results of the paper on extracting
structured fields from Health Canada product monographs. It is kept as it was
run, so that the numbers in the paper can be traced back to it.

The paper compares two versions of the pipeline:

- **Original pipeline**: the package at the root of this repository, as it was
  on August 27, 2026 (tag `paper-original`, commit `3d08736`). It produced the
  released dataset of 1,434 monographs and is the baseline of the evaluation.
- **Final version**: `v3/`. It changes how the sections are found and how long
  sections are sent to the model, for the nine evaluated fields. Its code was
  frozen on November 6, 2026, before the held-out run; `v3/FROZEN.txt` has the
  SHA-256 of each file (`sha256sum -c v3/FROZEN.txt` from inside `v3/`).

## Contents

| Folder | What it does |
|---|---|
| `v3/` | Final version: section location from PDF bookmarks (`sections_v3.py`), splitting and cleaning (`pipeline_v3.py`), prompts (`prompts_v3.py`), runner (`run_v3.py`, `run_all_v3.sh`), and two tools used while building it (`check_sections.py`, `score_quick.py`) |
| `heldout/` | Random draw of the held-out test set (`draw_heldout_set.py`, seed 20261005) and the runner of the original pipeline on both evaluation sets (`runs/run_setB.py`) |
| `heldout/runs/modelfiles/` | Ollama settings of the local runs (context of 32,768 tokens, answer limit of 2,048 tokens) |
| `results_ci/` | Scoring against the gold standard (`score_against_ground_truth.py`), confidence intervals and paired comparisons (`compute_ci.py`, `compute_ci_rerun.py`), and the error analysis (`error_analysis.py`) |
| `table1/` | Description of the corpus (Table 1) and the check of the PDF bookmarks |

## Running it

The scripts expect the layout used during the project:

- the original pipeline at `heldout/runs/code_aug27/pharma_extractor_package`.
  Create it with `git worktree add paper/heldout/runs/code_aug27/pharma_extractor_package paper-original`
  from the root of this repository;
- the monograph PDFs, the gold standards and the result files at the paths set
  at the top of each script (`CORPUS`, `FINAL`, `V2_DIR`, `PDF_DIR`). These are
  absolute paths of the project machine and have to be changed.

The PDFs are public and can be downloaded from the Drug Product Database of
Health Canada; they are not included. The scoring uses `sentence-transformers`
with `NeuML/pubmedbert-base-embeddings`.

Example, final version on the development set with a local Ollama model:

```
ollama create qwen2.5-7b-ctx32k -f heldout/runs/modelfiles/qwen2.5-7b-ctx32k.Modelfile
cd v3
PHARMA_EXTRACTOR_MODEL=qwen2.5-7b-ctx32k python run_v3.py --set A --out qwen_v3_setA.xlsx
```
