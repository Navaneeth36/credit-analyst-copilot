import os

# "ollama" (local) or "groq" (cloud, needs GROQ_API_KEY)
PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model": os.getenv("LLM_MODEL", "openai/gpt-oss-20b"),
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "key_env": None,
        "model": os.getenv("LLM_MODEL", "credit-copilot"),  # see Modelfile
    },
}

# download_models.py saves this into models/ for offline use
EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_MODEL_FOLDER = os.path.join(os.path.dirname(__file__), "models", EMBED_MODEL)

# chunking
CHUNK_LINES = 20
OVERLAP_LINES = 5
TOP_K = 6           # was 4, too few for long reports

# OCR
OCR_ENABLED = True
OCR_DPI = 200
OCR_BOX_THRESHOLD = 0.3
OCR_UNCLIP = 2.0         # default was cutting off long lines
MIN_TEXT_CHARS = 20      # less text than this -> OCR the page

COLUMN_GAP = 15  # points

CACHE_DIR = ".cache"
