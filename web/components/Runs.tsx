import type { Outcome } from "@/lib/labels";

/** How each verdict is drawn: filled for a verdict, an outline for an error (no verdict),
 *  so the shape tells error apart even where the colour does not. */
export const OUTCOME_MARK: Record<Outcome, string> = { correct: "bg-correct", wrong: "bg-wrong", error: "border-2 border-error" };

const CELL = { sm: "size-2", lg: "size-3" } as const;

/** The three runs of one question as squares. Decorative: the parent carries the text. */
export function Runs({ outcomes, vertical = false, size = "sm" }: { outcomes: Outcome[]; vertical?: boolean; size?: keyof typeof CELL }) {
  return (
    <span aria-hidden className={`flex gap-0.5 ${vertical ? "flex-col" : ""}`}>
      {outcomes.map((o, i) => (
        <span key={i} className={`${CELL[size]} rounded-xs transition-colors duration-300 ${OUTCOME_MARK[o]}`} />
      ))}
    </span>
  );
}

export function Legend() {
  return (
    <ul className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-muted">
      {(["correct", "wrong", "error"] as const).map((o) => (
        <li key={o} className="flex items-center gap-2">
          <span aria-hidden className={`size-2 rounded-xs ${OUTCOME_MARK[o]}`} />
          {o === "correct" ? "Correct" : o === "wrong" ? "Wrong" : "Pipeline error (counted as wrong)"}
        </li>
      ))}
    </ul>
  );
}
