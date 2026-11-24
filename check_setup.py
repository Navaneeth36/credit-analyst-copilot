# run this first, tells you what's missing
import importlib
import json
import os
import urllib.request

import config

problems = 0


def report(ok, message, fix=""):
    global problems
    print(("OK      " if ok else "PROBLEM ") + message)
    if not ok:
        problems += 1
        print("        fix: " + fix)


for library in ["pymupdf", "rapidocr_onnxruntime", "sentence_transformers",
                "faiss", "rank_bm25", "openai", "streamlit"]:
    try:
        importlib.import_module(library)
        report(True, f"library {library}")
    except ImportError:
        report(False, f"library {library} is not installed",
               "source venv/bin/activate, then pip install -r requirements.txt")

report(os.path.isdir(config.EMBED_MODEL_FOLDER), "embedding model saved for offline use",
       "connect to the internet once and run: python download_models.py")

print(f"\nAI provider: {config.PROVIDER}")
if config.PROVIDER == "ollama":
    base = config.PROVIDERS["ollama"]["base_url"].replace("/v1", "")
    try:
        # /api/tags lists installed models, if it answers ollama is up
        with urllib.request.urlopen(base + "/api/tags", timeout=3) as response:
            installed = [m["name"] for m in json.load(response)["models"]]
        report(True, "Ollama is running")

        wanted = config.PROVIDERS["ollama"]["model"]
        # names come back as "credit-copilot:latest"
        report(any(m.split(":")[0] == wanted for m in installed), f"model '{wanted}' exists",
               "ollama pull qwen2.5:7b   then   ollama create credit-copilot -f Modelfile")
    except OSError:
        report(False, "Ollama is not running", "open the Ollama app (or run: ollama serve)")
else:
    key = config.PROVIDERS[config.PROVIDER]["key_env"]
    report(bool(os.environ.get(key)), f"{key} is set", f'export {key}="..."')

if problems == 0:
    print("\nAll good. Run: streamlit run app.py")
else:
    print(f"\n{problems} problem(s) to fix.")
