import type { Metadata } from "next";
import Link from "next/link";
import { QuestionDetail, type Setup } from "@/components/QuestionDetail";
import { DEFAULT_CONFIG, chunks, configOptions, meta, questions } from "@/lib/data";
import { KIND_LABEL, SOURCE_LABEL, TOPIC_LABEL } from "@/lib/labels";

export const dynamicParams = false;

export function generateStaticParams() {
  return questions.map((q) => ({ id: q.id }));
}

const find = (id: string) => questions.find((q) => q.id === id)!;

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  return { title: `${find((await params).id).question} | Baggage assistant evals` };
}

const setups: Setup[] = configOptions.map((o) => ({ ...o, judge: meta.judge, checkModel: meta.checkModel }));

export default async function QuestionPage({ params }: { params: Promise<{ id: string }> }) {
  const q = find((await params).id);
  // Only the chunks this page mentions, not all 91.
  const ids = new Set([
    ...q.expected,
    ...Object.values(q.configs).flatMap((c) => [...c.retrieved.map(([id]) => id), ...c.runs.flatMap((r) => (r.kind === "answer" ? r.citations : []))]),
  ]);
  const used = Object.fromEntries([...ids].map((id) => [id, chunks[id]]));
  const tags = [KIND_LABEL[q.kind], TOPIC_LABEL[q.topic], `Source: ${SOURCE_LABEL[q.source]}`];

  return (
    <>
      <nav aria-label="Breadcrumb">
        <Link href="/questions" className="inline-flex items-center gap-2 text-sm font-medium">
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10 3 5 8l5 5" />
          </svg>
          All questions
        </Link>
      </nav>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight text-pretty">{q.question}</h1>
      <ul aria-label="About this question" className="mt-4 flex flex-wrap gap-2">
        {tags.map((t) => (
          <li key={t} className="rounded-full border border-line bg-surface px-3 text-sm/6 text-muted">
            {t}
          </li>
        ))}
      </ul>

      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <section aria-labelledby="reference" className="rounded-lg bg-accent-soft p-6">
          <h2 id="reference" className="text-sm font-medium text-accent">Reference answer the judge compares with</h2>
          <p className="mt-2">{q.reference}</p>
        </section>
        <section aria-labelledby="where" className="card p-6">
          <h2 id="where" className="text-sm font-medium text-muted">Where the sources answer it</h2>
          {q.expected.length ? (
            <ul className="mt-2 flex flex-col gap-1">
              {q.expected.map((id) => (
                <li key={id}>
                  <a href={chunks[id].url}>{chunks[id].title}</a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2">Nowhere: the sources do not answer this, so refusing is the correct reply.</p>
          )}
        </section>
      </div>

      <div className="mt-12">
        <QuestionDetail question={q} setups={setups} chunks={used} initial={DEFAULT_CONFIG} />
      </div>
    </>
  );
}
