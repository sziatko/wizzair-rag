"""Known facts that must survive chunking. Needs a local snapshot (data/ is not in git).

Run: uv run python -m wizzair_rag.chunks && uv run python tests/test_chunks.py
"""

import json

from wizzair_rag.chunks import CHUNKS_DIR

latest = max(CHUNKS_DIR.iterdir())
chunks = {c["id"]: c for c in map(json.loads, (latest / "chunks.jsonl").read_text(encoding="utf-8").splitlines())}
text = {i: c["text"] for i, c in chunks.items()}

assert "40 x 30 x 20 cm" in text["hc-cabin-baggage#accordion-free-carry-on-bag"]
assert chunks["gcc-wah-2023-03-01#15.1.6"]["page"] == 34
assert chunks["gcc-wah-2023-03-01#15.1.6"]["url"].endswith("#page=34")
assert "15.1.6.10." in text["gcc-wah-2023-03-01#15.1.6"]
assert "32 kilograms" in text["gcc-wah-2023-03-01#15.1.1"]
assert chunks["gcc-wah-2023-03-01#def-cabin-baggage"]["path"] == ["Definitions"]
assert "Baggage fee low season max. 10 kg" in text["fees-all-services#baggage-fees"]
assert "Christmas 2026 peak" in text["fees-all-services#baggage-fees"]
assert "€13.00 – €60.00" in text["fees-all-services#wizz-priority"]
assert "Discount Club" not in text["fees-all-services#wizz-priority"]
assert "WIZZ Priority (AIRPORT) | Per flight, per passenger | €65.00 – €75.00" in text["fees-all-services#wizz-priority"]
assert "Baggage fee 20 kg (AIRPORT) | " in text["fees-all-services#baggage-fees"]
assert "160 Wh when carried for personal use." in text["hc-restricted-items#accordion-lithium-batteries"]
assert "| Yes | No | Yes | Yes" in text["hc-restricted-items#accordion-lithium-batteries"]  # table row kept whole
assert "SUBMIT CLAIM" not in text["hc-bags-reporting-procedure#accordion-delayed-or-lost-baggage"]  # CTA button
assert "20 kg checked-in bag" in text["fees-fares-bundles#accordion-wizz-go-wizz-family-go"]
assert not text["fees-fares-bundles#intro"].endswith("Accordions")
for i, t in text.items():
    assert "Did you find this helpful" not in t, i
    assert "<" not in t and ">" not in t, i  # no HTML left over

print(f"ok: {len(chunks)} chunks in {latest.name}")
