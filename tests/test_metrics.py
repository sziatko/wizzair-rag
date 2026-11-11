"""Retrieval metrics on hand-made cases. Needs a local snapshot (importing the module loads the index).

Run: uv run --env-file .env python tests/test_metrics.py
"""

from wizzair_rag.evaluate import retrieval_metrics

m = retrieval_metrics(["x", "a", "y"], ["a"], {"a"})
assert (m["precision"], m["recall"], m["mrr"], m["hit_any"]) == (1 / 3, 1.0, 0.5, True), m
assert abs(m["f1"] - 0.5) < 1e-9, m

# Conflict group: both sources are labels, only one found.
m = retrieval_metrics(["a", "x", "y"], ["a", "b"], {"a", "b"})
assert (m["recall"], m["mrr"]) == (0.5, 1.0), m

# Nothing labelled found, but an alternative chunk with the same fact was.
m = retrieval_metrics(["x", "alt", "y"], ["a"], {"a", "alt"})
assert (m["precision"], m["recall"], m["f1"], m["mrr"], m["hit_any"]) == (0, 0, 0, 0, True), m

print("ok: retrieval metrics")
