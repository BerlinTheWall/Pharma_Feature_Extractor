"""AI API client with retry logic."""

import time
from .config import client

def call_ai_api(prompt: str, system_message: str, filename: str, temperature: float = 0.1, model: str = "llama3.1-8b"):
    """
    Generic AI API call with retry logic.
    
    Args:
        prompt: User prompt to send
        system_message: System message for context
        filename: Current file being processed (for logging)
        temperature: Model temperature (0-1)
        model: Model name to use
    
    Returns:
        API response content as string
    """
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
                print(f"Rate limit hit. Pausing 30s before retrying {filename}...")
                time.sleep(30)
            else:
                print(f"Error: {e}. Retrying {filename} in 5s...")
                time.sleep(5)