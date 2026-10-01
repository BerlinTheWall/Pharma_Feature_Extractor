"""AI API client with retry logic."""

import time
from .config import client, DEFAULT_MODEL, KEYWORD_MAX_TOKENS, KEYWORD_REQUEST_TIMEOUT
from .output_format import normalize_keyword_list

def call_ai_api(prompt: str, system_message: str, filename: str, temperature: float = 0.1, model: str = None, max_retries: int = 5, max_tokens: int = None, return_finish_reason: bool = False, timeout: float = None):
    """
    Generic AI API call with retry logic.

    Args:
        prompt: User prompt to send
        system_message: System message for context
        filename: Current file being processed (for logging)
        temperature: Model temperature (0-1)
        model: Model name to use (defaults to config.DEFAULT_MODEL, itself
            overridable via the PHARMA_EXTRACTOR_MODEL env var)
        max_tokens: hard ceiling on the generated answer. Left unset for the
            summary fields, which legitimately need room; set for the list
            fields, where an unbounded answer means a runaway generation that
            can burn the full client timeout.
        max_retries: give up and return "EXTRACTION_FAILED" after this many
            consecutive non-rate-limit failures (e.g. a request that keeps
            timing out), instead of retrying forever

    Returns:
        API response content as string, or "EXTRACTION_FAILED" if max_retries
        is exhausted
    """
    model = model or DEFAULT_MODEL
    attempts = 0
    rate_limit_attempts = 0
    timeout_attempts = 0
    max_timeout_retries = 2
    max_rate_limit_retries = max_retries * 3  # rate limits are expected to clear; give them more slack than real errors
    while True:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                **({"max_tokens": max_tokens} if max_tokens else {}),
                **({"timeout": timeout} if timeout else {})
            )
            choice = response.choices[0]
            if return_finish_reason:
                return choice.message.content, choice.finish_reason
            return choice.message.content
        except Exception as e:
            if "429" in str(e):
                rate_limit_attempts += 1
                if rate_limit_attempts >= max_rate_limit_retries:
                    print(f"Rate limit still hit after {rate_limit_attempts} attempts. Giving up on {filename}.")
                    return ("EXTRACTION_FAILED", "error") if return_finish_reason else "EXTRACTION_FAILED"
                print(f"Rate limit hit. Pausing 30s before retrying {filename}... (attempt {rate_limit_attempts}/{max_rate_limit_retries})")
                time.sleep(30)
                continue
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                timeout_attempts += 1
                if timeout_attempts >= max_timeout_retries:
                    print(f"Request timed out {timeout_attempts}x on {filename}. "
                          f"Giving up rather than replaying the same prompt.")
                    return ("EXTRACTION_FAILED", "timeout") if return_finish_reason else "EXTRACTION_FAILED"
                print(f"Request timed out. Retrying {filename} once more... "
                      f"(timeout {timeout_attempts}/{max_timeout_retries})")
                time.sleep(5)
                continue

            attempts += 1
            if attempts >= max_retries:
                print(f"Error: {e}. Giving up on {filename} after {attempts} attempts.")
                return ("EXTRACTION_FAILED", "error") if return_finish_reason else "EXTRACTION_FAILED"
            print(f"Error: {e}. Retrying {filename} in 5s... (attempt {attempts}/{max_retries})")
            time.sleep(5)

# Appended to the prompt when the model's first answer was not a clean list.
_FORMAT_CORRECTION = """

Your previous answer was rejected because it {reason}.

Return ONLY the terms, separated by commas, on a single line.
Do not write a summary, a sentence, an introduction or a closing remark.
Do not number the terms and do not use bullet points.
Correct shape: term one, term two, term three
"""


def call_ai_api_keywords(
    prompt: str,
    system_message: str,
    filename: str,
    field_name: str,
    source_text: str = None,
    temperature: float = 0.1,
    model: str = None,
    max_retries: int = 5,
    max_format_attempts: int = 3,
    max_tokens: int = None,
):
    """
    Call the model for a field whose value must be a comma-separated list.

    Small instruct models drift into prose no matter how firmly the prompt is
    worded, and prose stored in a list column is indistinguishable from data
    downstream. So the answer is validated: salvageable shapes (bullets,
    numbering, a wrapping quote, a leading label) are normalized, and genuine
    summaries are rejected and re-asked with a correction naming the problem.

    Pass `source_text` to also reject answers whose terms do not appear in the
    document -- the failure mode where the model returns a clean, plausible
    list it invented, or copied from an example in the prompt.

    Returns:
        The normalized comma-separated string, a passthrough sentinel, or
        "EXTRACTION_FAILED" if the model never produced a usable list. Prose is
        never returned -- an explicit failure is recoverable, silent bad data
        is not.
    """
    attempt_prompt = prompt
    attempt_temperature = temperature
    token_cap = max_tokens or KEYWORD_MAX_TOKENS

    for attempt in range(1, max_format_attempts + 1):
        if attempt > 1:
            # Say so before the call, not after: a silent multi-minute retry
            # looks like a hang in the log.
            print(f"    ↻ {field_name}: re-asking with a format correction "
                  f"(attempt {attempt}/{max_format_attempts})...")

        started = time.time()
        raw, finish_reason = call_ai_api(
            attempt_prompt,
            system_message,
            filename,
            temperature=attempt_temperature,
            model=model,
            max_retries=max_retries,
            max_tokens=token_cap,
            return_finish_reason=True,
            timeout=KEYWORD_REQUEST_TIMEOUT,
        )
        elapsed = time.time() - started

        if finish_reason == "length" and isinstance(raw, str) and "," in raw:
            # The cap cut generation mid-term, so the trailing fragment is not
            # a whole keyword. Drop it rather than storing half a word.
            raw = raw[:raw.rfind(",")]
            print(f"    ✂️ {field_name}: answer hit the {token_cap}-token cap; "
                  f"dropped the truncated final term")

        if raw == "EXTRACTION_FAILED":
            return "EXTRACTION_FAILED"

        value, reason = normalize_keyword_list(raw, source_text=source_text)
        if value is not None:
            if attempt > 1:
                print(f"    ✅ {field_name}: valid list on format attempt "
                      f"{attempt} ({elapsed:.0f}s)")
            return value

        preview = " ".join(str(raw).split())[:120]
        print(f"    ⚠️ {field_name}: rejected non-list answer after {elapsed:.0f}s "
              f"({reason}) on attempt {attempt}/{max_format_attempts}: {preview}...")

        attempt_prompt = prompt + _FORMAT_CORRECTION.format(reason=reason)
        # Drop to greedy decoding for the corrective attempts.
        attempt_temperature = 0.0

    print(f"    ❌ {field_name}: no valid list after {max_format_attempts} attempts "
          f"-- recording EXTRACTION_FAILED rather than storing prose")
    return "EXTRACTION_FAILED"
