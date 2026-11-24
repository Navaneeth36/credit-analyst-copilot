# run once with internet, then everything works offline
import config
from sentence_transformers import SentenceTransformer

print(f"Downloading {config.EMBED_MODEL} (about 90 MB)...")
SentenceTransformer(config.EMBED_MODEL).save(config.EMBED_MODEL_FOLDER)
print(f"Saved to {config.EMBED_MODEL_FOLDER}")

# OCR models come with the package, just check it loads
print("Checking the OCR engine...")
from rapidocr_onnxruntime import RapidOCR  # noqa: E402
RapidOCR()

print("Done. You can now work offline.")
