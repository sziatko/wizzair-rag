"""A5: run every eval question through the Level 1 pipeline, score retrieval like the
Cookbook, and let an LLM judge the answers against the reference answers.

Run:    uv run --env-file .env python -m wizzair_rag.evaluate run [runs] [full] [rerank] [k=N] [sample=N] [answer model]
        default 3 runs, top 3 and claude-haiku-5-5; "full" puts the whole corpus in every
        prompt, with no retrieval (a baseline for RAG); k=10 retrieves 10 chunks; sample=20
        runs a fixed random sample of 20 questions (a smoke test); a model named deepseek-*
        goes to DeepSeek. The answers are saved before judging, so a judge failure loses none.
Judge:  uv run --env-file .env python -m wizzair_rag.evaluate judge evals/results/<file>.json
        judges only the replies that have no verdict yet (finishes a run the judge broke off)
Regrade: uv run --env-file .env python -m wizzair_rag.evaluate regrade evals/results/<file>.json
        re-judges all saved replies in place, without asking for new answers
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
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from statistics import mean

import anthropic
from pydantic import BaseModel, ValidationError

from wizzair_rag.index import EMBED_MODEL, embed, load_index
from wizzair_rag.rag import ANSWER_MODEL, RERANK_MODEL, RERANK_POOL, TOP_K, Hit, chunks, deepseek_parse, excerpt, generate, rerank, search, usage_of

# DeepSeek V4 Pro judges every reply; Sonnet 5.5 re-grades a sample. One judge for the whole
# matrix, and the check comes from the other family, so a judge going easy on answers from
# its own family shows up (decision 10).
JUDGE_MODEL = "deepseek-v4-pro"
CHECK_MODEL = "claude-sonnet-5-5"
RESULTS_DIR = Path("evals/results")
WORKERS = 8  # parallel API calls
JUDGE_ATTEMPTS = 3  # a DeepSeek judge is asked again when its JSON misses the schema

# questions.json was written by Claude; questions-external.json carries its own `source`
# (Gemini, GPT) and was labelled by a blind verifier (decision 12).
groups = [{"source": "claude"} | g for g in json.loads(Path("evals/questions.json").read_text(encoding="utf-8"))]
groups += json.loads(Path("evals/questions-external.json").read_text(encoding="utf-8"))
# Chunks the blind verifier also found the fact in (decision 4). They are not labels:
# they only feed the secondary "hit@k any" column.
alternatives = {
    b["id"]: set(b["chunks"])
    for f in ("evals/blind-check-2026-11-11.json", "evals/blind-check-2026-11-12.json")
    for b in json.loads(Path(f).read_text(encoding="utf-8"))
}
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


def ask(question: str, hits: list[Hit], model: str) -> dict:
    """One reply as plain data, with the tokens and seconds of the call. A broken reply
    (citations outside the retrieved chunks, a cut-off output, JSON that does not match the
    schema) is a real failure of the pipeline: it is recorded and graded wrong, so one bad
    reply does not stop a run of 600. Its tokens are unknown, its seconds are not."""
    started = time.perf_counter()
    try:
        result = generate(question, hits, model)
        return {"reply": result.reply.model_dump(), "tokens": result.tokens, "seconds": round(result.seconds, 2)}
    except (ValueError, RuntimeError) as e:
        return {"reply": {"kind": "error", "message": str(e)}, "tokens": None, "seconds": round(time.perf_counter() - started, 2)}


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
    user = (
        f"<excerpts>\n{excerpts}\n</excerpts>\n\n<question>{question}</question>\n"
        f"<reference>{reference}</reference>\n<reply>{reply_text}</reply>"
    )
    if model.startswith("deepseek"):
        # A verdict has no "error" grade, and a raise here would lose a run's paid answers,
        # so a reply that misses the schema is asked again (decision 10).
        for attempt in range(JUDGE_ATTEMPTS):
            try:
                parsed, response = deepseek_parse(model, JUDGE_SYSTEM, user, Verdict)
                break
            except ValidationError:
                if attempt == JUDGE_ATTEMPTS - 1:
                    raise
    else:
        response = client.beta.messages.parse(
            model=model,
            max_tokens=16000,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_format=Verdict,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # if a safety classifier declines, the API retries on its recommended model
        )
        parsed = response.parsed_output
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"{model} stopped with {response.stop_reason!r}: {question}")
    return parsed.model_dump() | {"by": model, "tokens": usage_of(response)}


def judge_excerpts(group: dict, answer: dict) -> list[str]:
    """The chunks the judge reads, the same in RAG and full-corpus mode (decision 10): the
    ones that hold the fact (labels + blind-check alternatives) and the ones the answer
    cites, so a true detail from a cited chunk is not graded as unsupported. All 91 chunks
    in every verdict would cost ~$10 a run."""
    return sorted(set(group["chunks"]) | alternatives.get(group["id"], set()) | set(answer["citations"]))


def grade(group: dict, question: str, reply: dict) -> dict:
    """Refusals are graded by the reply's `kind` field, not by its text (brief, decision 6)."""
    expects_refusal = not group["chunks"]
    if reply["kind"] == "error":
        return {"correct": False, "reason": f"pipeline error: {reply['message']}", "by": "code"}
    if expects_refusal:
        return {"correct": reply["kind"] == "refusal", "reason": "a refusal was expected", "by": "code"}
    if reply["kind"] == "refusal":
        return {"correct": False, "reason": "refused, but the sources answer this", "by": "code"}
    return llm_verdict(JUDGE_MODEL, question, group["answer"], reply["text"], judge_excerpts(group, reply))


# ---------- commands ----------


def run(runs: int, full: bool, model: str, k: int, sample: int | None, rerank_pool: bool = False) -> Path:
    items = [(g, q) for g in groups for q in g["questions"]]
    if sample:
        items = random.Random(0).sample(items, sample)  # a fixed sample: smoke tests are comparable
    print(f"{len(items)} questions x {runs} runs, answers by {model}")
    if full:
        retrieved = [[Hit(c, 0.0) for c in chunks]] * len(items)  # the answer model sees every chunk
    else:
        query_vectors = embed([q for _, q in items], "query")  # one batch call, not one per question
        if rerank_pool:  # variant C: the top RERANK_POOL by cosine, reordered, the best k kept
            pools = [search(v, RERANK_POOL) for v in query_vectors]
            with ThreadPoolExecutor(WORKERS) as pool:
                retrieved = list(pool.map(lambda p: rerank(p[0][1], p[1], k), zip(items, pools)))
        else:
            retrieved = [search(v, k) for v in query_vectors]

    # Every (question, run) pair, in a fixed order; pool.map keeps that order.
    jobs = [(i, r) for i in range(len(items)) for r in range(runs)]
    with ThreadPoolExecutor(WORKERS) as pool:
        replies = list(pool.map(lambda job: ask(items[job[0]][1], retrieved[job[0]], model), jobs))

    records = []
    for i, (g, q) in enumerate(items):
        ids = [h.chunk.id for h in retrieved[i]]
        acceptable = set(g["chunks"]) | alternatives.get(g["id"], set())
        records.append({
            "group": g["id"],
            "source": g["source"],
            "kind": g["kind"],
            "topic": g["topic"],
            "question": q,
            "expected_chunks": g["chunks"],
            "retrieved": [] if full else [{"id": h.chunk.id, "score": round(h.score, 4)} for h in retrieved[i]],
            "retrieval": retrieval_metrics(ids, g["chunks"], acceptable) if g["chunks"] and not full else None,
            "runs": [{**replies[j], "verdict": None} for j, (qi, _) in enumerate(jobs) if qi == i],
        })

    started = datetime.now()
    result = {
        "date": started.isoformat(timespec="seconds"),
        "snapshot": chunks[0].snapshot,
        "embed_model": EMBED_MODEL,
        "answer_model": model,
        "judge_model": JUDGE_MODEL,
        "top_k": "all" if full else k,
        "rerank": rerank_pool,
        "runs": runs,
        "questions": records,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ("-full" if full else "-rerank" if rerank_pool else "" if k == TOP_K else f"-k{k}") + (f"-sample{sample}" if sample else "")
    out = RESULTS_DIR / f"{started:%Y-%m-%dT%H%M}-{model}{suffix}.json"
    # Saved before judging: the answers are paid for, and the judge may still fail.
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"answers saved -> {out}, judging")
    judge_pending(out)
    return out


def judge_pending(path: Path) -> None:
    """Judge the replies that have no verdict yet and save the file."""
    result = json.loads(path.read_text(encoding="utf-8"))
    by_id = {g["id"]: g for g in groups}
    pending = [(r, run) for r in result["questions"] for run in r["runs"] if run["verdict"] is None]
    with ThreadPoolExecutor(WORKERS) as pool:
        verdicts = list(pool.map(lambda p: grade(by_id[p[0]["group"]], p[0]["question"], p[1]["reply"]), pending))
    for (_, run), v in zip(pending, verdicts):
        run["verdict"] = v
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"judged {len(pending)} replies -> {path}")


def report(path: Path) -> str:
    result = json.loads(path.read_text(encoding="utf-8"))
    records = result["questions"]
    if any(run["verdict"] is None for r in records for run in r["runs"]):
        raise SystemExit(f"{path} has replies without a verdict; run `judge` on it first")
    kinds = ["fact", "faq", "tricky", "no-answer"]
    source = lambda r: r.get("source", "claude")  # results from before decision 12 hold only Claude's questions

    lines = [
        f"Snapshot {result['snapshot']}, {result['embed_model']} top-{result['top_k']}, "
        f"answers {result['answer_model']}, judge {result['judge_model']}, {result['runs']} runs.",
        "",
        "Retrieval (questions whose answer is in the sources; F1 from mean precision and recall, as in the Cookbook):",
        "",
        f"| Kind | Questions | Precision | Recall | F1 | MRR | Groups passed | hit@{result['top_k']} any |",
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

    lines += [
        "",
        "By who wrote the questions (accuracy as above; recall over questions whose answer is in the sources):",
        "",
        "| Source | Questions | Accuracy | Refused | Errors | Recall |",
        "|---|---|---|---|---|---|",
    ]
    for src in sorted({source(r) for r in records}):
        rows = [r for r in records if source(r) == src]
        per_run = [mean(r["runs"][i]["verdict"]["correct"] for r in rows) for i in range(result["runs"])]
        refused = mean(run["reply"]["kind"] == "refusal" for r in rows for run in r["runs"])
        errors = sum(run["reply"]["kind"] == "error" for r in rows for run in r["runs"])
        with_recall = [r["retrieval"]["recall"] for r in rows if r["retrieval"]]
        recall = f"{mean(with_recall):.2f}" if with_recall else "-"
        lines.append(f"| {src} | {len(rows)} | {mean(per_run):.0%} ({min(per_run):.0%}-{max(per_run):.0%}) | {refused:.0%} | {errors} | {recall} |")

    if "seconds" in records[0]["runs"][0]:  # results from before decision 12 did not record them
        calls = [run for r in records for run in r["runs"]]
        counted = [run["tokens"] for run in calls if run["tokens"]]
        lines += [
            "",
            f"Answer calls: {len(calls)}, mean {mean(run['seconds'] for run in calls):.1f} s each; tokens in "
            f"{sum(t['in'] for t in counted):,} (+ {sum(t['cached'] for t in counted):,} cached), out {sum(t['out'] for t in counted):,} "
            f"({len(calls) - len(counted)} calls with an error have no count).",
        ]
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
                judge_excerpts(by_id[s[0]["group"]], s[1]["reply"]),
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


def regrade(path: Path) -> None:
    """Re-judge a run's saved replies with the current judge rules; no new answers.
    The file is rewritten in place: its old verdicts came from rules that are gone."""
    result = json.loads(path.read_text(encoding="utf-8"))
    for r in result["questions"]:
        for run in r["runs"]:
            run["verdict"] = None
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    judge_pending(path)


def retrieval_only(pool_size: int = 10) -> str:
    """Decision 13, step 1: recall@3/5/10 and MRR of plain top-k and of top-10 reordered by a
    Voyage reranker. No answer model, no judge: costs cents. Only questions whose answer is in
    the sources (non-empty labels) count."""
    items = [(g, q) for g in groups for q in g["questions"] if g["chunks"]]
    vectors_q = embed([q for _, q in items], "query")
    pools = [search(v, pool_size) for v in vectors_q]
    # Level 2 (decision 16): the same questions against the summary indexes
    summary_pools = {v: [search(q, pool_size, load_index(chunks, f"-{v}")) for q in vectors_q] for v in ("s1", "s2")}

    with ThreadPoolExecutor(WORKERS) as ex:
        reranked = list(ex.map(lambda p: rerank(p[0][1], p[1], len(p[1])), zip(items, pools)))

    def row(label: str, rows: list[int], lists: list[list[Hit]]) -> str:
        cells = []
        for k in (3, 5, 10):
            m = [retrieval_metrics([h.chunk.id for h in lists[i][:k]], items[i][0]["chunks"], set(items[i][0]["chunks"]) | alternatives.get(items[i][0]["id"], set())) for i in rows]
            cells += [f"{mean(x['recall'] for x in m):.2f}", f"{mean(x['hit_any'] for x in m):.0%}"]
        mrr = mean(retrieval_metrics([h.chunk.id for h in lists[i]], items[i][0]["chunks"], set())["mrr"] for i in rows)
        return f"| {label} | {len(rows)} | " + " | ".join(cells) + f" | {mrr:.2f} |"

    lines = [
        f"Retrieval only, {EMBED_MODEL}, reranker {RERANK_MODEL} on the top {pool_size}.",
        "",
        "| Kind / order | Questions | recall@3 | any@3 | recall@5 | any@5 | recall@10 | any@10 | MRR@10 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for kind in ("faq", "tricky", "all"):
        rows = [i for i, (g, _) in enumerate(items) if kind in (g["kind"], "all")]
        lines += [row(f"{kind}, cosine", rows, pools), row(f"{kind}, reranked", rows, reranked)]
        lines += [row(f"{kind}, summary {name}", rows, p) for name, p in summary_pools.items()]
    return "\n".join(lines)


def main() -> None:
    command, *args = sys.argv[1:]
    if command == "retrieval":
        print(retrieval_only())
    elif command == "run":
        opts = {a.split("=")[0]: int(a.split("=")[1]) for a in args[1:] if "=" in a}
        model = next((a for a in args[1:] if a not in ("full", "rerank") and "=" not in a), ANSWER_MODEL)
        print(report(run(int(args[0]) if args else 3, "full" in args[1:], model, opts.get("k", TOP_K), opts.get("sample"), "rerank" in args[1:])))
    elif command == "judge":
        judge_pending(Path(args[0]))
        print(report(Path(args[0])))
    elif command == "regrade":
        regrade(Path(args[0]))
        print(report(Path(args[0])))
    elif command == "report":
        print(report(Path(args[0])))
    elif command == "check":
        check(Path(args[0]), int(args[1]) if len(args) > 1 else 30)
    else:
        raise SystemExit(f"unknown command {command!r}; use run, judge, regrade, report or check")


if __name__ == "__main__":
    main()
