import type { Metadata } from "next";
import { QuestionList } from "@/components/QuestionList";
import { DEFAULT_CONFIG, configOptions, rows } from "@/lib/data";

export const metadata: Metadata = { title: "All questions | Baggage assistant evals" };

export default function Questions() {
  return (
    <>
      <h1 className="text-3xl font-semibold tracking-tight">All {rows.length} questions</h1>
      <p className="mt-2 text-muted">
        Each row shows how the three answers to one question were graded. Open a question to read the answers, what the
        search found and why the judge decided as it did.
      </p>
      <div className="mt-8">
        <QuestionList rows={rows} options={configOptions} initial={DEFAULT_CONFIG} />
      </div>
    </>
  );
}
