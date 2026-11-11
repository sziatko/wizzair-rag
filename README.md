# Wizz Air baggage assistant (RAG with evals)

A question-answering assistant for Wizz Air passengers about baggage. Every answer cites
the exact place in an official Wizz Air document it comes from. When the documents do not
answer the question, the assistant politely refuses and points to the Wizz Air Help Centre
instead of guessing.

The evaluation set was written before the pipeline, and the project measures the
pipeline against it: retrieval metrics and answer accuracy on 210 questions, following
the [Claude Cookbook RAG guide](https://platform.claude.com/cookbook/capabilities-retrieval-augmented-generation-guide).

This is a personal project, not affiliated with Wizz Air. Answers are not official advice.

## What it does

```
$ uv run --env-file .env python -m wizzair_rag.rag "Can I take a 12 kg bag into the cabin?"
```

1. **Sources.** The General Conditions of Carriage of Wizz Air Hungary (PDF, the binding
   contract), the Help Centre baggage pages, the fees table and the fares and bundles page.
   They are saved as a frozen, dated snapshot so metrics stay comparable.
2. **Chunks.** One unit of the source document is one chunk: a Help Centre accordion item,
   a GCC clause with its sub-items, a bundle, a fee group. 91 chunks. The text is
   verbatim; ids come from the document (`gcc-wah-2023-03-01#15.1.6`), so eval labels
   survive a re-download.
3. **Retrieval.** Voyage AI `voyage-4-large` embeddings of headings plus text, an
   in-memory numpy matrix, top 3 chunks by cosine similarity.
4. **Answer.** Claude Haiku 5.5 answers from the three excerpts with structured output:
   either `{kind: "answer", text, citations}` or `{kind: "refusal"}`. Citations must be
   among the retrieved chunks, or the run fails loudly. The refusal message and the
   disclaimer are fixed strings in code.
5. **Conflicts.** The Help Centre and the GCC sometimes disagree (for example the
   declared-value limit: 2,500 EUR vs 2,224 SDR, approx. EUR 2,800). The assistant then
   gives both values with both citations and says the sources differ.

## Evaluation

`evals/questions.json`: 102 groups, 210 questions. A group is one fact from the rules
with its labelled chunk(s), a reference answer and 1–3 wordings of the question.

| Kind | Groups | Questions | What it tests |
|---|---|---|---|
| fact | 53 | 159 | One fact; three wordings each (formal, search-style, a passenger's situation) |
| faq | 19 | 19 | Questions as real passengers ask them |
| tricky | 19 | 21 | False premises, edge cases, two sections at once, partial answers, off-topic |
| no-answer | 11 | 11 | Sound answerable but the sources do not answer them; a refusal is expected |

How the labels were made honest:

- One model drafted the groups; a second agent with a fresh context saw only the chunks
  and the questions, picked the chunks itself, and a human resolved the disagreements
  (87 of 87 labels were among the verifier's chunks).
- No-answer questions were generated, then a second agent tried hard to answer them from
  the chunks. Only those it could not answer stayed `no-answer`; partly answerable ones
  became `tricky` groups with a partial reference answer.

How it is scored:

- **Retrieval**, as in the Cookbook: precision, recall, F1 and MRR against the labelled
  chunks, per question and per group (a group passes when all its wordings found all
  its chunks). `hit@3 any` also counts other chunks that hold the same fact.
- **Answers**: refusals are graded from the `kind` field, not the text. Other replies go
  to an LLM judge (Claude Sonnet 5.5; the baseline below was judged by Claude Opus 5.5)
  that sees the question, the reference answer and the
  excerpts. On conflict groups only a reply with both values counts; on partial groups
  the reply must give the known part and say what the sources do not cover.
- **Judge check**: a second model (Claude Opus 5.5 now, Claude Sonnet 5.5 for the
  baseline) re-grades a random sample of the judge's verdicts without seeing them;
  disagreements are reviewed by hand.
- Retrieval is deterministic and runs once; answers run 3 times to show the spread.

## Results

Level 1 baseline, run on 2026-11-11 against the snapshot of 2026-11-09:
`voyage-4-large` top 3, answers by Claude Haiku 5.5, judge Claude Opus 5.5, 3 runs.
Raw results: `evals/results/2026-11-11T1824.json`.

**Retrieval** (194 questions whose answer is in the sources):

| Kind | Questions | Precision | Recall | F1 | MRR | Groups passed | hit@3 any |
|---|---|---|---|---|---|---|---|
| fact | 159 | 0.33 | 0.93 | 0.48 | 0.82 | 44/53 (83%) | 98% |
| faq | 17 | 0.33 | 0.94 | 0.49 | 0.85 | 16/17 (94%) | 100% |
| tricky | 18 | 0.39 | 0.69 | 0.50 | 0.75 | 10/16 (62%) | 83% |
| all | 194 | 0.33 | 0.91 | 0.49 | 0.81 | 70/86 (81%) | 97% |

Precision is capped near 0.33 by design: most groups have one labelled chunk and the
pipeline always returns three. F1 is computed from mean precision and recall, as in the
Cookbook.

**Answer accuracy** (mean over 3 runs, min–max in brackets):

| Kind | Questions | Accuracy | Refused | Pipeline errors |
|---|---|---|---|---|
| fact | 159 | 84% (82–85%) | 1% | 2 |
| faq | 19 | 93% (89–95%) | 11% | 0 |
| tricky | 21 | 76% (71–81%) | 19% | 0 |
| no-answer | 11 | 45% (36–55%) | 45% | 1 |
| all | 210 | 82% (81–82%) | 6% | 3 |

**Judge check:** Claude Sonnet 5.5 re-graded 30 random verdicts blind and agreed on
29 (97%). In the one disagreement, a manual review sided with the Opus judge.
Judging all 3 runs cost about $7.40 (1.28M input and 117k output tokens on Opus 5.5).
Given that agreement, later runs use Claude Sonnet 5.5 as the judge (about $3.70 for the
same volume) and Opus 5.5 re-grades a sample of 30 (about $0.30).

### What the numbers say

- **Retrieval is mostly fine; the misses have a pattern.** When a fact is in both a GCC
  clause and a Help Centre page, the GCC clause often wins the top 3 (damaged bags,
  valuables, e-cigarettes). `hit@3 any` at 97% shows that most "misses" still retrieved
  a chunk with the fact, but not always the most complete one. Tricky questions suffer
  most: a false premise ("my cat's carrier", "a 10 kg bag on the basic fare") pulls
  retrieval towards the premise, not the rule that corrects it.
- **Refusals are the weak spot.** On no-answer questions Haiku often replies with
  `kind: "answer"` and text like "the excerpts don't say how late you can add a bag".
  The wording is right, but the structured refusal flag is not set, so the passenger
  does not get the standard Help Centre message. This is the A4 finding, now measured:
  the prompt's rule for partial answers competes with the rule to refuse.
- **Haiku sometimes invents a conflict.** The prompt's conflict rule ("if sources differ,
  give both") makes it call two unrelated clauses a disagreement (for example a reporting
  deadline vs the "bag is lost after 21 days" rule). It also hedges with "probably not"
  where an exclusion clause gives a clear no.
- **Answers that miss a second fact.** Many wrong replies are right but incomplete: they
  give the size but not the price, or the deadline but not the liability limit, often
  because the second chunk was not retrieved.
- **3 pipeline errors in 630 replies:** Haiku cited a sub-clause id (`15.1.6.3`) that is
  part of a retrieved chunk but is not a chunk id. The run records it as a wrong answer.
- **Synthetic vs real wording:** FAQ questions score as well as or better than the
  model-written fact questions, so there is no sign that one model's wording inflates
  the metrics.

## Trade-offs

- **Frozen snapshots instead of live pages.** Metrics are comparable over time, but
  answers can be out of date, so every answer carries the snapshot date and a disclaimer.
- **One source unit = one chunk.** Citations point to a real place and text stays
  verbatim, but chunk sizes vary from 84 to ~5,900 characters.
- **Two kinds of source; on a conflict, show both.** The GCC is binding, the Help Centre
  is what passengers read. Picking one would mean the assistant decides for the passenger.
- **A cheap answer model under a stronger judge.** Haiku 5.5 keeps the cost per answer
  tiny. The judge is Sonnet 5.5, not Opus 5.5: it costs half as much and agreed with
  Opus on 29 of 30 verdicts. Opus still re-grades a sample of every run, so drift shows.
- **No vector database.** 91 chunks (~16k tokens) fit in a numpy matrix.
- **The judge sees the excerpts.** Without them it graded correct replies as wrong from
  its own idea of Wizz Air rules. With them it can accept an extra detail that is true in
  an excerpt but off the point.
- **Synthetic questions.** Model-written wordings are cleaner than real ones; FAQ-style
  questions are in the set to offset that.

The full reasoning is in [docs/decisions.md](docs/decisions.md).

## Run it

Needs Python 3.14 and [uv](https://docs.astral.sh/uv/), plus Anthropic and Voyage AI API
keys. Copy `.env.example` to `.env` and fill in the keys.

```bash
uv sync
uv run python -m wizzair_rag.download          # saves a dated snapshot under data/raw/
uv run python -m wizzair_rag.chunks            # data/chunks/<snapshot>/chunks.jsonl
uv run --env-file .env python -m wizzair_rag.index
uv run --env-file .env python -m wizzair_rag.rag "Can I take a 12 kg bag into the cabin?"
```

Downloaded Wizz Air documents are not in the repository; `download.py` fetches them. The
fees table is rendered by JavaScript and was saved once by hand (`fees-table.txt`).

Evals:

```bash
uv run --env-file .env python -m wizzair_rag.evaluate run 3        # writes evals/results/<date>T<time>.json
uv run python -m wizzair_rag.evaluate report evals/results/<file>.json
uv run --env-file .env python -m wizzair_rag.evaluate check evals/results/<file>.json 30
```

Tests (need a local snapshot):

```bash
uv run python tests/test_chunks.py
uv run python tests/test_questions.py
uv run --env-file .env python tests/test_metrics.py
```

## Next

Measured improvements on the same evals: summary indexing and re-ranking, a
"whole corpus in the prompt" baseline (the corpus is only ~16k tokens), and question
wordings from a different model family.
