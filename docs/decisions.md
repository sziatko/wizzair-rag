# Decisions and trade-offs

Short log of choices made while building the project. The README summarises them;
this file keeps the reasoning. Newest last.

## 1. Frozen, dated snapshots instead of live pages (2026-11-09)

- **Choice:** `download.py` saves every source into `data/raw/<date>/` with a manifest
  (URL, time, sha256). Chunks, the index and evals point at one snapshot.
- **Why:** pages change without notice; a moving target makes metrics incomparable.
  Answers carry the snapshot date and a disclaimer to check wizzair.com.
- **Cost:** answers can be out of date. Incremental updates are deferred.
- **Detail:** the fee table is rendered by JavaScript. Its rendered text was saved once
  by hand (`fees-table.txt`), because the JSON API uses internal names
  ("baggage-max23" is shown as "max. 20 kg") that cannot be cited.

## 2. One source unit = one chunk (2026-11-09)

- **Choice:** a Help Centre accordion item, a bundle, a GCC clause with its sub-items,
  a definition, or a fee group is one chunk. The id comes from the source itself
  (`gcc-wah-2023-03-01#15.1.6`, `hc-cabin-baggage#accordion-free-carry-on-bag`),
  so eval labels survive a re-download.
- **Why:** citations point to a real place in the document; text stays verbatim.
- **Cost:** chunk sizes vary (84 to ~5,900 chars). A size cap is deferred until
  evals show it matters.
- **Detail:** table rows are kept on one line (`cell | cell | cell`), otherwise
  "Yes" / "No" cells lose their row. Call-to-action buttons are dropped.

## 3. Two kinds of source; on a conflict, show both (2026-11-11)

- **Sources:** Help Centre and fee pages (written for passengers) and the General
  Conditions of Carriage (GCC, the legal contract the passenger accepts when booking, PDF).
- **Choice:** keep both. When they disagree, the answer gives both values with their
  citations, says the sources differ, and advises checking with Wizz Air. Facts found
  only in the GCC (liability limits, claim deadlines, uncollected baggage) are answered
  from the GCC.
- **Why:** the GCC is binding, the Help Centre is what passengers actually read. Picking
  one would mean the assistant decides for the passenger: on the declared value the GCC
  is the more favourable one (approx. EUR 2,800 vs 2,500 EUR). The GCC states amounts in
  SDR (an IMF currency basket) with EUR approximations; answers quote both.
  Wizz Air itself does not apply GCC clauses 17.2.2, 17.2.5 and 18.2.9 to consumers.
- **Cost:** facts are often stated in two places, and some disagree. Conflicts found:
  - declared value limit: Help Centre 2,500 EUR vs GCC 2,224 SDR (approx. EUR 2,800);
  - excess weight: Help Centre 13 EUR/kg vs fee table 13–15 EUR/kg;
  - adding sports equipment: Help Centre "at booking or up to 3 hours before" vs
    GCC "at booking, through the Call Centre";
  - knives in cabin bags: 6 cm limit (general security list) vs a full ban
    (Wizz Air's own rule).
- **Consequence for answers:** the generation prompt states the conflict rule.
- **Consequence for evals:** conflict groups list the chunks of both sources, and the
  judge counts an answer as correct only if it names both values and says they differ.
  An answer that gives one value as the only truth is wrong. Where the sources agree,
  or only one has the fact, one source is enough.
- **History:** first decided as "the Help Centre wins"; replaced the same day, because
  the GCC is the binding contract.

## 4. Eval labels checked blind by an independent model (2026-11-11)

- **Choice:** one model drafted the groups, questions and labels. A separate agent
  with a fresh context saw only the chunks and the questions, without labels or
  reference answers, and picked the chunks and answers itself. A human resolves only
  the disagreements.
- **Result:** in 87 of 87 groups the label was among the verifier's chunks; in 83 it
  was the verifier's best chunk. Seven groups were fixed after review
  (`evals/blind-check-2026-11-11.json`).
- **Cost:** the verifier is from the same model family, so shared blind spots are
  possible. A different-vendor check is deferred.

## 5. Questions without an answer are generated, then attacked (2026-11-11)

- **Choice:** one agent wrote 15 baggage questions that sound answerable but that the
  chunks do not answer. A second agent saw only the questions and tried hard to answer
  them from the chunks. 11 stayed unanswered and became `no-answer` groups (expected
  answer: a refusal). 4 got a partial answer (the rule exists, the exact case is not
  covered) and became `tricky` groups whose reference answer gives the known part and
  says what the sources do not cover (`evals/no-answer-check-2026-11-11.json`).
- **Why:** the brief planned hand-written questions. Generating them is faster, and the
  blind attack is what keeps the label honest: a question only counts as unanswerable
  if a second model could not answer it either.
- **Cost:** synthetic questions are cleaner than real ones. Real passenger questions
  (FAQ now, logs later) stay in the set to offset that.

## 6. Level 1 pipeline: the Cookbook baseline, a cheap answer model (2026-11-11)

- **Choice:** Voyage AI embeddings (`voyage-4-large`) of headings + chunk text; an
  in-memory numpy matrix; top-3 chunks by cosine similarity; answers by Claude Haiku 5.5.
- **Why:** follows the Cookbook so later levels compare against a known baseline. The
  corpus is small (91 chunks, ~16k tokens), so a vector database would add nothing.
  A cheap answer model under a stronger judge shows how far a low-cost setup gets.
- **Answer format:** structured output, either `{kind: "answer", text, citations}` or
  `{kind: "refusal"}`. Evals count refusals from the field, not from the text. The
  refusal message and the disclaimer are fixed strings in code, not model output.
  Citations must be among the retrieved chunks, otherwise the run fails loudly.
- **Cost:** Haiku may miss nuance that a larger model would catch; the evals show it.

## 7. How the evals score retrieval and answers (2026-11-11)

- **Retrieval, as in the Cookbook:** precision, recall, MRR and F1 against the labelled
  chunks only (the primary chunk; both sources on a conflict group). F1 of the set is
  computed from mean precision and recall, like the Cookbook. A group passes when every
  wording found all its labelled chunks. Groups whose expected answer is a refusal are
  left out of retrieval metrics.
- **Secondary column `hit@3 any`:** share of questions with at least one chunk that holds
  the fact in the top 3, counting the alternatives the blind verifier found
  (`evals/blind-check-2026-11-11.json`). It shows how many "misses" found the same fact
  elsewhere. It is not the headline, because alternatives are often incomplete (only one
  page gives the 10 kg weight) and on a conflict group one source is not the full answer.
- **Answers:** refusals are graded in code from the reply's `kind` (a refusal where the
  sources answer is wrong; an answer where a refusal is expected is wrong). Every other
  reply goes to an LLM judge with the question, the reference answer and excerpts, with
  the conflict, partial and false-premise rules.
- **What the judge reads:** the chunks that hold the fact (labels and blind-check
  alternatives) plus the chunks the reply cites, the same in every mode. The answer must
  cite every chunk it relies on, so a true detail from a cited chunk is not graded as
  unsupported. All 91 chunks in every verdict would cost about $10 a run.
- **Why the judge sees excerpts at all:** without them, it graded correct replies as
  wrong using its own idea of Wizz Air rules ("wheels count in the size"), while the
  Help Centre says wheels may add up to 5 cm. The judge is told to use only the reference
  and the excerpts.
- **Judge and check from different families:** DeepSeek V4 Pro judges every reply, and
  Claude Sonnet 5.5 re-grades a random sample of 30 verdicts per file without seeing them;
  disagreements are reviewed by hand. So each answer model has a judge or a checker outside
  its own family: Pro may go easy on DeepSeek answers, and the Sonnet sample would show it.
  The judge is one model for the whole matrix, so the matrix compares answer models, not
  judges.
- **Cost:** the judge sees only part of the corpus, so it would accept an extra detail
  that is true in an excerpt but does not apply to the question.
- **Runs:** retrieval is deterministic and runs once; answers and verdicts run 3 times
  to show the spread.

## 8. Answer prompt: refusals, invented conflicts, sub-clause citations (2026-11-11)

- **Choice:** three rules in the answer prompt, no code or schema change. (1) Refuse when
  the excerpts do not answer the core of the question, and an "answer" that only says the
  excerpts do not cover it counts as a refusal; a partial answer stays for the case where
  the excerpts really state part of it. (2) A conflict means two excerpts giving different
  values or rules for the *same* thing; two rules about different things are not one.
  (3) Cite the id exactly as in the excerpt's `id` attribute, never a clause number from
  the text. The check that citations are among the retrieved chunks is unchanged.
- **Why:** a first prompt let the model answer "the excerpts don't say..." instead of
  refusing, call two unrelated clauses a conflict, and cite sub-clauses like `#18.2.7.2`.
- **Not fixed:** the prompt rule reduces sub-clause citations but does not remove them. A
  per-call enum of retrieved ids in the schema would.
- **Cost:** the refusal rule can be too strong where the sources answer only part of the
  question (`tricky`).

## 9. A whole-corpus mode: every chunk in the prompt, no retrieval (2026-11-11)

- **Choice:** `evaluate run <runs> full` sends all 91 chunks (~16k tokens) to the same
  answer prompt instead of the top 3. It answers one question: how much do the answers
  lose to retrieval? Retrieval metrics are not computed in this mode.
- **Why:** the corpus fits in a prompt, so the mode is a cheap ceiling for any retrieval
  improvement and an honest comparison for the README.
- **Cost:** it does not scale; it is a measuring tool, not a candidate pipeline.
  `evaluate regrade` re-judges saved replies without asking for new answers.

## 10. One protocol for every measurement, DeepSeek as a second provider (2026-11-11)

- **Protocol:** the answer prompt of decision 8; 3 runs per combination; the matrix
  {Haiku 5.5, DeepSeek V4.1 Flash} x {RAG top 3, whole corpus}; DeepSeek V4 Pro judges
  every reply; Sonnet 5.5 re-grades a sample of 30 verdicts per file (decision 7).
- **How DeepSeek is called:** its Anthropic-compatible API (`https://api.deepseek.com/anthropic`),
  with the same `anthropic` SDK and no new dependency. It ignores `output_config.format`,
  so there is no constrained decoding: the JSON schema goes into the system prompt and the
  reply is validated with the same Pydantic model. JSON that does not match counts as a
  pipeline error, so part of a DeepSeek error rate can be format, not knowledge. Thinking
  is left at each provider's default (on for both Haiku 5.5 and DeepSeek).
- **Judge retries:** an answer whose JSON does not match is an error, but a verdict has no
  error grade, and a judge failure after all answers would lose a paid run. So the judge
  is asked again, up to 3 times; only then does the run stop.
- **Cost:** DeepSeek Flash is $0.15-0.30 per 1M input tokens (off-peak / peak), $0.003-0.006
  on a cache hit, which the whole-corpus prompt mostly is. The judge is the main cost:
  Pro is $0.66-1.32 per 1M input and $1.98-3.96 per 1M output tokens. Actual judge cost:
  $0.5-1.3 per file of 3 runs.
- **Result (3 runs each, judge DeepSeek V4 Pro):** Haiku 5.5 85% with top 3 and 88% with
  the whole corpus; DeepSeek Flash 88% and 92%. The min-max ranges do not overlap. The
  whole-corpus gain is almost all on `tricky` (Haiku 67% -> 81%, Flash 73% -> 90%), where
  retrieval recall is 0.69: retrieval limits the answers there. On the 173 questions
  where all labelled chunks were in the top 3, both modes score the same; the gain comes
  from the 21 questions where some labelled chunk was missed (Haiku 44% -> 81%, Flash
  44% -> 89%). Flash had no malformed JSON in 1,260 replies.
- **Judge check:** Sonnet agreed with Pro on 110 of 120 sampled verdicts. A manual review of
  the 10 disagreements sided with Sonnet in 7; five of them were Pro marking a reply wrong
  for omitting a reference detail the question did not ask about. Pro is the stricter
  judge, for both answer models alike; it showed no leniency to DeepSeek answers.

## 11. Citations limited to the retrieved ids by the schema (2026-11-12)

- **Choice:** `rag.reply_schema(ids)` builds the reply schema for every call, with `citations`
  as a list of `Literal` of the ids of the chunks in that prompt. For Claude it is
  constrained decoding, so a sub-clause id like `#18.2.7.2` cannot be generated. DeepSeek has
  no constrained decoding: the enum goes into the JSON schema in the system prompt, and
  pydantic rejects a foreign id as a pipeline error, as before. The old check that
  citations are among the retrieved chunks is gone; only "an answer has citations" stays.
- **Why:** decision 8 reduced these citations with a prompt rule but did not remove them, and
  they were all of the pipeline errors (7 and 7 of 630 for Haiku, 0 and 5 for Flash).
- **Not changed:** the answer prompt. The schema is the only variable, so the effect is
  measurable on the same protocol.
- **Cost:** every call has its own schema, so Claude compiles a grammar per distinct set of
  ids. The smoke test (15 questions, top 3 and 91 ids) showed no visible delay (2.5-3.6 s per
  answer). Whether the change moves accuracy is not measured yet: it is part of the next
  matrix (decision 13).

## 12. Questions from other model families, labelled blind (2026-11-12)

- **Why:** the Claude-written questions could share Claude's wording, which would inflate
  the metrics. Gemini and GPT wrote questions from the two prompts in
  `evals/candidates/prompts.md`, and the reports now split every number by who wrote
  the questions (`source`). Versions are as the project owner named them ("Gemini Flash 3.6",
  "GPT-6"); the exact ids are to be added to the results once known.
- **Sets:** 30 passenger questions and 30 difficult questions from each, 120 in all. Embedding
  similarity against the 210 existing questions and between the new ones found five
  near-identical pairs (0.84-0.90); they were dropped by hand, 115 remain. Pairs that state
  the same fact in other words were kept, because they are extra wordings, not duplicates.
- **Labels:** three independent Claude Code subagents, one per third of the shuffled questions,
  saw only the 91 chunks and neutral ids (no source, no type), and for each question gave a
  verdict (answerable, partial, unanswerable, off-topic), the chunks, a reference answer
  and whether the premise is false. A fourth agent then tried to answer the 34
  partial/unanswerable questions completely and had to quote a sentence from a chunk; the
  quotes were checked by string search. Reading each, three of its five full answers were
  accepted (the 21-day loss rule, the fragile-items exclusion, the instrument fee), two stayed
  partial. The subagents run on the Claude Code subscription, not the API.
- **Result:** 72 answerable, 30 partial, 12 off-topic, 1 unanswerable; 15 false premises,
  7 questions where the sources differ. `evals/questions-external.json` holds them as groups
  (`evals/blind-check-2026-11-12.json` the alternative chunks). Labels follow the convention
  of decision 7: the primary chunk, and on a conflict the best chunk of the other source.
- **Kinds:** answerable passenger questions are `faq`, everything else is `tricky` (partial,
  false premise, off-topic with an expected refusal), the one unanswerable question is
  `no-answer`. `faq` here means "a model wrote it as a passenger"; use `source` to separate
  them from the 19 real-style FAQ questions.
- **Cost:** the verifiers are the same model family as the author of the first set, so shared
  blind spots are possible (as in decision 4). The ban on reading the repository is in
  their prompt, not enforced. Only one question is `no-answer`: the corpus (61 GCC chunks)
  answers almost everything at least in part, so refusals can be judged on 13 questions
  (12 off-topic and 1) from this set.

## 13. Run protocol, cost plan and the retrieval experiment (2026-11-12)

- **Code before runs (no cost):** answers are saved before judging, so a judge failure
  loses nothing (`evaluate judge <file>` judges what is missing); DeepSeek 429 answers
  are retried with a growing wait, the number of workers stays 8; every answer records its
  tokens and seconds; `run` takes `k=N` (chunks retrieved), `sample=N` (a fixed smoke
  sample) and reads `questions-external.json`; the report adds a table by source.
- **One matrix on all 325 questions:** {Haiku 5.5, DeepSeek Flash} x {top 3, whole corpus}
  x 3 runs, judge DeepSeek V4 Pro, Sonnet 5.5 checks 30 verdicts per file. One run both
  measures decision 11 and compares Claude, Gemini and GPT wording. It replaces the
  results of decision 10 as the baseline (those cover 210 questions; the report's "claude"
  row is comparable with them).
- **Measured, from a smoke test of 15 questions:** a Haiku answer with 3 chunks takes about
  2.6k input and 0.5k output tokens, a DeepSeek judge verdict a few thousand; judging cost
  was measured before at $0.6-1.2 per file of 630 verdicts.
- **Estimated cost of the matrix (325 questions x 3 runs = 975 answers per file):** Haiku
  answers about $0.5 with top 3 and about $2 with the whole corpus (17k tokens in, price
  $0.10 / $0.50 per 1M); Flash answers a few tenths of a dollar (its output price is not
  recorded here); judging about $1-2 per file; Sonnet checks about $0.5 in all. In all about
  $7-11, of which DeepSeek is about $4-8. DeepSeek balance before: $10.01.
- **The retrieval experiment (A/B/C):** A = top 3 (the matrix above), B = top 10 straight to
  the model, C = top 10, reranker, top 3, then the model. C gives the model as many chunks
  as A, so A against C shows what the reranker adds; B against A shows what more chunks
  add. The whole corpus is the ceiling. The reranker enters the pipeline only if C is clearly
  better than A and B.
- **Order, to avoid paid runs that decide nothing:** first retrieval only (recall@3, @5, @10
  and MRR, before and after reranking; costs cents, no answer model, no judge). If recall@10
  is not above recall@3 on the `tricky` questions, a reranker has nothing to reorder and the
  experiment stops. Otherwise B and C run on DeepSeek Flash only (about $2.5-4.5 for both,
  judge included); Haiku joins only if Flash shows a gain (about $2.5-4.5 more).
- **Rules for every paid run:** a smoke test on 15 questions first; no re-run to look at a
  number again (`report` and `regrade` read saved files); the run's date, models and `k`
  are in the file name and the file.

## 14. Matrix results, and the reranker stays out (2026-11-12)

- **Result:** on 325 questions, top 3 gives 76% for Haiku and Flash; the whole corpus 82%
  and 86%; Flash with 10 chunks (B) 85%; Flash with a reranker, 10 -> 3 (C), 79%. Tables
  and the Sonnet check (198/210 agreement with Haiku B) are in the README.
- **Decision:** the reranker is not added. By the rule of decision 13, C must be clearly
  better than A and B; it is better than A by 3 points (ranges nearly touch) and worse
  than B by 6. It lifts recall@3 (0.86 -> 0.92) but not enough answers.
- **Haiku on B:** 82% (82-83%), against 76% on top 3 and 82% on the whole corpus; no
  pipeline errors. Both models gain from 10 chunks (+6 Haiku, +9 Flash), so 10 chunks are
  the better default. Sonnet agreed with Pro on 27/30 verdicts of this file.
- **Open:** Flash's 15 errors in the whole-corpus run are all format failures of an
  unconstrained output (broken JSON, a missing `reply` wrapper, a citation outside the ids).
- **Cost:** DeepSeek credit used: about $8.3 up to C, about $2.2 more for Haiku B.


## 15. The default stays at 3 chunks; the reranker stays out for now (2026-11-12)

- **Decision:** `TOP_K` stays 3. Ten chunks measured better (Flash +9 points, Haiku +6), but they
  double the input of every answer (about 5.2k tokens against 2.6k for Haiku), and every later
  eval run pays for it in judge time and money. The README keeps A and B side by side so the
  trade-off stays visible.
- **Reranker:** measured on Flash only (C: +3 points over A, inside the noise; B is 6 points
  better than C). It was not run on Haiku, to save the judge cost. It comes back for review
  when the corpus grows (other topics or carriers: cosine top 10 then loses recall) or when a
  Haiku C run is affordable. Until then the code stays (`rag.rerank`), the pipeline does not use it.
- **Known and not fixed:** with 10 chunks Haiku sometimes writes "the sources do not say" with
  `kind: answer` instead of `refusal` (4 of 36 no-answer runs, two questions); the grader counts
  it as wrong. A prompt change would need a new paid run.

## 16. Level 2: summary indexing, measured on retrieval only (2026-11-12)

- **What:** every chunk gets a 2-3 sentence summary, written once by Claude Sonnet 5.5 in a chat
  session (no API call), from the chunk text alone and not from the eval file, saved in
  `data/chunks/<snapshot>/summaries.jsonl` and then frozen. A few eval questions had been shown
  in that session earlier; a leak could only inflate the result, and the result is negative. Chunk text stays verbatim in answers; the summary only enters the text that is embedded.
- **Variants:** S1 = heading + summary + text (primary); S2 = heading + summary (exploratory, not
  used for the decision).
- **How it is measured:** `evaluate retrieval` only: recall@3/5/10 and MRR on the same 296
  questions, no answer model, no judge, cents. The existing rows (cosine, reranked) sit next to S1 and S2.
- **Criteria, set before the first run:** S1 counts as a gain if recall@3 on all questions is at
  least 0.92 (cosine is 0.86, the reranker 0.92) **or** recall@3 on `tricky` is at least 0.84
  (cosine 0.71, reranker 0.84), and `faq` recall@3 does not fall more than 0.03 below cosine.
  A difference under 0.03 is noise: the summaries are one sample from one model.
- **If it is a gain:** one answer run of Haiku on top 3 (about $2-3, mostly the judge), after
  checking the DeepSeek balance. **If not:** it is written down as measured, and no answer run is made.
- **Result (retrieval only, 296 questions, 91 summaries, 2026-11-12):** S1 gives recall@3 0.87
  (cosine 0.86, reranker 0.92), `tricky` 0.75 (0.71 and 0.84), `faq` 0.89 (0.88); MRR 0.76, the
  same as cosine. S2 is no better (0.86, 0.74). By the criteria above this is **not a gain**: all
  is below 0.92, `tricky` is below 0.84, and the differences from cosine are 0.01-0.04, within or
  near the noise of one summary sample. No answer run is made.
- **Reading:** on 91 chunks with headings already in the embedded text, a summary adds little;
  the misses are mostly a GCC clause beating the Help Centre page, which a summary of each does
  not change. The summaries stay in `data/` (not published); `index summary` and the extra rows
  of `evaluate retrieval` stay for a bigger corpus.

## 17. The 12 judge disagreements, reviewed by hand (2026-11-12)

- **What:** the 12 verdicts where Sonnet 5.5 disagreed with DeepSeek Pro in the matrix files
  (Haiku and Flash, A, B, C, whole corpus), read against the reference answer and the chunks.
  The reviewer was Claude Sonnet 5.5 in a chat session, so it is the same family as the checker:
  the four borderline cases below are worth a second human look.
- **Verdicts:** Sonnet right in 7 (sports timing question, high-value declaration, cat in the
  cabin, two 10 kg bags, 2-year-old with stroller, 45 cm backpack, duty-free bag), Pro right in 4
  (trolley at 12 kg, baby with stroller and instrument, delayed bag considered lost, power bank),
  one open (a sports equipment "limits" question). Borderline: duty-free bag, trolley at 12 kg,
  stroller and instrument, sports equipment limits.
- **Direction:** Pro marked 6 correct replies wrong and 1 wrong reply right, so the absolute
  accuracy is about 3 points low on this sample. Each judge was strict in 6 of the 12, so
  "Pro is the stricter judge" (decision 10) does not hold for this matrix. Because the judge is
  the same for every answer model, comparisons between A, B, C and the whole corpus stand.
- **Findings about the grading itself:**
  1. Two causes, not one. (a) Three of the 12 come from groups that hold two facts under one
     reference (`sports-equipment-limits`: limits and when to add; `lost-21-days`: when a bag
     counts as lost and which documents to send): a wording about one fact is marked down for
     omitting the other. (b) In most of the rest the reference mixes key facts with details
     (the 10 kg limit, an airport fee amount, an extra personal item, "one form per bag"), and
     the two judges disagree about which are key. Six of the 12 are single-question groups, so a
     reference per question would not have fixed them; splitting groups and separating key
     facts from details would.
  2. The conflict rule of decision 3 ("name both values and say the sources differ") is applied to
     every wording of a conflict group, also to a question about limits, where the difference
     (when to add the equipment) is not relevant.
  3. Pro called a true claim "unsupported" when it came from a chunk the judge was not shown
     (fees apply to each checked bag): the chunk was retrieved, but neither labelled nor cited,
     and the judge sees only those two kinds. Checked in the saved results file.
- **Not done:** no re-grading and no change to the question file; both would cost judge runs.

## 18. Reporting the retrieval result as a quality-vs-cost trade-off (2026-11-17)

- **What changed in the wording:** the README, the eval explorer (`web/`) and this log now say
  that the reranker works and is cheap but did not add enough quality on this corpus, and that
  10 chunks buy more quality at twice the input per answer: a choice between quality (B) and
  cost (A, C), not "the reranker does not work". The finding about other models' questions now
  compares the same kind of question across sources instead of whole sources. The README gets
  a "Quality vs cost" table (mean tokens per answer from the `tokens` field of the saved files).
- **Why:**
  1. The argument "it adds a second API call" was weak: the reranker call is small and cheap,
     and C gives the answer model the same 3 chunks as A, so the answer costs the same. What
     remains against it is latency, one more moving part and a gain below the bar of decision 13.
  2. The comparison by source mixed question types: Claude's 191 questions are mostly `fact`
     (159), Gemini's and GPT's are mostly `faq` and `tricky`. Whole-source accuracy then
     measures the mix of kinds as much as the author.
  3. The 19 `faq` groups of `evals/questions.json` were taken from the Wizz Air FAQ but carried
     `source: claude`. They now carry `source: wizzair-faq`. The saved results files are not
     changed: reports take the source from the question files by group id
     (`evaluate.source_by_group`), so old files are counted the new way.
- **Result, `faq` against `faq` (top 3, Haiku A / Haiku B, n = questions, 3 runs each):**
  Wizz Air FAQ 93% / 89% (n=19, recall@3 0.94); Gemini 76% / 75% (n=21, 0.83); GPT 44% / 62%
  (n=22, 0.86). Claude's `fact` questions: 88% / 89% (n=159; recall@3 0.99, 0.88 and 0.92 for
  the formal, search-style and situation wordings). On Flash, `faq` from GPT: A 44%, B 59%,
  C 52%; from Gemini: A 73%, B 87%, C 70%. Recall@3 is similar across sources, so retrieval
  does not explain the gap. Haiku A, GPT's `faq` questions: 28 of 37 wrong replies omit a key
  fact (keyword heuristic: the judge's reason has "omit", "miss", "incomplete" or "does not
  mention"); the rest are "not covered" replies, a missed false premise or a refusal.
- **Limits:** 19-22 questions per source and kind, so a few points are noise. The incompleteness
  count is a keyword heuristic, not a reading of every reason (adding "fails to" gives 34 of 37,
  but some of those are false "not covered" replies, not missed facts). The reference answer is
  per group (decision 17), which penalises omitted details, so absolute numbers for
  multi-part questions are low.
- **Correction to decision 13:** the whole-corpus prompt measured 31.4k input tokens for Haiku,
  not about 17k, so the estimated cost of a Haiku whole-corpus file is about $3.3, not $2.
- **Not changed:** decisions 14 and 15 stand: the reranker stays out and `TOP_K` stays 3. No
  new runs, no API calls; every number comes from the saved files of 2026-11-12.
