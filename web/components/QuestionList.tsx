"use client";

import Link from "next/link";
import { useState } from "react";
import { KINDS, KIND_LABEL, SOURCES, SOURCE_LABEL, TOPIC_LABEL, correctCount, type ConfigOption, type QuestionRow } from "@/lib/labels";
import { Pill } from "./Pill";
import { Legend, Runs } from "./Runs";

const RESULTS = { all: "Any result", "3": "All 3 correct", mixed: "Mixed", "0": "None correct" } as const;
type Result = keyof typeof RESULTS;

const matches = (correct: number, result: Result) =>
  result === "all" || (result === "3" ? correct === 3 : result === "0" ? correct === 0 : correct === 1 || correct === 2);

const FIELD = "flex flex-col gap-1 text-sm text-muted";
const CONTROL = "h-11 rounded-md border border-line-strong bg-surface px-3 text-ink";

function Select<T extends string>({ label, value, onChange, options }: { label: string; value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <label className={FIELD}>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value as T)} className={CONTROL}>
        {options.map(([v, text]) => (
          <option key={v} value={v}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

export function QuestionList({ rows, options, initial }: { rows: QuestionRow[]; options: ConfigOption[]; initial: string }) {
  const [config, setConfig] = useState(initial);
  const [kind, setKind] = useState<string>("all");
  const [topic, setTopic] = useState<string>("all");
  const [source, setSource] = useState<string>("all");
  const [result, setResult] = useState<Result>("all");
  const [text, setText] = useState("");

  const topics = [...new Set(rows.map((r) => r.topic))].sort();
  const needle = text.trim().toLowerCase();
  const shown = rows.filter(
    (r) =>
      (kind === "all" || r.kind === kind) &&
      (topic === "all" || r.topic === topic) &&
      (source === "all" || r.source === source) &&
      matches(correctCount(r.outcomes[config]), result) &&
      r.question.toLowerCase().includes(needle),
  );

  return (
    <>
      <form role="search" aria-label="Filter questions" onSubmit={(e) => e.preventDefault()} className="card grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 lg:grid-cols-6">
        <Select label="Setup" value={config} onChange={setConfig} options={options.map((o) => [o.id, `${o.model}, ${o.retrieval}`])} />
        <Select label="Result" value={result} onChange={setResult} options={Object.entries(RESULTS) as [Result, string][]} />
        <Select label="Kind" value={kind} onChange={setKind} options={[["all", "All kinds"], ...KINDS.map((k): [string, string] => [k, KIND_LABEL[k]])]} />
        <Select label="Topic" value={topic} onChange={setTopic} options={[["all", "All topics"], ...topics.map((t): [string, string] => [t, TOPIC_LABEL[t]])]} />
        <Select label="Source" value={source} onChange={setSource} options={[["all", "Anyone"], ...SOURCES.map((s): [string, string] => [s, SOURCE_LABEL[s]])]} />
        <label className={FIELD}>
          Search
          <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Words in the question" className={CONTROL} />
        </label>
      </form>
      <div className="mt-6 mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted" aria-live="polite">
          <span className="font-mono text-ink">{shown.length}</span> of {rows.length} questions
        </p>
        <Legend />
      </div>
      {shown.length ? (
        <ul className="card divide-y divide-line overflow-hidden">
          {shown.map((r) => (
            <li key={r.id}>
              <Link href={`/q/${r.id}`} className="flex min-h-16 flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 text-ink hover:bg-surface-muted hover:text-ink">
                <Runs outcomes={r.outcomes[config]} size="lg" />
                <span className="sr-only">{correctCount(r.outcomes[config])} of 3 correct:</span>
                <span className="min-w-0 flex-1 basis-80">{r.question}</span>
                <span className="flex gap-2">
                  <Pill>{KIND_LABEL[r.kind]}</Pill>
                  <Pill>{TOPIC_LABEL[r.topic]}</Pill>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="card px-4 py-6 text-muted">No question matches these filters. Clear the search or set a filter back to all.</p>
      )}
    </>
  );
}
