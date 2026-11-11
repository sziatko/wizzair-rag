"""Embed every chunk of one snapshot with Voyage AI and save the vectors.

Like the Cookbook's in-memory vector DB: a numpy matrix, one row per chunk,
saved next to the chunk ids so a stale index fails loudly instead of misaligning.

Run: uv run --env-file .env python -m wizzair_rag.index [YYYY-MM-DD]   (default: latest snapshot)
Writes data/index/<snapshot>/<model>.npz
"""

import sys
from pathlib import Path

import numpy as np
import voyageai

from wizzair_rag.chunks import Chunk, load_chunks

EMBED_MODEL = "voyage-4-large"
INDEX_DIR = Path("data/index")


def embed(texts: list[str], input_type: str) -> np.ndarray:
    """input_type is "document" for chunks and "query" for questions (Voyage embeds them differently)."""
    result = voyageai.Client().embed(texts, model=EMBED_MODEL, input_type=input_type)
    vectors = np.array(result.embeddings, dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)  # unit length: dot product = cosine


def chunk_for_embedding(c: Chunk) -> str:
    """Headings first, like the Cookbook: "Sports equipment" alone says more than its body text."""
    return " > ".join(c.path) + "\n\n" + c.text


def index_path(snapshot: str) -> Path:
    return INDEX_DIR / snapshot / f"{EMBED_MODEL}.npz"


def load_index(chunks: list[Chunk]) -> np.ndarray:
    data = np.load(index_path(chunks[0].snapshot))
    if list(data["ids"]) != [c.id for c in chunks]:
        raise ValueError("index does not match chunks.jsonl; rebuild it: python -m wizzair_rag.index")
    return data["vectors"]


def main() -> None:
    chunks = load_chunks(sys.argv[1] if len(sys.argv) > 1 else None)
    vectors = embed([chunk_for_embedding(c) for c in chunks], "document")
    out = index_path(chunks[0].snapshot)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, ids=np.array([c.id for c in chunks]), vectors=vectors)
    print(f"{len(chunks)} chunks, {vectors.shape[1]} dims -> {out}")


if __name__ == "__main__":
    main()
