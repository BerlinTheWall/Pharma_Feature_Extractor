"""AI API client with retry logic."""

import time
from .config import client, DEFAULT_MODEL

def call_ai_api(prompt: str, system_message: str, filename: str, temperature: float = 0.1, model: str = None, max_retries: int = 5):
    """
    Generic AI API call with retry logic.

    Args:
        prompt: User prompt to send
        system_message: System message for context
        filename: Current file being processed (for logging)
        temperature: Model temperature (0-1)
        model: Model name to use (defaults to config.DEFAULT_MODEL, itself
            overridable via the PHARMA_EXTRACTOR_MODEL env var)
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
    max_rate_limit_retries = max_retries * 3  # rate limits are expected to clear; give them more slack than real errors
    while True:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e):
                rate_limit_attempts += 1
                if rate_limit_attempts >= max_rate_limit_retries:
                    print(f"Rate limit still hit after {rate_limit_attempts} attempts. Giving up on {filename}.")
                    return "EXTRACTION_FAILED"
                print(f"Rate limit hit. Pausing 30s before retrying {filename}... (attempt {rate_limit_attempts}/{max_rate_limit_retries})")
                time.sleep(30)
                continue
            attempts += 1
            if attempts >= max_retries:
                print(f"Error: {e}. Giving up on {filename} after {attempts} attempts.")
                return "EXTRACTION_FAILED"
            print(f"Error: {e}. Retrying {filename} in 5s... (attempt {attempts}/{max_retries})")
            time.sleep(5)