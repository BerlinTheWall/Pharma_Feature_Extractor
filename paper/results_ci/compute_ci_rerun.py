"""
Development-set (Set A) scores for the November 2026 full-context reruns,
next to the August runs, using exactly the same scoring as compute_ci.py.

The August Qwen and Mistral runs used Ollama's default context, which cut
long prompts short. The reruns use a 32,768-token context and a 2,048-token
output cap (see paper_draft/heldout/runs/modelfiles).

Results go to ./rerun_nov2026; the files compute_ci.py wrote are not touched.
Run with the environment that has sentence-transformers:
  "..\\..\\..\\online-pdf-reader\\.venv\\Scripts\\python.exe" compute_ci_rerun.py
"""
import os

import compute_ci as C

V3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v3", "setA_outputs")
RUNS = r"D:\Western University\Project\pharma_extractor ____\paper_draft\heldout\runs\setA_outputs"

C.SYSTEMS = {
    "Qwen 2.5 7B, Aug (original pipeline)": "qwen_extractions.xlsx",
    "Qwen 2.5 7B, Aug (second version)": "qwen_v2_extractions.xlsx",
    "Mistral 7B, Aug (original pipeline)": "mistral_extractions.xlsx",
    "Qwen 2.5 7B, Nov full context (original pipeline)": os.path.join(RUNS, "qwen_v1_setA.xlsx"),
    "Qwen 2.5 7B, Nov full context (second version)": os.path.join(RUNS, "qwen_v2_setA.xlsx"),
    "Mistral 7B, Nov full context (original pipeline)": os.path.join(RUNS, "mistral_v1_setA.xlsx"),
    "Mistral 7B, Nov full context (second version)": os.path.join(RUNS, "mistral_v2_setA.xlsx"),
    "Qwen 2.5 7B, third version": os.path.join(V3, "qwen_v3_setA.xlsx"),
    "Mistral 7B, third version": os.path.join(V3, "mistral_v3_setA.xlsx"),
    "Llama 3.1 8B, run B (original pipeline)": "cf_llama_extractions.xlsx",
    "Llama 3.1 8B, third version": os.path.join(V3, "llama_v3_setA.xlsx"),
}
C.PAIRS = [
    ("Qwen 2.5 7B, Nov", "Qwen 2.5 7B, Nov full context (original pipeline)",
     "Qwen 2.5 7B, Nov full context (second version)"),
    ("Mistral 7B, Nov", "Mistral 7B, Nov full context (original pipeline)",
     "Mistral 7B, Nov full context (second version)"),
    ("Qwen 2.5 7B, Aug to Nov (original pipeline)", "Qwen 2.5 7B, Aug (original pipeline)",
     "Qwen 2.5 7B, Nov full context (original pipeline)"),
    ("Mistral 7B, Aug to Nov (original pipeline)", "Mistral 7B, Aug (original pipeline)",
     "Mistral 7B, Nov full context (original pipeline)"),
]
C.PAIRS += [
    ("Qwen 2.5 7B, original to third", "Qwen 2.5 7B, Nov full context (original pipeline)", "Qwen 2.5 7B, third version"),
    ("Mistral 7B, original to third", "Mistral 7B, Nov full context (original pipeline)", "Mistral 7B, third version"),
    ("Llama 3.1 8B, run B to third", "Llama 3.1 8B, run B (original pipeline)", "Llama 3.1 8B, third version"),
]
C.PAIRED_FIELDS = ["Indication of Use", "Contraindications", "Serious warning and precautions", "Adverse Events", "Drug Interactions"]
C.HERE = os.path.join(C.HERE, "rerun_nov2026")
os.makedirs(C.HERE, exist_ok=True)

if __name__ == "__main__":
    C.main()
