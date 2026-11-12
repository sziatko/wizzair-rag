"""Consistency of evals/questions.json against the chunks. Needs a local snapshot.

Run: uv run python tests/test_questions.py
"""

import json
from collections import Counter
from pathlib import Path

from wizzair_rag.chunks import load_chunks

chunks = load_chunks()
chunk_ids = {c.id for c in chunks}
groups = json.loads(Path("evals/questions.json").read_text(encoding="utf-8"))
# Questions written by other model families (Gemini, GPT), labelled by a blind verifier.
external = json.loads(Path("evals/questions-external.json").read_text(encoding="utf-8"))
assert all(g["source"] in ("gemini", "gpt") for g in external)
groups += external

ids = Counter(g["id"] for g in groups)
assert not [i for i, n in ids.items() if n > 1], "duplicate group ids"
questions = Counter(q.lower() for g in groups for q in g["questions"])
assert not [q for q, n in questions.items() if n > 1], "duplicate questions"  # retrieval is deterministic

for g in groups:
    assert g["kind"] in ("fact", "faq", "tricky", "no-answer"), g["id"]
    assert set(g["chunks"]) <= chunk_ids, f"{g['id']}: unknown chunk {set(g['chunks']) - chunk_ids}"
    # No correct chunks = the expected answer is a refusal.
    if g["kind"] == "no-answer":
        assert not g["chunks"], f"{g['id']}: a no-answer group has no chunks"
    assert g["questions"] and g["answer"], g["id"]
    if g["kind"] == "fact":
        assert len(g["questions"]) >= 3, f"{g['id']}: a fact group needs 3+ wordings"

print(f"ok: {len(groups)} groups, {sum(questions.values())} questions in {chunks[0].snapshot}")
print("  by kind: ", dict(Counter(g["kind"] for g in groups)))
print("  by topic:", dict(Counter(g["topic"] for g in groups)))
print("  chunks used:", len({c for g in groups for c in g["chunks"]}), "of", len(chunk_ids))
