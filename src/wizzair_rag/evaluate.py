"""A5: run every eval question through the Level 1 pipeline, score retrieval like the
Cookbook, and let an LLM judge the answers against the reference answers.

Run:    uv run --env-file .env python -m wizzair_rag.evaluate run [runs]     (default 3 runs)
Report: uv run python -m wizzair_rag.evaluate report evals/results/<file>.json
Check:  uv run --env-file .env python -m wizzair_rag.evaluate check evals/results/<file>.json [n]

`run` writes evals/results/<date>T<time>.json: one record per question with the retrieved
chunks, retrieval metrics and every run's reply with its verdict. Retrieval is
deterministic, so it runs once; only the answers are repeated, to see their spread.
`check` re-grades a random sample of the judge's verdicts with a different model,
without showing it the judge's verdict, and reports how often the two agree.
"""

import json
import random
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from statistics import mean

import anthropic
from pydantic import BaseModel

from wizzair_rag.index import EMBED_MODEL, embed
from wizzair_rag.rag import ANSWER_MODEL, TOP_K, Hit, chunks, excerpt, generate, search

# Sonnet judges every reply; Opus re-grades a sample. Half the cost of an Opus judge, and
# the two agreed on 29 of 30 verdicts in the first run (decision 7).
JUDGE_MODEL = "claude-sonnet-5-5"
CHECK_MODEL = "claude-opus-5-5"  # a second opinion on the judge, from another model
RESULTS_DIR = Path("evals/results")
WORKERS = 8  # parallel API calls

groups = json.loads(Path("evals/questions.json").read_text(encoding="utf-8"))
# Chunks the blind verifier also found the fact in (decision 4). They are not labels:
# they only feed the secondary "hit@3 any" column.
blind = json.loads(Path("evals/blind-check-2026-11-11.json").read_text(encoding="utf-8"))
alternatives = {b["id"]: set(b["chunks"]) for b in blind}
chunk_by_id = {c.id: c for c in chunks}
client = anthropic.Anthropic()


# ---------- retrieval metrics, as in the Cookbook ----------


def retrieval_metrics(retrieved: list[str], relevant: list[str], acceptable: set[str]) -> dict:
    found = [r in relevant for r in retrieved]
    hits = sum(found)
    precision, recall = hits / len(retrieved), hits / len(relevant)
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if hits else 0.0,
        "mrr": 1 / (found.index(True) + 1) if hits else 0.0,  # rank of the first relevant chunk
        "hit_any": any(r in acceptable for r in retrieved),  # any chunk that holds the fact
    }


# ---------- answers ----------


def ask(question: str, hits: list[Hit]) -> dict:
    """One reply as plain data. A broken reply (citations outside the retrieved chunks, a
    cut-off output) is a real failure of the pipeline: it is recorded and graded wrong,
    so one bad reply does not stop a run of 600."""
    try:
        return generate(question, hits).reply.model_dump()
    except (ValueError, RuntimeError) as e:
        return {"kind": "error", "message": str(e)}


# ---------- judge ----------

JUDGE_SYSTEM = """You grade replies of a Wizz Air baggage assistant against a reference answer from a checked eval set. You also get the excerpts the assistant answered from. Use only the reference and the excerpts, never your own knowledge of Wizz Air rules: it may be out of date.

The reply is correct only if:
- it gives the key facts of the reference (numbers, sizes, weights, prices, yes or no) and contradicts none of them; extra details are fine if the excerpts support them, and wrong if they do not;
- when the reference says the sources differ, the reply gives both values and says the sources differ; a reply that presents one value as the only truth is wrong;
- when the reference starts with "Partial:", the reply gives the known part and says plainly what the sources do not cover; a reply that fills the gap with a guess is wrong;
- when the reference starts with "False premise:", the reply corrects the premise instead of going along with it.

Judge facts, not wording, length or style. Give a one or two sentence reason, then the verdict."""


class Verdict(BaseModel):
    reason: str
    correct: bool


def llm_verdict(model: str, question: str, reference: str, reply_text: str, chunk_ids: list[str]) -> dict:
    excerpts = "\n\n".join(excerpt(chunk_by_id[i]) for i in chunk_ids)
    response = client.beta.messages.parse(
        model=model,
        max_tokens=16000,
        system=JUDGE_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"<excerpts>\n{excerpts}\n</excerpts>\n\n<question>{question}</question>\n"
            f"<reference>{reference}</reference>\n<reply>{reply_text}</reply>",
        }],
        output_format=Verdict,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # if a safety classifier declines, the API retries on its recommended model
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"{model} stopped with {response.stop_reason!r}: {question}")
    tokens = {"in": response.usage.input_tokens, "out": response.usage.output_tokens}
    return response.parsed_output.model_dump() | {"by": model, "tokens": tokens}


def grade(group: dict, question: str, hits: list[Hit], reply: dict) -> dict:
    """Refusals are graded by the reply's `kind` field, not by its text (brief, decision 6)."""
    expects_refusal = not group["chunks"]
    if reply["kind"] == "error":
        return {"correct": False, "reason": f"pipeline error: {reply['message']}", "by": "code"}
    if expects_refusal:
        return {"correct": reply["kind"] == "refusal", "reason": "a refusal was expected", "by": "code"}
    if reply["kind"] == "refusal":
        return {"correct": False, "reason": "refused, but the sources answer this", "by": "code"}
    return llm_verdict(JUDGE_MODEL, question, group["answer"], reply["text"], [h.chunk.id for h in hits])


# ---------- commands ----------


def run(runs: int) -> Path:
    items = [(g, q) for g in groups for q in g["questions"]]
    print(f"{len(items)} questions x {runs} runs")
    query_vectors = embed([q for _, q in items], "query")  # one batch call, not 210
    retrieved = [search(v) for v in query_vectors]

    # Every (question, run) pair, in a fixed order; pool.map keeps that order.
    jobs = [(i, r) for i in range(len(items)) for r in range(runs)]
    with ThreadPoolExecutor(WORKERS) as pool:
        replies = list(pool.map(lambda job: ask(items[job[0]][1], retrieved[job[0]]), jobs))
        print("answers done, judging")
        verdicts = list(pool.map(
            lambda jr: grade(*items[jr[0][0]], retrieved[jr[0][0]], jr[1]), zip(jobs, replies)
        ))

    records = []
    for i, (g, q) in enumerate(items):
        ids = [h.chunk.id for h in retrieved[i]]
        acceptable = set(g["chunks"]) | alternatives.get(g["id"], set())
        records.append({
            "group": g["id"],
            "kind": g["kind"],
            "topic": g["topic"],
            "question": q,
            "expected_chunks": g["chunks"],
            "retrieved": [{"id": h.chunk.id, "score": round(h.score, 4)} for h in retrieved[i]],
            "retrieval": retrieval_metrics(ids, g["chunks"], acceptable) if g["chunks"] else None,
            "runs": [
                {"reply": replies[j], "verdict": verdicts[j]}
                for j, (qi, _) in enumerate(jobs) if qi == i
            ],
        })

    started = datetime.now()
    result = {
        "date": started.isoformat(timespec="seconds"),
        "snapshot": chunks[0].snapshot,
        "embed_model": EMBED_MODEL,
        "answer_model": ANSWER_MODEL,
        "judge_model": JUDGE_MODEL,
        "top_k": TOP_K,
        "runs": runs,
        "questions": records,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{started:%Y-%m-%dT%H%M}.json"
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out}")
    return out


def report(path: Path) -> str:
    result = json.loads(path.read_text(encoding="utf-8"))
    records = result["questions"]
    kinds = ["fact", "faq", "tricky", "no-answer"]

    lines = [
        f"Snapshot {result['snapshot']}, {result['embed_model']} top-{result['top_k']}, "
        f"answers {result['answer_model']}, judge {result['judge_model']}, {result['runs']} runs.",
        "",
        "Retrieval (questions whose answer is in the sources; F1 from mean precision and recall, as in the Cookbook):",
        "",
        "| Kind | Questions | Precision | Recall | F1 | MRR | Groups passed | hit@3 any |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for kind in [*kinds[:3], "all"]:
        rows = [r for r in records if r["retrieval"] and kind in (r["kind"], "all")]
        if not rows:
            continue
        m = {k: mean(r["retrieval"][k] for r in rows) for k in ("precision", "recall", "mrr", "hit_any")}
        f1 = 2 * m["precision"] * m["recall"] / (m["precision"] + m["recall"])
        by_group = defaultdict(list)
        for r in rows:
            by_group[r["group"]].append(r["retrieval"]["recall"] == 1)
        passed = sum(all(v) for v in by_group.values())
        lines.append(
            f"| {kind} | {len(rows)} | {m['precision']:.2f} | {m['recall']:.2f} | {f1:.2f} | {m['mrr']:.2f} "
            f"| {passed}/{len(by_group)} ({passed / len(by_group):.0%}) | {m['hit_any']:.0%} |"
        )

    lines += [
        "",
        "Answer accuracy (LLM judge; refusals graded by the reply's kind). Mean over runs, min-max in brackets:",
        "",
        "| Kind | Questions | Accuracy | Refused | Errors |",
        "|---|---|---|---|---|",
    ]
    for kind in [*kinds, "all"]:
        rows = [r for r in records if kind in (r["kind"], "all")]
        if not rows:
            continue
        per_run = [mean(r["runs"][i]["verdict"]["correct"] for r in rows) for i in range(result["runs"])]
        refused = mean(run["reply"]["kind"] == "refusal" for r in rows for run in r["runs"])
        errors = sum(run["reply"]["kind"] == "error" for r in rows for run in r["runs"])
        lines.append(
            f"| {kind} | {len(rows)} | {mean(per_run):.0%} ({min(per_run):.0%}-{max(per_run):.0%}) "
            f"| {refused:.0%} | {errors} |"
        )
    return "\n".join(lines)


def check(path: Path, n: int) -> None:
    """Re-grade a sample of the judge's LLM verdicts with CHECK_MODEL and measure agreement."""
    result = json.loads(path.read_text(encoding="utf-8"))
    if result["judge_model"] == CHECK_MODEL:
        raise SystemExit(f"{path} was judged by {CHECK_MODEL}; a model cannot check itself")
    by_id = {g["id"]: g for g in groups}
    judged = [
        (r, run) for r in result["questions"] for run in r["runs"] if run["verdict"]["by"] != "code"
    ]
    sample = random.Random(0).sample(judged, min(n, len(judged)))
    with ThreadPoolExecutor(WORKERS) as pool:
        second = list(pool.map(
            lambda s: llm_verdict(
                CHECK_MODEL, s[0]["question"], by_id[s[0]["group"]]["answer"], s[1]["reply"]["text"],
                [h["id"] for h in s[0]["retrieved"]],
            ),
            sample,
        ))

    rows = [
        {
            "group": r["group"],
            "question": r["question"],
            "reference": by_id[r["group"]]["answer"],
            "reply": run["reply"]["text"],
            "judge": run["verdict"],
            "check": v,
            "agree": run["verdict"]["correct"] == v["correct"],
        }
        for (r, run), v in zip(sample, second)
    ]
    out = path.with_name(f"{path.stem}-judge-check.json")
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    agreed = sum(row["agree"] for row in rows)
    print(f"{result['judge_model']} vs {CHECK_MODEL}: agree on {agreed}/{len(rows)} ({agreed / len(rows):.0%}) -> {out}")
    for row in rows:
        if not row["agree"]:
            print(f"- {row['group']}: judge {row['judge']['correct']}, check {row['check']['correct']}: {row['question']}")


def main() -> None:
    command, *args = sys.argv[1:]
    if command == "run":
        print(report(run(int(args[0]) if args else 3)))
    elif command == "report":
        print(report(Path(args[0])))
    elif command == "check":
        check(Path(args[0]), int(args[1]) if len(args) > 1 else 30)
    else:
        raise SystemExit(f"unknown command {command!r}; use run, report or check")


if __name__ == "__main__":
    main()
