"""Main entry point for the pharmaceutical monograph extractor."""

import argparse
import os
import sys
import time

# Emoji in the progress output crashes with UnicodeEncodeError the moment
# stdout is redirected to a log file on Windows (cp1252). An unattended run is
# always redirected, so force UTF-8 before anything prints.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Add parent directory to path if running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pharma_extractor_package.config import API_BASE_URL, DEFAULT_MODEL, client
from pharma_extractor_package.notify import beep
from pharma_extractor_package.pipeline import run_pipeline

DEFAULT_TARGET = os.path.join("..", "..", "Received Monographs", "Product monograph")


def preflight() -> bool:
    """
    Confirm the model answers before committing to a multi-day run.

    A wrong base URL or an unpulled model otherwise shows up as thousands of
    EXTRACTION_FAILED rows discovered hours later.
    """
    print(f"🔌 Checking model endpoint: {API_BASE_URL} (model: {DEFAULT_MODEL})")
    try:
        started = time.time()
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            temperature=0,
        )
        reply = (response.choices[0].message.content or "").strip()
        print(f"  ✅ Model responded in {time.time() - started:.1f}s: {reply[:60]!r}")
        return True
    except Exception as e:
        print(f"  ❌ Model endpoint check failed: {e}")
        print("     Is the server running, and is the model pulled?")
        print("     For Ollama:  ollama serve   and   ollama pull " + DEFAULT_MODEL)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract structured clinical fields from Health Canada monograph PDFs.",
    )
    parser.add_argument(
        "target_folder",
        nargs="?",
        default=DEFAULT_TARGET,
        help="Root folder of monograph PDFs (walked recursively by default)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="output",
        help="Where the Excel and the resume checkpoint are written (default: output)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only read PDFs directly in target_folder, not in subfolders",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore the existing checkpoint and reprocess everything",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Also reprocess checkpointed files that errored out",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N new files, for a smoke test before the full run",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip the model connectivity check",
    )
    args = parser.parse_args()

    target_folder = os.path.abspath(args.target_folder)
    if not os.path.isdir(target_folder):
        print(f"❌ Folder path not found: {target_folder}")
        return 1

    if not args.skip_preflight and not preflight():
        return 1

    started = time.time()
    try:
        run_pipeline(
            target_folder,
            output_dir=os.path.abspath(args.output_dir),
            recursive=not args.no_recursive,
            resume=not args.no_resume,
            retry_failed=args.retry_failed,
            limit=args.limit,
        )
    except KeyboardInterrupt:
        # Everything finished is already on disk; say so rather than dumping a
        # traceback that looks like data loss.
        print("\n⏹️ Interrupted. Completed records are checkpointed — rerun the")
        print("   same command to resume from where it stopped.")
        return 130

    print(f"\n⏳ Total runtime: {(time.time() - started) / 3600:.2f}h")
    beep()
    print("\n✨ Pipeline complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
