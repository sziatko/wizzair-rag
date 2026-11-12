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

from wizzair_rag.chunks import Chunk, load_chunks, load_summaries

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


def summary_text(c: Chunk, summary: str, variant: str) -> str:
    """Decision 16: s1 = heading + summary + text (primary), s2 = heading + summary (exploratory)."""
    head = " > ".join(c.path) + "\n\n" + summary
    return {"s1": head + "\n\n" + c.text, "s2": head}[variant]


def index_path(snapshot: str, variant: str = "") -> Path:
    return INDEX_DIR / snapshot / f"{EMBED_MODEL}{variant}.npz"  # variant "" = Level 1, "-s1" / "-s2" = Level 2


def load_index(chunks: list[Chunk], variant: str = "") -> np.ndarray:
    data = np.load(index_path(chunks[0].snapshot, variant))
    if list(data["ids"]) != [c.id for c in chunks]:
        raise ValueError("index does not match chunks.jsonl; rebuild it: python -m wizzair_rag.index")
    return data["vectors"]


def save_index(chunks: list[Chunk], texts: list[str], variant: str = "") -> None:
    vectors = embed(texts, "document")
    out = index_path(chunks[0].snapshot, variant)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, ids=np.array([c.id for c in chunks]), vectors=vectors)
    print(f"{len(chunks)} chunks, {vectors.shape[1]} dims -> {out}")


def main() -> None:
    """With "summary" as an argument: also build the Level 2 indexes from summaries.jsonl."""
    args = [a for a in sys.argv[1:] if a != "summary"]
    chunks = load_chunks(args[0] if args else None)
    save_index(chunks, [chunk_for_embedding(c) for c in chunks])
    if "summary" in sys.argv[1:]:
        summaries = load_summaries(chunks)
        for variant in ("s1", "s2"):
            save_index(chunks, [summary_text(c, s, variant) for c, s in zip(chunks, summaries)], f"-{variant}")


if __name__ == "__main__":
    main()
