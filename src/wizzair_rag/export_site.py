"""Export what the eval explorer site (web/) shows, as compact JSON in web/data/.

Run: uv run python -m wizzair_rag.export_site

Needs the local data/: the chunks of the snapshot the runs answered from (for titles and URLs),
and the vector index, because importing evaluate imports rag, which loads it.
The site gets chunk titles and URLs, never chunk text: data/ is not published (see .gitignore),
web/data/ is committed so the site builds from a clone.
Metrics come from evaluate.metrics, the same numbers `evaluate report` prints.
"""

import json
from collections import Counter
from pathlib import Path

from wizzair_rag.chunks import load_chunks
from wizzair_rag.evaluate import CHECK_MODEL, RESULTS_DIR, groups, load_judged, metrics
from wizzair_rag.rag import RERANK_POOL

SITE_DATA = Path("web/data")
# The final matrix of 2026-11-12 (decision 14): 7 configurations, 325 questions each, 3 runs.
RUNS = "2026-11-12T*.json"
MODELS = {
    "claude-haiku-5-5": "Claude Haiku 5.5",
    "deepseek-flash": "DeepSeek V4.1 Flash",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
}


def retrieval_label(result: dict) -> str:
    if result["top_k"] == "all":
        return "Whole corpus, no retrieval"
    if result.get("rerank"):
        return f"Top {RERANK_POOL}, reranked to {result['top_k']}"
    return f"Top {result['top_k']}"


def question_ids() -> dict[tuple[str, str], str]:
    """A stable URL id per question: its group id and its place in the group."""
    ids = {(g["id"], q): f"{g['id']}-{i}" for g in groups for i, q in enumerate(g["questions"], 1)}
    if dupes := [i for i, n in Counter(ids.values()).items() if n > 1]:
        raise ValueError(f"duplicate question ids: {dupes}")
    return ids


def run_view(run: dict) -> dict:
    reply, verdict = run["reply"], run["verdict"]
    return reply | {"correct": verdict["correct"], "reason": verdict["reason"], "by": verdict["by"]}


def checked_run(check: dict, runs: list[dict], where: str) -> int:
    """The run a second-judge row grades. Rows written before `check` stored the run number
    match by reply text; when several runs share that text their verdicts must agree,
    or the site could show "agrees" on the wrong run."""
    if "run" in check:
        return check["run"]
    same = [i for i, run in enumerate(runs) if run.get("text") == check["reply"]]
    if not same:
        raise ValueError(f"{where}: a judge-check row matches no reply")
    if len({runs[i]["correct"] for i in same}) > 1:
        raise ValueError(f"{where}: a judge-check row matches runs {same} with different verdicts")
    return same[0]


def export() -> tuple[list[dict], list[dict], dict]:
    ids = question_ids()
    by_group = {g["id"]: g for g in groups}
    questions: dict[str, dict] = {}
    configs = []
    for path in sorted(p for p in RESULTS_DIR.glob(RUNS) if not p.stem.endswith("-judge-check")):
        result = load_judged(path)
        config = path.stem.split("-", 3)[3]  # 2026-11-12T1503-claude-haiku-5-5 -> claude-haiku-5-5
        checks: dict[tuple[str, str], list[dict]] = {}
        for c in json.loads(path.with_name(f"{path.stem}-judge-check.json").read_text(encoding="utf-8")):
            checks.setdefault((c["group"], c["question"]), []).append(c)
        sampled = sum(map(len, checks.values()))
        configs.append({
            "id": config,
            "model": MODELS[result["answer_model"]],
            "retrieval": retrieval_label(result),
            "top_k": result["top_k"],
            "rerank": bool(result.get("rerank")),
            "date": result["date"],
            "snapshot": result["snapshot"],
            "judge": MODELS[result["judge_model"]],
            "check": {"model": MODELS[CHECK_MODEL], "sampled": sampled, "agreed": sum(c["agree"] for cs in checks.values() for c in cs)},
            "metrics": metrics(result),
        })
        for r in result["questions"]:
            qid = ids[(r["group"], r["question"])]
            g = by_group[r["group"]]
            q = questions.setdefault(qid, {
                "id": qid, "group": g["id"], "question": r["question"], "kind": g["kind"], "topic": g["topic"],
                "source": g["source"], "reference": g["answer"], "expected": g["chunks"], "configs": {},
            })
            runs = [run_view(run) for run in r["runs"]]
            # The sampled runs, if this question was in the second judge's sample.
            for c in checks.pop((r["group"], r["question"]), []):
                i = checked_run(c, runs, f"{path.name}: {qid}")
                if "check" in runs[i]:
                    raise ValueError(f"{path.name}: {qid}: two judge-check rows grade run {i}")
                runs[i]["check"] = {"correct": c["check"]["correct"], "reason": c["check"]["reason"]}
            q["configs"][config] = {"retrieved": [[h["id"], round(h["score"], 3)] for h in r["retrieved"]], "runs": runs}
        if checks:
            raise ValueError(f"{path.name}: {sum(map(len, checks.values()))} judge-check rows match no question")
    # Shown once for the whole site (footer, findings), so every config must agree on them.
    shared = {(c["snapshot"], c["judge"], c["check"]["model"]) for c in configs}
    if len(shared) != 1:
        raise ValueError(f"configs differ in snapshot, judge or check model: {shared}")
    # The chunks the runs answered from, not the latest download: ids can outlive a snapshot.
    chunks = {c.id: {"title": " > ".join(c.path), "url": c.url} for c in load_chunks(configs[0]["snapshot"])}
    return configs, list(questions.values()), chunks


def main() -> None:
    configs, questions, chunks = export()
    assert len(configs) == 7 and len(questions) == 325, (len(configs), len(questions))
    assert all(len(q["configs"]) == 7 and all(len(c["runs"]) == 3 for c in q["configs"].values()) for q in questions)
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    for name, data in (("configs", configs), ("questions", questions), ("chunks", chunks)):
        out = SITE_DATA / f"{name}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{out}: {out.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
