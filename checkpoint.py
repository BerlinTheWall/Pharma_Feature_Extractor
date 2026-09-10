"""Crash-safe checkpointing for long extraction runs.

A full corpus run is thousands of LLM calls over many hours. Holding every
record in memory until the end means a reboot, a dropped Ollama connection or
a stray Ctrl-C throws away the whole run. Instead each finished record is
appended to a JSONL file and flushed to disk immediately, so a restart picks
up from the last completed PDF.
"""

import json
import os
from typing import Dict, List


def load_records(checkpoint_path: str) -> List[Dict]:
    """
    Read every record written so far.

    Truncated trailing lines -- the normal result of a hard kill mid-write --
    are skipped rather than treated as corruption, so a run is never blocked
    by its own interrupted last write.
    """
    if not os.path.isfile(checkpoint_path):
        return []

    records = []
    skipped = 0
    with open(checkpoint_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1

    if skipped:
        print(f"  ⚠️ Skipped {skipped} incomplete checkpoint line(s) from an interrupted run")

    return records


def completed_keys(records: List[Dict]) -> set:
    """Source keys already processed, for skipping on resume."""
    return {r.get("Source Path") for r in records if r.get("Source Path")}


def failed_keys(records: List[Dict]) -> set:
    """
    Source keys whose record is an outright failure.

    A file counts as failed when the whole-file handler caught an exception
    (metadata replaced by an ERROR string). Per-field misses like
    SECTION_NOT_FOUND are genuine extraction outcomes, not failures, and are
    left alone.
    """
    failed = set()
    for record in records:
        key = record.get("Source Path")
        if key and str(record.get("Brand Name", "")).startswith("ERROR"):
            failed.add(key)
    return failed


def append_record(checkpoint_path: str, record: Dict) -> None:
    """Append one record and force it to disk before returning."""
    os.makedirs(os.path.dirname(os.path.abspath(checkpoint_path)), exist_ok=True)
    with open(checkpoint_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def rewrite_records(checkpoint_path: str, records: List[Dict]) -> None:
    """Replace the checkpoint with `records` (used when retrying failures)."""
    tmp_path = checkpoint_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, checkpoint_path)
