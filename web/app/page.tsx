import { Pill } from "@/components/Pill";
import { VerdictGrid } from "@/components/VerdictGrid";
import { DEFAULT_CONFIG, REPO_URL, configById, configOptions, configs, meta, questions, rows } from "@/lib/data";
import { pct, type Kind, type Source } from "@/lib/labels";

const acc = (id: string) => pct(configById(id).metrics.by_kind.all.accuracy);
const recall = (id: string, kind: string) => configById(id).metrics.retrieval[kind].recall.toFixed(2);
const slice = (id: string, source: Source, kind: Kind) => configById(id).metrics.by_source_kind[source][kind];
/** Mean input tokens per answer, cached ones included. */
const tokensIn = (id: string) => {
  const c = configById(id).metrics.calls;
  return `${((c.in + c.cached) / (c.calls - c.uncounted) / 1000).toFixed(1)}k`;
};
// Answerable passenger-style questions from each source, set against Claude's one-fact questions (decision 18).
const BY_TYPE = [
  ["wizzair-faq", "faq", "questions taken from the Wizz Air FAQ"],
  ["claude", "fact", "Claude's one-fact questions"],
  ["gemini", "faq", "Gemini's"],
  ["gpt", "faq", "GPT's"],
] as const;
const recallRange = (id: string) => {
  const r = BY_TYPE.map(([s, k]) => {
    const x = slice(id, s, k).recall;
    if (x === null) throw new Error(`${id}: no recall for ${s} ${k}`);
    return x;
  });
  return `${Math.min(...r).toFixed(2)}–${Math.max(...r).toFixed(2)}`;
};

const TH = "px-4 py-3 font-medium";
// Body cells own their top border: with border-collapse the 1px line is split into halves.
const TD = "border-t border-line px-4 py-3";
const NUM = "text-right font-mono";

export default function Overview() {
  const sampled = configs.reduce((n, c) => n + c.check.sampled, 0);
  const agreed = configs.reduce((n, c) => n + c.check.agreed, 0);
  const shipped = configById(DEFAULT_CONFIG);
  const best = configs.reduce((a, b) => (b.metrics.by_kind.all.accuracy > a.metrics.by_kind.all.accuracy ? b : a));
  const k10 = "claude-haiku-5-5-k10";

  const stats = [
    { label: "Shipped setup", value: acc(shipped.id), note: `${shipped.model}, ${shipped.retrieval.toLowerCase()}` },
    { label: "Best setup", value: acc(best.id), note: `${best.model}, ${best.retrieval.toLowerCase()}` },
    { label: "Search recall", value: `${recall(shipped.id, "all")} → ${recall(k10, "all")}`, note: "Top 3 vs top 10 chunks" },
    { label: "Second judge agrees", value: `${agreed}/${sampled}`, note: `${meta.checkModel} re-graded a sample` },
  ];

  const findings = [
    {
      figure: `${acc("claude-haiku-5-5")} → ${acc("deepseek-flash-k10")}`,
      title: "The search limits the answers, and 10 chunks nearly remove the limit",
      body: (
        <>
          With the 3 closest chunks both models get {acc("claude-haiku-5-5")} and {acc("deepseek-flash")} right. With all 91
          chunks in the prompt, {acc("claude-haiku-5-5-full")} and {acc("deepseek-flash-full")}. With 10 chunks,{" "}
          {acc(k10)} and {acc("deepseek-flash-k10")}. On tricky questions search recall is {recall("claude-haiku-5-5", "tricky")}{" "}
          with the top 3 and {recall(k10, "tricky")} with the top 10.
        </>
      ),
    },
    {
      figure: `${tokensIn(shipped.id)} → ${tokensIn(k10)} tokens`,
      title: "Quality or cost: more chunks buy quality, a reranker keeps the cost",
      body: (
        <>
          Reordering the top 10 and keeping 3 raises search recall from {recall("deepseek-flash", "all")} to{" "}
          {recall("deepseek-flash-rerank", "all")} and correct answers from {acc("deepseek-flash")} to{" "}
          {acc("deepseek-flash-rerank")} (Flash). The reranker picks 3 of the top 10, so it can lift a chunk from positions
          4-10: the model reads as much context as with the top 3, so an answer costs the same, but not always the same
          chunks. The reranker adds latency and one more moving part. Ten chunks without a reranker score higher ({acc("deepseek-flash-k10")} on
          Flash, {acc(k10)} on Haiku) but double the input of every answer ({tokensIn(k10)} tokens against{" "}
          {tokensIn(shipped.id)} for Haiku). The reranker did not clear the bar set before the run, so it stays out on this
          91-chunk corpus; on a larger one it is the likely candidate (not measured).
        </>
      ),
    },
    {
      figure: BY_TYPE.map(([s, k]) => pct(slice(shipped.id, s, k).accuracy)).join(" · "),
      title: "Question type matters more than who wrote the question",
      body: (
        <>
          Answerable passenger-style questions with the shipped setup:{" "}
          {BY_TYPE.map(([s, k, who]) => `${pct(slice(shipped.id, s, k).accuracy)} for ${who} (${slice(shipped.id, s, k).questions})`).join(", ")}.
          Search recall is similar ({recallRange(shipped.id)}), so search is not the cause: GPT&apos;s questions ask for several
          facts at once and the answer misses one. Ten chunks help most there ({pct(slice(shipped.id, "gpt", "faq").accuracy)}{" "}
          → {pct(slice(k10, "gpt", "faq").accuracy)}). Samples are small, and the reference answer is per group, which
          penalises omitted details.
        </>
      ),
    },
    {
      figure: `${agreed} / ${sampled}`,
      title: "The judge was checked by a model from another family",
      body: (
        <>
          {meta.judge} graded every answer. {meta.checkModel} re-graded {sampled} of them without seeing the
          first verdict and agreed on {agreed}. The disagreements were reviewed by hand; the{" "}
          <a href={`${REPO_URL}/blob/main/docs/decisions.md`}>decision log</a> has the details.
        </>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-16">
      <section aria-labelledby="intro">
        <p className="font-mono text-xs tracking-caps text-accent uppercase">
          RAG evaluation · {questions.length} questions · {configs.length} setups
        </p>
        <h1 id="intro" className="mt-4 text-4xl font-semibold tracking-tight text-balance">
          A baggage assistant for Wizz Air passengers, and every answer it gave in testing
        </h1>
        <div className="mt-6 grid gap-8 text-lg text-muted md:grid-cols-2">
          <p>
            The assistant answers questions from Wizz Air&apos;s baggage rules and cites the rule it used. When the rules say
            nothing, it says so instead of guessing.
          </p>
          <p>
            It was tested on {questions.length} questions written before the code: {questions.length * 3} answers per setup,
            each graded against a reference answer. These are the saved results; nothing on this site calls a model.
          </p>
        </div>
        <dl className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((s) => (
            <div key={s.label} className="card flex flex-col gap-2 p-6">
              <dt className="text-sm text-muted">{s.label}</dt>
              {/* 2xl, not 3xl: "0.86 → 0.98" in 3xl mono is ~211px, wider than a card in the 4-column row. */}
              <dd className="font-mono text-2xl font-medium tracking-tight whitespace-nowrap">{s.value}</dd>
              <dd className="text-xs text-muted">{s.note}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="grid">
        <h2 id="grid" className="text-2xl font-semibold">Every answer, by question</h2>
        <p className="mt-2 text-muted">
          Each column is one question, each square one of its three answers. Switch the setup to see which answers change.
        </p>
        <div className="mt-6">
          <VerdictGrid rows={rows} options={configOptions} initial={DEFAULT_CONFIG} />
        </div>
      </section>

      <section aria-labelledby="setups">
        <h2 id="setups" className="text-2xl font-semibold">Seven setups, same questions</h2>
        <p className="mt-2 text-muted">
          Two answer models, and four ways to choose what they read: the 3 or 10 chunks closest to the question, 10
          reordered by a reranker with the best 3 kept, or all 91 chunks with no search at all.
        </p>
        <div className="card mt-6 overflow-x-auto">
          <table className="w-full border-separate border-spacing-0 text-left text-sm whitespace-nowrap">
            <thead className="bg-surface-muted text-muted">
              <tr>
                <th scope="col" className={TH}>Answer model</th>
                <th scope="col" className={TH}>What it read</th>
                <th scope="col" className={`${TH} text-right`}>Correct</th>
                <th scope="col" className={`${TH} text-right`}>Range, 3 runs</th>
                <th scope="col" className={`${TH} text-right`}>Search recall</th>
                <th scope="col" className={`${TH} text-right`}>Refused</th>
                <th scope="col" className={`${TH} text-right`}>Errors</th>
                <th scope="col" className={`${TH} text-right`}>Judge check</th>
              </tr>
            </thead>
            <tbody>
              {configs.map((c) => {
                const all = c.metrics.by_kind.all;
                const r = c.metrics.retrieval.all;
                return (
                  <tr key={c.id}>
                    <th scope="row" className={`${TD} font-medium`}>
                      <span className="inline-flex items-center gap-2">
                        {c.model}
                        {c.id === DEFAULT_CONFIG && <Pill tone="accent">Shipped</Pill>}
                      </span>
                    </th>
                    <td className={`${TD} text-muted`}>{c.retrieval}</td>
                    <td className={`${TD} ${NUM} font-medium`}>{pct(all.accuracy)}</td>
                    <td className={`${TD} ${NUM} text-muted`}>
                      {Math.round(all.min * 100)}–{pct(all.max)}
                    </td>
                    <td className={`${TD} ${NUM}`}>{r ? r.recall.toFixed(2) : "—"}</td>
                    <td className={`${TD} ${NUM}`}>{pct(all.refused)}</td>
                    <td className={`${TD} ${NUM}`}>{all.errors}</td>
                    <td className={`${TD} ${NUM}`}>
                      {c.check.agreed}/{c.check.sampled}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="findings">
        <h2 id="findings" className="text-2xl font-semibold">What the numbers say</h2>
        <p className="mt-2 text-muted">
          From the test runs of{" "}
          <time dateTime={meta.runDay}>
            {new Date(`${meta.runDay}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })}
          </time>
          .
        </p>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {findings.map((f) => (
            <article key={f.title} className="card p-6">
              <p className="font-mono text-xl font-medium text-accent">{f.figure}</p>
              <h3 className="mt-3 font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-muted">{f.body}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
