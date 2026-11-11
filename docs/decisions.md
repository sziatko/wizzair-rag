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
  in-memory numpy matrix; top-3 chunks by cosine similarity; answers by Claude Haiku 5.5;
  Claude Opus 5.5 as the judge (A5).
- **Why:** follows the Cookbook so later levels compare against a known baseline. The
  corpus is small (91 chunks, ~16k tokens), so a vector database would add nothing.
  A cheap answer model under a strong judge shows how far a low-cost setup gets.
- **Answer format:** structured output, either `{kind: "answer", text, citations}` or
  `{kind: "refusal"}`. Evals count refusals from the field, not from the text. The
  refusal message and the disclaimer are fixed strings in code, not model output.
  Citations must be among the retrieved chunks, otherwise the run fails loudly.
- **Cost:** Haiku may miss nuance that a larger model would catch; the evals will show it.

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
  reply goes to the Claude Opus 5.5 judge with the question, the reference answer and the
  excerpts the answer model saw, with the conflict, partial and false-premise rules.
- **Why the judge sees the excerpts:** without them, the judge graded correct replies as
  wrong using its own idea of Wizz Air rules ("wheels count in the size"), while the
  Help Centre says wheels may add up to 5 cm. The judge is told to use only the reference
  and the excerpts.
- **Cost:** the judge checks extra details against the excerpts, not against the full
  corpus, so it would accept an extra detail that is true in a retrieved excerpt but does
  not apply to the question. The judge is checked against a second model (Claude Sonnet
  5.5) on a random sample; disagreements are reviewed by hand.
- **Runs:** retrieval is deterministic and runs once; answers and verdicts run 3 times
  to show the spread.
- **Change, same day: Sonnet judges, Opus checks.** The first full run with the Opus
  judge cost about $7.40 for 3 runs, almost all of it input tokens. Sonnet 5.5 agreed
  with it on 29 of 30 sampled verdicts (in the one disagreement Opus was right), so
  later runs use Sonnet 5.5 as the judge (half the price) and Opus 5.5 re-grades a
  sample of 30. The baseline in `evals/results/2026-11-11T1824.json` stays judged by
  Opus. Cost: a weaker judge on the full set, with a sample of 30 to show if it drifts.

## 8. Prompt fixes for refusals, invented conflicts and sub-clause citations (2026-11-11)

- **Choice:** three edits to the answer prompt, no code or schema change. (1) Refuse when
  the excerpts do not answer the core of the question, and an "answer" that only says the
  excerpts do not cover it counts as a refusal; a partial answer stays for the case where
  the excerpts really state part of it. (2) A conflict means two excerpts giving different
  values or rules for the *same* thing; two rules about different things are not one.
  (3) Cite the id exactly as in the excerpt's `id` attribute, never a clause number from
  the text. The check that citations are among the retrieved chunks is unchanged.
- **Result (1 run, judge Sonnet 5.5, vs the 3-run Opus baseline):** answer accuracy
  82% -> 89%; no-answer 45% -> 91%; fact 84% -> 90%; tricky 76% -> 71%; pipeline errors
  3 of 630 -> 1 of 210. Opus re-graded 30 verdicts and agreed on 26 (87%); all 4
  disagreements were Sonnet saying "correct" and Opus "incorrect", so Sonnet is the more
  lenient judge and part of the gain may be the judge, not the prompt.
- **Not fixed:** one reply still cited a sub-clause id (`#18.2.7.2`), so the prompt rule
  reduces but does not remove it. A per-call enum of retrieved ids in the schema would.
- **Got worse:** two `tricky` groups where the sources answer only part of the question
  (`tricky-basic-fare-10kg`, `tricky-infant-turns-two`): the reply now gives only
  "the excerpts don't say" or misses the known part. Single run, so noisy; the refusal
  rule is probably a bit too strong there.
- **Cost:** one run is noisy at group level (3 questions per group), so group changes of
  one question are not evidence. Re-run with 3 runs before relying on them.
