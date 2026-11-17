"use client";

import { useState } from "react";
import type { Chunk, Question, Run } from "@/lib/data";
import { OUTCOME_LABEL, outcomeOf, type ConfigOption, type Outcome } from "@/lib/labels";
import { ConfigPicker } from "./ConfigPicker";
import { Pill } from "./Pill";
import { OUTCOME_MARK, Runs } from "./Runs";

export type Setup = ConfigOption & { judge: string; checkModel: string };

const OUTCOME_INK: Record<Outcome, string> = { correct: "text-correct-ink", wrong: "text-wrong-ink", error: "text-error-ink" };

// Whole pixels: the bar's fill is rounded to the track width, not a percentage of it.
const BAR_PX = 160;

function ChunkLink({ id, chunks }: { id: string; chunks: Record<string, Chunk> }) {
  return <a href={chunks[id].url}>{chunks[id].title}</a>;
}

function Answer({ run, n, setup, chunks }: { run: Run; n: number; setup: Setup; chunks: Record<string, Chunk> }) {
  const outcome = outcomeOf(run);
  return (
    <article className="card p-6">
      <header className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">Answer {n}</h3>
        <p className={`inline-flex items-center gap-2 text-sm font-semibold ${OUTCOME_INK[outcome]}`}>
          <span aria-hidden className={`size-2 rounded-xs ${OUTCOME_MARK[outcome]}`} />
          {OUTCOME_LABEL[outcome]}
        </p>
      </header>
      {run.kind === "answer" && (
        <>
          <p className="mt-3 whitespace-pre-wrap">{run.text}</p>
          <p className="mt-3 text-sm text-muted">
            Cites:{" "}
            {run.citations.map((id, i) => (
              <span key={id}>
                {i > 0 && "; "}
                <ChunkLink id={id} chunks={chunks} />
              </span>
            ))}
          </p>
        </>
      )}
      {run.kind === "refusal" && <p className="mt-3">Refused: the assistant found nothing about this in its sources.</p>}
      {run.kind === "error" && <p className="mt-3 text-muted">The pipeline failed: {run.message}</p>}
      <p className="mt-4 border-t border-line pt-4 text-sm">
        <span className="text-muted">{run.by === "code" ? "Graded by a rule in code: " : `${setup.judge}: `}</span>
        {run.reason}
      </p>
      {run.check && (
        <p className="mt-2 text-sm">
          <span className="text-muted">
            {setup.checkModel} re-graded it and {run.check.correct === run.correct ? "agrees" : "disagrees"}:{" "}
          </span>
          {run.check.reason}
        </p>
      )}
    </article>
  );
}

export function QuestionDetail({ question: q, setups, chunks, initial }: { question: Question; setups: Setup[]; chunks: Record<string, Chunk>; initial: string }) {
  const [id, setId] = useState(initial);
  const setup = setups.find((s) => s.id === id)!;
  const { retrieved, runs } = q.configs[id];
  const cited = new Set(runs.flatMap((r) => (r.kind === "answer" ? r.citations : [])));

  return (
    <div className="grid gap-8 md:grid-cols-[--spacing(64)_1fr]">
      <ConfigPicker
        options={setups}
        value={id}
        onChange={setId}
        legend="Compare the setups"
        right={(o) => <Runs outcomes={q.configs[o.id].runs.map(outcomeOf)} />}
      />
      <div className="flex min-w-0 flex-col gap-12">
        <section aria-labelledby="search">
          <h2 id="search" className="text-xl font-semibold">What the search found</h2>
          {retrieved.length ? (
            <>
              <p className="mt-1 text-sm text-muted">Chunks in the order the search ranked them, with their cosine similarity to the question.</p>
              <ol className="card mt-4 divide-y divide-line">
                {retrieved.map(([cid, score], i) => (
                  <li key={cid} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 text-sm">
                    <span className="w-6 font-mono text-muted">{i + 1}</span>
                    <span className="flex min-w-0 flex-1 basis-60 flex-wrap items-center gap-2">
                      <ChunkLink id={cid} chunks={chunks} />
                      {q.expected.includes(cid) && <Pill tone="correct">holds the answer</Pill>}
                      {cited.has(cid) && <Pill>cited</Pill>}
                    </span>
                    <span className="flex items-center gap-3">
                      <span aria-hidden className="h-1 overflow-hidden rounded-full bg-surface-muted" style={{ width: BAR_PX }}>
                        <span className="block h-full bg-accent" style={{ width: Math.round(score * BAR_PX) }} />
                      </span>
                      <span className="font-mono">{score.toFixed(3)}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </>
          ) : (
            <p className="card mt-4 px-4 py-3 text-sm text-muted">No search in this setup: all 91 chunks were in the prompt.</p>
          )}
        </section>
        <section aria-labelledby="answers">
          <h2 id="answers" className="text-xl font-semibold">
            Three answers from {setup.model}
          </h2>
          <div className="mt-4 flex flex-col gap-4">
            {runs.map((run, i) => (
              <Answer key={i} run={run} n={i + 1} setup={setup} chunks={chunks} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
