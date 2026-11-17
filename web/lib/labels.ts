// Client-safe: names and outcomes shared by server pages and client components.
import type { Run } from "./data";

export const KINDS = ["fact", "faq", "tricky", "no-answer"] as const;
export const SOURCES = ["claude", "wizzair-faq", "gemini", "gpt"] as const;
export type Kind = (typeof KINDS)[number];
export type Source = (typeof SOURCES)[number];

export const KIND_LABEL: Record<Kind, string> = {
  fact: "Facts",
  faq: "FAQ-style",
  tricky: "Tricky",
  "no-answer": "Not in the sources",
};

export const KIND_ABOUT: Record<Kind, string> = {
  fact: "One fact from the rules, in three wordings: formal, search-style, a passenger's situation.",
  faq: "Answerable questions as passengers ask them: 19 taken from the Wizz Air FAQ, the rest written by Gemini and GPT.",
  tricky: "False premises, edge cases, two sections at once, partial answers, off-topic.",
  "no-answer": "They sound answerable, but the sources do not answer them. Refusing is correct.",
};

export const SOURCE_LABEL: Record<Source, string> = { claude: "Claude", "wizzair-faq": "Wizz Air FAQ", gemini: "Gemini", gpt: "GPT" };

// The topics of evals/questions*.json; a topic missing here fails the build (see data.ts).
export const TOPIC_LABEL: Record<string, string> = {
  cabin: "cabin bags",
  checked: "checked bags",
  fees: "fees",
  bundles: "fare bundles",
  children: "children's baggage",
  special: "special baggage",
  restricted: "restricted items",
  "damaged-lost": "damaged and lost bags",
  "off-topic": "off-topic",
};

/** One setup as the pickers, the grid and the list show it. */
export type ConfigOption = { id: string; model: string; retrieval: string; accuracy: number; byKind: Record<Kind, number> };

export type Outcome = "correct" | "wrong" | "error";

export const outcomeOf = (run: Run): Outcome => (run.kind === "error" ? "error" : run.correct ? "correct" : "wrong");

export const OUTCOME_LABEL: Record<Outcome, string> = {
  correct: "Correct",
  wrong: "Wrong",
  error: "Pipeline error",
};

export type QuestionRow = {
  id: string;
  question: string;
  kind: Kind;
  topic: string;
  source: Source;
  outcomes: Record<string, Outcome[]>; // config id -> the 3 runs
};

export const correctCount = (o: Outcome[]) => o.filter((x) => x === "correct").length;

export const pct = (x: number) => `${Math.round(x * 100)}%`;
