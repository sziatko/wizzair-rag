const TONE = {
  neutral: "bg-surface-muted text-muted",
  accent: "bg-accent-soft text-accent",
  correct: "bg-surface-muted font-medium text-correct-ink",
} as const;

/** A small rounded label: a question's kind or topic, "Shipped", "holds the answer". */
export function Pill({ tone = "neutral", children }: { tone?: keyof typeof TONE; children: React.ReactNode }) {
  return <span className={`rounded-full px-2 text-xs/5 ${TONE[tone]}`}>{children}</span>;
}
