"""Level 1 RAG, as in the Cookbook: embed the question, take the top-k chunks by cosine
similarity, let Claude answer from them with citations or refuse.

Run: uv run --env-file .env python -m wizzair_rag.rag "Can I take a 12 kg bag into the cabin?"
"""

import sys
from dataclasses import dataclass
from typing import Literal

import anthropic
import numpy as np
from pydantic import BaseModel, Field

from wizzair_rag.chunks import Chunk, load_chunks
from wizzair_rag.index import embed, load_index
from wizzair_rag.sources import HELP_CENTRE

ANSWER_MODEL = "claude-haiku-5-5"
TOP_K = 3
BAGGAGE_HELP = f"{HELP_CENTRE}/booking-information-and-services/baggage"
REFUSAL = (
    "There is no information about this in the sources I have. "
    f"For details, please check the Wizz Air Help Centre: {BAGGAGE_HELP}"
)
# The GCC page says Wizz Air does not apply these clauses to consumers.
NOT_APPLIED_TO_CONSUMERS = {"gcc-wah-2023-03-01#17.2.2", "gcc-wah-2023-03-01#17.2.5", "gcc-wah-2023-03-01#18.2.9"}

SYSTEM = """You answer questions from Wizz Air passengers about baggage, using only the excerpts given with each question. Each excerpt has an id.

- Answer only from the excerpts, never from general knowledge. Keep numbers, sizes and prices exactly as written.
- Refuse (kind "refusal") when the excerpts do not answer the core of the question, or the question is not about Wizz Air baggage. Never write an answer that only says the excerpts do not cover it: that is a refusal.
- If the excerpts answer the core of the question but not a detail, or only one part of it, answer that part and say plainly what the sources do not cover. This applies only when the excerpts really state a fact that answers part of the question.
- Sources disagree only when two excerpts give different values or rules for the same thing (for example the Help Centre and the General Conditions of Carriage state different limits for the same item). Then give both values, cite both, say that the sources differ, and advise checking with Wizz Air. Two rules about different things (a deadline and a loss rule, a limit and a fee) are not a disagreement: state each as it is and do not say the sources differ.
- Cite the ids of every excerpt your answer relies on. Cite only the id exactly as it appears in an excerpt's id attribute, never a clause number inside the text (an excerpt with id "gcc-x#15.1.6" is cited as "gcc-x#15.1.6", not "gcc-x#15.1.6.3").
- Be short and plain: a few sentences, in English."""


# A discriminated union, like `type Reply = {kind: "answer", ...} | {kind: "refusal"}` in TypeScript:
# a refusal cannot carry text or citations, an answer cannot lack them.
class Answer(BaseModel):
    kind: Literal["answer"]
    text: str
    citations: list[str]


class Refusal(BaseModel):
    kind: Literal["refusal"]


class Reply(BaseModel):
    reply: Answer | Refusal = Field(discriminator="kind")


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float  # cosine similarity


@dataclass(frozen=True)
class Result:
    question: str
    hits: list[Hit]
    reply: Answer | Refusal


chunks = load_chunks()
vectors = load_index(chunks)
client = anthropic.Anthropic()


def search(query_vector: np.ndarray, k: int = TOP_K) -> list[Hit]:
    scores = vectors @ query_vector
    return [Hit(chunks[i], float(scores[i])) for i in np.argsort(-scores)[:k]]


def retrieve(question: str, k: int = TOP_K) -> list[Hit]:
    return search(embed([question], "query")[0], k)


def excerpt(c: Chunk) -> str:
    return f'<excerpt id="{c.id}" title="{" > ".join(c.path)}">\n{c.text}\n</excerpt>'


def answer(question: str) -> Result:
    return generate(question, retrieve(question))


def generate(question: str, hits: list[Hit]) -> Result:
    """The answer step alone, for evals that retrieve many questions in one batch."""
    excerpts = "\n\n".join(excerpt(h.chunk) for h in hits)
    response = client.messages.parse(
        model=ANSWER_MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"<excerpts>\n{excerpts}\n</excerpts>\n\nQuestion: {question}"}],
        output_format=Reply,
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"model stopped with {response.stop_reason!r}: {question}")
    reply = response.parsed_output.reply
    if isinstance(reply, Answer):
        retrieved = {h.chunk.id for h in hits}
        if not reply.citations or not set(reply.citations) <= retrieved:
            raise ValueError(f"citations {reply.citations} are not among retrieved {sorted(retrieved)}")
    return Result(question, hits, reply)


def render(result: Result) -> str:
    """What the passenger sees: the answer with its sources and a disclaimer, or the standard refusal."""
    if isinstance(result.reply, Refusal):
        return REFUSAL
    by_id = {h.chunk.id: h.chunk for h in result.hits}
    cited = [by_id[i] for i in result.reply.citations]
    lines = [result.reply.text, "", "Sources:"]
    lines += [f"- {' > '.join(c.path)} ({c.url})" for c in cited]
    if NOT_APPLIED_TO_CONSUMERS & set(result.reply.citations):
        lines.append("Note: Wizz Air states it does not apply GCC clauses 17.2.2, 17.2.5 and 18.2.9 to consumers.")
    lines.append(f"\nNot official advice. Based on Wizz Air documents saved on {cited[0].snapshot}; check wizzair.com before you travel.")
    return "\n".join(lines)


def main() -> None:
    result = answer(" ".join(sys.argv[1:]))
    for h in result.hits:
        print(f"  {h.score:.3f}  {h.chunk.id}")
    print()
    print(render(result))


if __name__ == "__main__":
    main()
