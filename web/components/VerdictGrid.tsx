"use client";

import Link from "next/link";
import { useState } from "react";
import { KINDS, KIND_ABOUT, KIND_LABEL, correctCount, pct, type ConfigOption, type QuestionRow } from "@/lib/labels";
import { Legend, Runs } from "./Runs";
import { ConfigPicker } from "./ConfigPicker";

/** Every question as a column of its 3 graded answers, in a fixed order, so switching the
 *  setup shows which answers turn green or red. */
export function VerdictGrid({ rows, options, initial }: { rows: QuestionRow[]; options: ConfigOption[]; initial: string }) {
  const [config, setConfig] = useState(initial);
  const [pointed, setPointed] = useState<QuestionRow | null>(null);
  const current = options.find((o) => o.id === config)!;

  return (
    <div className="card grid gap-8 p-6 md:grid-cols-[--spacing(64)_1fr]">
      <ConfigPicker
        options={options}
        value={config}
        onChange={setConfig}
        legend="Show the answers of"
        right={(o) => <span className="font-mono font-medium">{pct(o.accuracy)}</span>}
      />
      <div className="flex min-w-0 flex-col gap-8">
        {/* 325 links are 325 Tab stops: let keyboard users jump past them. */}
        <a href="#grid-end" className="sr-only focus:not-sr-only focus:self-start focus:rounded-md focus:bg-accent-soft focus:px-3 focus:py-2 focus:text-sm">
          Skip the {rows.length} questions
        </a>
        {KINDS.map((kind) => {
          const kindRows = rows.filter((r) => r.kind === kind);
          return (
            <section key={kind}>
              <div className="flex items-baseline justify-between gap-4">
                <h3 className="font-semibold">
                  {KIND_LABEL[kind]} <span className="text-sm font-normal text-muted">{kindRows.length} questions</span>
                </h3>
                <p className="font-mono text-2xl font-medium">{pct(current.byKind[kind])}</p>
              </div>
              <p className="mt-1 text-sm text-muted">{KIND_ABOUT[kind]}</p>
              <div className="mt-3 flex flex-wrap gap-0.5">
                {kindRows.map((r) => (
                  <Link
                    key={r.id}
                    href={`/q/${r.id}`}
                    aria-label={`${r.question} (${correctCount(r.outcomes[config])} of 3 correct)`}
                    onMouseEnter={() => setPointed(r)}
                    onFocus={() => setPointed(r)}
                    className="rounded-sm p-0.5 hover:bg-accent-soft"
                  >
                    <Runs outcomes={r.outcomes[config]} vertical />
                  </Link>
                ))}
              </div>
            </section>
          );
        })}
        <div id="grid-end" className="flex flex-col gap-3">
          <Legend />
          {/* Visual only, no aria-live: each link's aria-label already reads the question. */}
          <p className="min-h-12 rounded-md bg-surface-muted px-4 py-3 text-sm">
            {pointed ? (
              <>
                {pointed.question}{" "}
                <span className="text-muted">{correctCount(pointed.outcomes[config])} of 3 correct. Click to see the answers.</span>
              </>
            ) : (
              <span className="text-muted">Point at a column to read its question; click it to see the answers and the judge&apos;s reasons.</span>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
