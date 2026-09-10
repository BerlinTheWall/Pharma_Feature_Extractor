"""Completion beep that degrades to a no-op where it isn't available.

winsound is Windows-only, and even on Windows it raises when the machine has
no sound device -- which is the normal case for the unattended, headless runs
this pipeline is built for. Importing it at module scope, as the extractors
used to, turns "no speaker" or "not Windows" into an import-time crash hours
before the run would have finished.
"""

try:
    import winsound
except ImportError:  # not Windows
    winsound = None


def beep(frequency: int = 440, duration_ms: int = 500) -> None:
    """Play a short completion tone, or do nothing if the host can't."""
    if winsound is None:
        return
    try:
        winsound.Beep(frequency, duration_ms)
    except Exception:
        pass
