// Build-time data: web/data/*.json written by `python -m wizzair_rag.export_site`.
// Parsed here once (the file is the boundary); everything else trusts these types.
// Strict objects: a key renamed on the Python side fails the build instead of vanishing.
// Server only: it reads files. Client components import types and lib/labels.ts.
import { readFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { KINDS, SOURCES, TOPIC_LABEL, outcomeOf, type ConfigOption, type Kind, type QuestionRow } from "./labels";

const share = z.number();
const accuracy = z
  .object({
    questions: z.number(),
    accuracy: share,
    min: share,
    max: share,
    refused: share,
    errors: z.number(),
  })
  .strict();
const withRecall = accuracy.extend({ recall: share.nullable() }).strict();
const retrievalMetrics = z
  .object({
    questions: z.number(),
    precision: share,
    recall: share,
    f1: share,
    mrr: share,
    hit_any: share,
    groups_passed: z.number(),
    groups: z.number(),
  })
  .strict();

const Config = z
  .object({
    id: z.string(),
    model: z.string(),
    retrieval: z.string(),
    top_k: z.union([z.number(), z.literal("all")]),
    rerank: z.boolean(),
    date: z.string(),
    snapshot: z.string(),
    judge: z.string(),
    check: z.object({ model: z.string(), sampled: z.number(), agreed: z.number() }).strict(),
    metrics: z
      .object({
        retrieval: z.record(retrievalMetrics),
        by_kind: z.record(accuracy),
        by_source: z.record(withRecall),
        by_source_kind: z.record(z.record(withRecall)),
        calls: z.object({ calls: z.number(), seconds: z.number(), in: z.number(), cached: z.number(), out: z.number(), uncounted: z.number() }).strict(),
      })
      .strict(),
  })
  .strict();

const verdict = { correct: z.boolean(), reason: z.string(), by: z.string() };
// Optional on purpose: only the runs in the second judge's sample have one.
const check = z.object({ correct: z.boolean(), reason: z.string() }).strict().optional();
const Run = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("answer"), text: z.string(), citations: z.array(z.string()), ...verdict, check }).strict(),
  z.object({ kind: z.literal("refusal"), ...verdict, check }).strict(),
  z.object({ kind: z.literal("error"), message: z.string(), ...verdict, check }).strict(),
]);

const Question = z
  .object({
    id: z.string(),
    group: z.string(),
    question: z.string(),
    kind: z.enum(KINDS),
    topic: z.string().refine((t) => t in TOPIC_LABEL, (t) => ({ message: `topic ${t} has no label in lib/labels.ts` })),
    source: z.enum(SOURCES),
    reference: z.string(),
    expected: z.array(z.string()),
    configs: z.record(
      z
        .object({
          retrieved: z.array(z.tuple([z.string(), z.number()])),
          runs: z.array(Run).length(3),
        })
        .strict(),
    ),
  })
  .strict();

const Chunk = z.object({ title: z.string(), url: z.string().url() }).strict();

export type Config = z.infer<typeof Config>;
export type Run = z.infer<typeof Run>;
export type Question = z.infer<typeof Question>;
export type Chunk = z.infer<typeof Chunk>;

const read = (name: string) => JSON.parse(readFileSync(path.join(process.cwd(), "data", `${name}.json`), "utf-8"));

// Order of the README table: per model, top 3, top 10, reranked, whole corpus.
const retrievalRank = (c: Config) => (c.top_k === "all" ? 3 : c.rerank ? 2 : c.top_k === 10 ? 1 : 0);

export const configs: Config[] = z
  .array(Config)
  .parse(read("configs"))
  .sort((a, b) => a.model.localeCompare(b.model) || retrievalRank(a) - retrievalRank(b));
export const questions: Question[] = z.array(Question).parse(read("questions"));
export const chunks: Record<string, Chunk> = z.record(Chunk).parse(read("chunks"));

// The three files point at each other by id; a dangling id would crash a page mid-build.
const dangling = [
  ...questions.flatMap((q) => {
    const ids = [
      ...q.expected,
      ...Object.values(q.configs).flatMap((c) => [...c.retrieved.map(([id]) => id), ...c.runs.flatMap((r) => (r.kind === "answer" ? r.citations : []))]),
    ];
    return ids.filter((id) => !(id in chunks)).map((id) => `${q.id}: chunk ${id}`);
  }),
  ...questions.flatMap((q) => {
    const have = Object.keys(q.configs).sort().join();
    const want = configs.map((c) => c.id).sort().join();
    return have === want ? [] : [`${q.id}: configs [${have}], expected [${want}]`];
  }),
];
if (dangling.length) throw new Error(`web/data ids that point nowhere:\n${dangling.slice(0, 20).join("\n")}`);

/** Shown once for the whole site, so every config must agree on it (export_site.py checks too). */
export const meta = (() => {
  // The day of the runs too: the findings are dated by it, as one test series.
  const shared = new Set(configs.map((c) => `${c.snapshot}|${c.judge}|${c.check.model}|${c.date.slice(0, 10)}`));
  if (shared.size !== 1) throw new Error(`configs differ in snapshot, judge, check model or run day: ${[...shared].join("; ")}`);
  const [c] = configs;
  return { snapshot: c.snapshot, judge: c.judge, checkModel: c.check.model, runDay: c.date.slice(0, 10) };
})();

/** The shipped pipeline (rag.py): Haiku, top 3. */
export const DEFAULT_CONFIG = "claude-haiku-5-5";

export const configById = (id: string): Config => {
  const c = configs.find((x) => x.id === id);
  if (!c) throw new Error(`no config ${id} in web/data/configs.json`);
  return c;
};

export const configOptions: ConfigOption[] = configs.map((c) => ({
  id: c.id,
  model: c.model,
  retrieval: c.retrieval,
  accuracy: c.metrics.by_kind.all.accuracy,
  byKind: Object.fromEntries(KINDS.map((k) => [k, c.metrics.by_kind[k].accuracy])) as Record<Kind, number>,
}));

/** What the grid and the list need: no answer texts, so client bundles stay small. */
export const rows: QuestionRow[] = questions.map((q) => ({
  id: q.id,
  question: q.question,
  kind: q.kind,
  topic: q.topic,
  source: q.source,
  outcomes: Object.fromEntries(Object.entries(q.configs).map(([id, c]) => [id, c.runs.map(outcomeOf)])),
}));

export const REPO_URL = z
  .string({ required_error: "Set NEXT_PUBLIC_REPO_URL (web/.env.local locally, project settings on Vercel)" })
  .url()
  .parse(process.env.NEXT_PUBLIC_REPO_URL);
