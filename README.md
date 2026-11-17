# Wizz Air baggage assistant (RAG with evals)

A question-answering assistant for Wizz Air passengers about baggage. Every answer cites
the exact place in an official Wizz Air document it comes from. When the documents do not
answer the question, the assistant politely refuses and points to the Wizz Air Help Centre
instead of guessing.

The evaluation set was written before the pipeline, and the project measures the
pipeline against it: retrieval metrics and answer accuracy on 325 questions, following
the [Claude Cookbook RAG guide](https://platform.claude.com/cookbook/capabilities-retrieval-augmented-generation-guide).

**Live demo: [wizzair-rag-three.vercel.app](https://wizzair-rag-three.vercel.app/)**, the eval
explorer. Every question, every graded answer, what the search found and why the judge
decided as it did. It shows saved results and calls no model.

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
| faq | 19 | 19 | Questions as passengers ask them, taken from the Wizz Air FAQ (`source: wizzair-faq`) |
| tricky | 19 | 21 | False premises, edge cases, two sections at once, partial answers, off-topic |
| no-answer | 11 | 11 | Sound answerable but the sources do not answer them; a refusal is expected |

How the labels were made honest:

- One model drafted the groups; a second agent with a fresh context saw only the chunks
  and the questions, picked the chunks itself, and a human resolved the disagreements
  (87 of 87 labels were among the verifier's chunks).
- No-answer questions were generated, then a second agent tried hard to answer them from
  the chunks. Only those it could not answer stayed `no-answer`; partly answerable ones
  became `tricky` groups with a partial reference answer.

A second set, `evals/questions-external.json`, has 115 questions written by Gemini and GPT
from two fixed prompts (`evals/candidates/prompts.md`), to see whether Claude's own wording
flatters the metrics (compared kind for kind, question type matters more than the author; see
"What the numbers say"). Three subagents with fresh context labelled them blind and a fourth tried
to answer the partial ones completely (decision 12): 72 answerable, 30 partial, 12 off-topic,
1 unanswerable. Every report splits the numbers by `source` (claude, wizzair-faq, gemini,
gpt) and by kind within each source. The results below cover all 325 questions.

How it is scored:

- **Retrieval**, as in the Cookbook: precision, recall, F1 and MRR against the labelled
  chunks, per question and per group (a group passes when all its wordings found all
  its chunks). `hit@3 any` also counts other chunks that hold the same fact.
- **Answers**: refusals are graded from the `kind` field, not the text. Other replies go
  to an LLM judge (DeepSeek V4 Pro) that sees the question, the reference answer and
  the excerpts that hold the fact plus the ones the reply cites. On conflict groups only a reply with both values counts; on partial groups
  the reply must give the known part and say what the sources do not cover.
- **Judge check**: a second model from another family (Claude Sonnet 5.5) re-grades a random sample of the judge's verdicts without seeing them;
  disagreements are reviewed by hand.
- Retrieval is deterministic and runs once; answers run 3 times to show the spread.

## Results

One protocol for every number below (decisions 10 and 13), run on 2026-11-12 against the
snapshot of 2026-11-09: the answer schema that limits citations to the retrieved ids
(decision 11), 3 runs per combination, DeepSeek V4 Pro as the judge, Claude Sonnet 5.5
re-grading 30 verdicts per file. This replaces the earlier 210-question table (decision 10).
Raw results: `evals/results/2026-11-12T*.json`.

**Answer accuracy**, all 325 questions (mean over 3 runs; min-max in brackets for `all`).
A = top 3, B = top 10, C = top 10 reordered by a Voyage `rerank-2.5` reranker, best 3 kept:

| Kind | Questions | Haiku, A | Haiku, B | Haiku, whole corpus | Flash, A | Flash, B | Flash, C | Flash, whole corpus |
|---|---|---|---|---|---|---|---|---|
| fact | 159 | 88% | 89% | 87% | 86% | 90% | 89% | 92% |
| faq | 62 | 70% | 75% | 81% | 68% | 81% | 69% | 84% |
| tricky | 92 | 57% | 75% | 74% | 62% | 76% | 66% | 75% |
| no-answer | 12 | 100% | 89% | 97% | 97% | 97% | 94% | 97% |
| **all** | 325 | **76%** (74-78%) | **82%** (82-83%) | **82%** (81-84%) | **76%** (75-78%) | **85%** (83-86%) | **79%** (78-79%) | **86%** (84-86%) |
| Claude's questions (191) | | 87% | 88% | 87% | 85% | 90% | 88% | 90% |
| Wizz Air FAQ (19) | | 93% | 89% | 96% | 89% | 98% | 88% | 95% |
| Gemini's questions (59) | | 68% | 81% | 69% | 67% | 81% | 68% | 74% |
| GPT's questions (56) | | 41% | 62% | 76% | 51% | 67% | 55% | 78% |
| pipeline errors (of 975) | | 0 | 0 | 0 | 2 | 5 | 1 | 15 |

"Whole corpus" puts all 91 chunks (about 16k tokens by a character estimate; measured prompt
input is 31k (Haiku) and 20k (Flash)) in every prompt with no retrieval, as a
ceiling for what retrieval could give. DeepSeek Flash is DeepSeek V4.1 Flash through
DeepSeek's Anthropic-compatible API. C was run on Flash only; B on both models (decision 13).

**Retrieval** (296 questions whose answer is in the sources; the same for both answer models):

| Retrieval | Chunks to the model | Precision | Recall | F1 | MRR | Groups passed | any chunk with the fact |
|---|---|---|---|---|---|---|---|
| A: cosine | 3 | 0.31 | 0.86 | 0.46 | 0.74 | 148/188 (79%) | 97% |
| B: cosine | 10 | 0.11 | 0.98 | 0.19 | 0.76 | 180/188 (96%) | 100% |
| C: cosine + reranker | 3 | 0.33 | 0.92 | 0.49 | 0.84 | 162/188 (86%) | 98% |

On `tricky` questions alone recall is 0.71 (A), 0.95 (B) and 0.84 (C). Retrieval-only
numbers, before any answer model, are in `evaluate retrieval` (recall@3/5/10 with and without
the reranker). Precision is capped near 0.33 by design: most groups have one labelled chunk and
A and C always return three.

**Quality vs cost** (mean tokens per answer call over the 975 calls of each file, from the
`tokens` field; cached input tokens included in the input):

| Configuration | Accuracy | Input tokens per answer | Output tokens per answer | Answer cost per 1,000 answers (estimate) |
|---|---|---|---|---|
| Haiku, A: top 3 | 76% | 2.6k | 0.46k | ~$0.49 |
| Haiku, B: top 10 | 82% | 5.2k | 0.52k | ~$0.78 |
| Haiku, whole corpus | 82% | 31.4k | 0.61k | ~$3.44 |
| Flash, A: top 3 | 76% | 1.6k (1.1k cached) | 0.36k | not recorded |
| Flash, B: top 10 | 85% | 3.2k (1.0k cached) | 0.46k | not recorded |
| Flash, C: top 10, reranker, top 3 | 79% | 1.7k (1.0k cached) | 0.39k | not recorded, plus one reranker call |
| Flash, whole corpus | 86% | 20.2k (20.0k cached) | 0.45k | not recorded |

Haiku's estimate uses the price recorded in decision 13 ($0.10 / $0.50 per 1M input / output
tokens); judging is not included. Flash's output price is not recorded, so there is no
estimate for it. Haiku and Flash count tokens differently, so compare rows within a model.

**Judge check:** Sonnet agreed with the DeepSeek Pro judge on 198 of 210 sampled verdicts
(94%): 28/30 and 29/30 on the Haiku A and whole-corpus files, 29/30 on Flash A and the whole
corpus, 27/30 on Haiku B, 26/30 on Flash B, 30/30 on C. The 12 disagreements were reviewed
by hand (decision 17): Pro was wrong in 7, Sonnet in 4, one depends on the grading rule. Pro
marked 6 correct replies as wrong and 1 wrong reply as correct, so the absolute numbers are a
little low (about 3 points on the sample) for every answer model alike; the comparisons stand.

### What the numbers say

- **Retrieval limits the answers, and 10 chunks nearly remove the limit.** Top 3 gives 76%
  for both models; the whole corpus gives 82% (Haiku) and 86% (Flash). With 10 chunks Haiku
  reaches 82% and Flash 85%, within the whole-corpus ranges, with about a sixth of the whole
  corpus's input tokens (Flash). The gain is
  on `faq` (+13 points) and `tricky` (+14), where A misses a labelled chunk (recall 0.71 on
  `tricky`); on `fact` the answer model is the limit, not retrieval.
- **The reranker trades a little quality for cost; more chunks buy more quality.** Reranking
  the top 10 and keeping 3 raises recall at 3 from 0.86 to 0.92, MRR from 0.74 to 0.84, and
  answer accuracy from 76% to 79% (Flash; ranges 75-78% and 78-79% nearly touch). The model
  gets the same 3 chunks as in A, so the answer costs the same; the reranker call is small
  but adds latency and one more moving part. Ten
  chunks without a reranker (B) score higher (85% on Flash, 82% on Haiku) but double the
  input of every answer (about 5.2k tokens against 2.6k for Haiku). So the choice is quality
  (B) or cost (A, C). The reranker was measured on Flash only and did not clear the bar set
  before the run (decision 13), so it stays out on this 91-chunk corpus. On a larger corpus,
  where the top 10 by cosine loses recall, it is the likely candidate (not measured).
- **Question type matters more than who wrote the question.** Passenger-style answerable
  questions, top 3, Haiku: 93% for 19 questions taken from the Wizz Air FAQ, 88% for
  Claude's one-fact questions (159), 76% for Gemini's (21), 44% for GPT's (22). Recall at 3
  is similar (0.83-0.94), so retrieval is not the cause. For GPT's questions, 28 of 37 wrong
  replies omit a key fact (keyword heuristic); the rest are "not covered" replies, a missed
  false premise or a refusal. The questions ask for several facts at once and the answer
  misses one. Ten chunks help
  most there (GPT 44% to 62%); the reranker, which only reorders the same 3 chunks, helps
  less (Flash: 44% to 52%, against 59% for ten chunks). Samples are small (19-22 per
  source). Reference answers are per group, which penalises omitted details (decision 17),
  so absolute numbers for multi-part questions are low.
- **DeepSeek Flash is not better than Haiku at equal context**: with top 3 both score 76%.
  Flash wins with a long context (whole corpus 86% against 82%), but its 15 pipeline errors
  there (1.5% of answers) are format failures that count as wrong: broken JSON (6), a missing
  `reply` wrapper (5), a citation outside the allowed ids (4). Nothing constrains DeepSeek's
  output to the schema. Haiku had none, since the schema constrains its decoding.
- **Sub-clause citations are gone** for Haiku: the id enum of decision 11 made 0 errors in
  1,950 answers, where decision 10 had 14 in 1,260.
- **Haiku refuses more with the whole corpus on tricky questions** (26% against Flash's
  24%; with 10 chunks 22%); the earlier gap (29% against 16%) shrank on the larger set.
- **Retrieval misses have a pattern.** When a fact is in both a GCC clause and a Help
  Centre page, the GCC clause often wins the top 3 (damaged bags, valuables,
  e-cigarettes). A false premise ("my cat's carrier", "a 10 kg bag on the basic fare")
  pulls retrieval towards the premise, not the rule that corrects it.
- **Answers that miss a second fact.** Many wrong replies are right but incomplete: they
  give the size but not the price, or the deadline but not the liability limit.
- **Cost:** the matrix, B, C and the retrieval experiment took about $8.3 of DeepSeek
  credit (answers and 6 judged files); Haiku B added about $2.2 (judging; Haiku's Anthropic
  cost was not measured).

## Trade-offs

- **Frozen snapshots instead of live pages.** Metrics are comparable over time, but
  answers can be out of date, so every answer carries the snapshot date and a disclaimer.
- **One source unit = one chunk.** Citations point to a real place and text stays
  verbatim, but chunk sizes vary from 84 to ~5,900 characters.
- **Two kinds of source; on a conflict, show both.** The GCC is binding, the Help Centre
  is what passengers read. Picking one would mean the assistant decides for the passenger.
- **Cheap answer models under a stronger judge.** Haiku 5.5 and DeepSeek Flash keep the
  cost per answer tiny. The judge is DeepSeek V4 Pro and Sonnet 5.5 re-grades a sample of
  every run: judge and check come from different families, so a judge that goes easy on
  its own family shows up (decision 10).
- **Chunks vs cost.** More chunks raise answer quality and double the input; a reranker
  keeps the input of 3 chunks but adds a call.
- **No vector database.** 91 chunks (about 16k tokens by a character estimate; measured
  prompt input is 31k (Haiku) and 20k (Flash)) fit in a numpy matrix.
- **The judge sees the excerpts.** Without them it graded correct replies as wrong from
  its own idea of Wizz Air rules. With them it can accept an extra detail that is true in
  an excerpt but off the point.
- **Synthetic questions.** Model-written wordings are cleaner than real ones; 19 questions
  taken from the Wizz Air FAQ are in the set to offset that.

The full reasoning is in [docs/decisions.md](docs/decisions.md).

## Run it

Needs Python 3.14 and [uv](https://docs.astral.sh/uv/), plus Anthropic, Voyage AI (embeddings and reranker) and DeepSeek API
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

Demo page (runs locally, no deploy, no extra dependencies):

```bash
uv run --env-file .env python -m wizzair_rag.demo   # then open http://127.0.0.1:8000
```

Type a question or click an example. The page shows the answer with its cited sources, the
standard refusal when the documents say nothing, and the chunks the search found with their
scores, so you can see what the answer was built from.

Eval explorer (`web/`, a static Next.js site with the saved results; it calls no model):

```bash
uv run python -m wizzair_rag.export_site   # evals/results -> web/data/*.json (needs the local chunks)
cd web && npm install
echo "NEXT_PUBLIC_REPO_URL=<this repo's GitHub URL>" > .env.local
npm run dev                                 # or `npm run build`: static files in web/out
```

It shows every question with what the search found, the three answers of each setup, the
judge's reasons and the second judge's verdict where it re-graded one. The site gets chunk
titles and URLs, never chunk text.

Evals:

```bash
uv run --env-file .env python -m wizzair_rag.evaluate run 3        # writes evals/results/<date>T<time>-<model>.json
uv run --env-file .env python -m wizzair_rag.evaluate run 1 full   # whole corpus in the prompt, no retrieval
uv run --env-file .env python -m wizzair_rag.evaluate run 3 deepseek-flash   # another answer model (DEEPSEEK_API_KEY in .env)
uv run --env-file .env python -m wizzair_rag.evaluate run 1 sample=15        # smoke test: a fixed sample of 15 questions
uv run --env-file .env python -m wizzair_rag.evaluate run 3 deepseek-flash k=10   # retrieve 10 chunks instead of 3
uv run --env-file .env python -m wizzair_rag.evaluate run 3 rerank deepseek-flash   # top 10 reordered by a reranker, best 3 kept
uv run --env-file .env python -m wizzair_rag.evaluate retrieval   # retrieval only: recall@3/5/10 and MRR, with and without the reranker (cents)
uv run --env-file .env python -m wizzair_rag.evaluate judge evals/results/<file>.json     # judge only the replies without a verdict
uv run --env-file .env python -m wizzair_rag.evaluate regrade evals/results/<file>.json   # re-judge all saved replies
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

1. **Level 2 was measured and does not help here** (decision 16): summaries added to the embedded
   text give recall@3 0.87 against 0.86 for plain cosine; the reranker gives 0.92. The default
   stays at 3 chunks and the reranker stays out for now (decision 15); both come back for review
   when the corpus grows.
2. **Constrain or repair DeepSeek's output**, if it becomes the default answer model: its
   format errors are the only thing that keeps it behind in the whole-corpus run.
3. **Fix the grading rule found in decision 17**: a reference answer per question, not per group, so
   a reply is not marked down for facts its wording did not ask about.
