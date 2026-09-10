# Running the full corpus on another machine

The full corpus is ~1,435 PDFs × 14 LLM calls each ≈ **20,000 model calls**. On a
local 7B model that is a **multi-day** run. This document is the procedure for
doing it unattended on a second Windows PC.

The pipeline is built for that now: every finished PDF is written to a JSONL
checkpoint before the next one starts, so a crash, a reboot, or an Ollama
restart costs you one file, not the whole run.

---

## 1. What to copy

Copy two things to the new machine:

| From | To (suggested) | Size |
|---|---|---|
| `pharma_extractor ____\pharma_extractor_package\` | `C:\pharma\pharma_extractor_package\` | small |
| `Received Monographs\Product monograph\` | `C:\pharma\Product monograph\` | ~4 GB |

Put them side by side; nothing else from the project tree is needed.

There are **no credentials to copy** — the default configuration talks to a
local Ollama server, so nothing leaves the machine and no API key is involved.

## 2. Install

```bat
:: Python 3.10+ from python.org (tick "Add python.exe to PATH")
python -m pip install -r C:\pharma\pharma_extractor_package\requirements.txt

:: Ollama from https://ollama.com/download
ollama pull mistral
```

`ollama serve` runs as a background service after install. Confirm it answers:

```bat
curl http://localhost:11434/api/tags
```

## 3. Smoke test before committing days to it

Always do this first. It catches a missing model or a wrong path in five
minutes instead of five hours.

```bat
cd C:\pharma\pharma_extractor_package
python run.py "C:\pharma\Product monograph" -o output --limit 2
```

You should see the endpoint check pass, then two PDFs processed. Check
`output\` for the checkpoint and the `.xlsx`, and open the spreadsheet to
confirm the fields look sane.

## 4. Start the real run

```bat
cd C:\pharma\pharma_extractor_package
.\run_extraction.bat "C:\pharma\Product monograph"
```

> **Keep the `.\` prefix.** PowerShell refuses to run a program from the
> current directory without it and reports `is not recognized` even though the
> file is sitting right there. `.\run_extraction.bat` works in both PowerShell
> and cmd.exe.

Anything after the target folder is passed through to `run.py`, so the resume
workflows work through the launcher too:

```bat
.\run_extraction.bat "C:\pharma\Product monograph" --retry-failed
```

`.\run_extraction.bat` does the things an unattended run needs:

- walks all `<class>\<generic>\*.pdf` subfolders in one pass
- forces UTF-8 so the emoji progress output doesn't crash on redirect
- disables sleep, hibernate and disk timeout while it runs
- logs to `output\run_<timestamp>.log`
- **restarts the pipeline automatically** if it exits non-zero, waiting 60s
  between attempts, up to 100 times — safe, because the restart resumes from
  the checkpoint

Leave the window open. Logging off will kill it — use **Disconnect** in Remote
Desktop, not Sign out.

## 5. Watch it from anywhere

The launcher sends every line of extraction output to the log, so **the window
you started it from stays blank until the run finishes**. That is expected — it
is not a hang. The launcher opens a second window that follows the log for you;
set `NOMONITOR=1` first if you don't want it. `-Encoding UTF8` matters: without
it Windows PowerShell reads the UTF-8 log as ANSI and the progress emoji come
out as mojibake.

```bat
:: progress
powershell -c "Get-Content output\run_*.log -Tail 30 -Wait -Encoding UTF8"

:: how many PDFs are done
powershell -c "(Get-Content 'output\Product monograph_checkpoint.jsonl').Count"
```

Each file logs a running average and an ETA:

```
  ⏱️ 137/1435 done | avg 51.2s/file | ~18.5h remaining
```

The `.xlsx` is rebuilt from the checkpoint every 10 files, so you can open it
mid-run to inspect results (copy it first — Excel locks the file, and a locked
target will fail the next rewrite).

## 6. Stopping and resuming

Ctrl-C, a reboot, or a power cut all cost at most the file in flight.

To resume, **rerun the exact same command**. It reads the checkpoint, skips
what is done, and prints `N already done | M to process`.

| Situation | Command |
|---|---|
| Resume after any stop | `.\run_extraction.bat "C:\pharma\Product monograph"` |
| Reprocess files that errored | `python run.py "..." -o output --retry-failed` |
| Start completely fresh | delete `output\*_checkpoint.jsonl`, or pass `--no-resume` |

## 7. Context length — check this before a long run

Ollama defaults to a **4096-token context**. Several prompts in this pipeline
send multi-page sections — the adverse-events extractor sends roughly five
pages of text — which is comfortably over that limit. Ollama silently drops
the overflow rather than erroring, so the model answers from a truncated
document and the run *looks* fine while quietly losing recall.

Check what you are actually getting:

```bat
ollama ps
:: the CONTEXT column shows the loaded context size
```

Raise it before starting, then restart the service:

```bat
setx OLLAMA_CONTEXT_LENGTH 16384
```

A larger context costs GPU memory. If `ollama ps` then shows the model partly
on CPU (`17%/83% CPU/GPU`), you have traded speed for it — on a long run that
trade is usually still worth it, but measure both with `--limit 2` before
committing days.

This is worth pinning down for the thesis regardless: if the published
accuracy numbers were produced at 4096 tokens, some of the reported weakness on
long-section fields may be truncation rather than model capability.

## 8. List fields and the context window

Indications, contraindications, adverse events and drug interactions must be
comma-separated keywords and nothing else. Two things used to break that:

**Oversized input.** Sections were sent to the model at up to 15,000 characters
(adverse events and drug interactions were not capped at all), against a
4096-token window. Overflow is not an error — the server silently drops the
excess, so the model sees a fragment and starts summarising it. That is where
the prose in those columns came from. Input is now capped by
`PHARMA_EXTRACTOR_MAX_SECTION_CHARS` (default 6000).

**No output check.** Whatever the model returned went into the spreadsheet.
Answers are now validated: bullets, numbering, wrapping quotes and a leading
label are normalised into a clean list, while genuine summaries are rejected and
re-asked up to three times with a correction. If the model never produces a
list, the cell records `EXTRACTION_FAILED` — an explicit failure you can find
and re-run, instead of prose that looks like data.

Raise the two limits together to feed the model more of each section:

```bat
setx OLLAMA_CONTEXT_LENGTH 16384
setx PHARMA_EXTRACTOR_MAX_SECTION_CHARS 20000
```

**Invented lists.** The worst failure was not prose but a clean list that was
never in the document. The drug-interactions prompt used to end with a concrete
example, and the model sometimes returned that example verbatim — thirteen real
drug names, perfectly formatted, entirely unrelated to the monograph. Format
checks cannot catch that, because the shape is correct.

Two defences: every prompt example is now a placeholder (`<drug name>`) that
cannot be copied as content, and each returned term is checked against the
source text. If fewer than half the terms appear in the document the answer is
rejected as invented and re-asked.

Watch the log for `rejected non-list answer`. A few is normal. Many on one
field means the section finder is feeding that field the wrong text, which is a
retrieval problem, not a formatting one. A rejection reading `terms appear in
the source text` means the model invented an answer — usually the sign that the
section it was given was empty or irrelevant.

## 9. Throughput

One model call at a time, ~14 calls per PDF. To speed the run up:

- **A bigger GPU is the main lever.** Ollama uses it automatically; check with
  `ollama ps` that the model shows `100% GPU` rather than partly CPU.
- **Split the corpus across machines** by therapeutic class — each run keeps
  its own checkpoint and Excel, named after the folder you point it at:

  ```bat
  :: machine A
  .\run_extraction.bat "C:\pharma\Product monograph\ACE Inhibitor"
  :: machine B
  .\run_extraction.bat "C:\pharma\Product monograph\Calcium channel blocker"
  ```

  Merge the per-folder spreadsheets afterwards; the `Source Path`,
  `Drug Folder` and `Therapeutic Class` columns keep provenance.
- **Try `qwen2.5:7b`** by changing `PHARMA_EXTRACTOR_MODEL` in the .bat — but
  note the README's finding that Qwen under-catches clinically important
  adverse events.

## 10. If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `Model endpoint check failed` | Ollama not running, or model not pulled | `ollama serve`, `ollama pull mistral` |
| Every field is `EXTRACTION_FAILED` | Wrong `PHARMA_EXTRACTOR_BASE_URL`, or model name typo | Check the .bat settings block |
| `No module named openpyxl` | Deps not fully installed | `pip install -r requirements.txt` |
| `UnicodeEncodeError` on `📄` | Ran `python run.py` redirected without the .bat | `set PYTHONIOENCODING=utf-8` |
| Excel rewrite fails mid-run | You have the .xlsx open | Close it; the checkpoint is unaffected |
| Machine slept overnight | Power settings not applied | Run the .bat as Administrator |
| `run_extraction.bat` `is not recognized` | PowerShell won't run from the current dir | Use `.\run_extraction.bat` |
| Prose in a keyword column | Section text overflowed the context | Raise both context and MAX_SECTION_CHARS |
| Long sections extract poorly | 4096-token context truncation | `setx OLLAMA_CONTEXT_LENGTH 16384`, restart Ollama |

---

## Environment variables

All optional; the .bat sets the ones that matter.

| Variable | Default | Purpose |
|---|---|---|
| `PHARMA_EXTRACTOR_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint |
| `PHARMA_EXTRACTOR_API_KEY` | `ollama` | Ignored by Ollama; set for hosted providers |
| `PHARMA_EXTRACTOR_MODEL` | `mistral` | Model name |
| `PHARMA_EXTRACTOR_SAFE_DELAY` | `1` | Seconds between files; `0` for local |
| `PHARMA_EXTRACTOR_EXCEL_FLUSH_EVERY` | `10` | Files between Excel rewrites |
| `PHARMA_EXTRACTOR_MAX_SECTION_CHARS` | `6000` | Max characters of a section sent per call |
