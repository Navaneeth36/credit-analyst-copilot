import os
import re

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

import config


def load_embedder():
    if os.path.isdir(config.EMBED_MODEL_FOLDER):
        # saved copy exists, don't let it hit the internet
        os.environ["HF_HUB_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(config.EMBED_MODEL_FOLDER)

    # not downloaded yet
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(config.EMBED_MODEL)


def tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def build_index(chunks, embedder):
    # embeddings for meaning, BM25 for exact terms like "going concern"
    texts = [c["text"] for c in chunks]

    # normalised -> inner product is cosine sim
    vectors = np.array(embedder.encode(texts, normalize_embeddings=True), dtype="float32")
    meaning = faiss.IndexFlatIP(vectors.shape[1])
    meaning.add(vectors)

    keywords = BM25Okapi([tokenize(t) for t in texts])

    return {"meaning": meaning, "keyword": keywords, "chunks": chunks}


def search(query, index, embedder, k=config.TOP_K, pool=20, only=None):
    chunks = index["chunks"]
    if only is not None:
        pool = len(chunks)  # rank everything if we're filtering
    pool = min(pool, len(chunks))

    q = np.array(embedder.encode([query], normalize_embeddings=True), dtype="float32")
    _, by_meaning = index["meaning"].search(q, pool)

    scores = index["keyword"].get_scores(tokenize(query))
    by_keyword = np.argsort(scores)[::-1][:pool]

    # reciprocal rank fusion (k=60 is the standard value)
    totals = {}
    for ranking in (by_meaning[0], by_keyword):
        for rank, pos in enumerate(ranking):
            pos = int(pos)
            if pos == -1:  # faiss pads with -1
                continue
            totals[pos] = totals.get(pos, 0) + 1 / (60 + rank)

    ranked = sorted(totals, key=totals.get, reverse=True)
    if only is not None:
        ranked = [pos for pos in ranked if only(chunks[pos])]
    best = ranked[:k]
    return [dict(chunks[pos], score=round(totals[pos], 4)) for pos in best]
