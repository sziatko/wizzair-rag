"""Level 1 RAG, as in the Cookbook: embed the question, take the top-k chunks by cosine
similarity, let Claude answer from them with citations or refuse.

Run: uv run --env-file .env python -m wizzair_rag.rag "Can I take a 12 kg bag into the cabin?"
"""

import json
import os
import sys
import time
from dataclasses import dataclass
from functools import cache
from typing import Literal

import anthropic
import numpy as np
import voyageai
from anthropic.types import Message
from pydantic import BaseModel, Field, create_model

from wizzair_rag.chunks import Chunk, load_chunks
from wizzair_rag.index import chunk_for_embedding, embed, load_index
from wizzair_rag.sources import HELP_CENTRE

ANSWER_MODEL = "claude-haiku-5-5"
DEEPSEEK_URL = "https://api.deepseek.com/anthropic"  # DeepSeek's Anthropic-compatible API (decision 10)
TOP_K = 3
RERANK_MODEL = "rerank-2.5"
RERANK_POOL = 10  # candidates the reranker reorders before the top k is kept
RATE_LIMIT_ATTEMPTS = 6  # DeepSeek lowers its concurrency limit with the remaining balance
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


def reply_schema(ids: list[str]) -> type[Reply]:
    """A Reply whose citations can only be these ids (decision 11). The model cannot cite a
    sub-clause id like `gcc-x#18.2.7.2`: Claude's constrained decoding rejects it, and for
    DeepSeek, which has no constrained decoding, validation does."""
    cited = create_model("Answer", __base__=Answer, citations=(list[Literal[tuple(ids)]], ...))
    return create_model("Reply", __base__=Reply, reply=(cited | Refusal, Field(discriminator="kind")))


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float  # cosine similarity


@dataclass(frozen=True)
class Result:
    question: str
    hits: list[Hit]
    reply: Answer | Refusal
    tokens: dict  # {"in", "cached", "out"} of the answer call
    seconds: float  # wall time of the answer call, retries included


chunks = load_chunks()
vectors = load_index(chunks)
client = anthropic.Anthropic()


@cache
def deepseek() -> anthropic.Anthropic:
    """Built on first use, so commands that never call DeepSeek do not need its key."""
    return anthropic.Anthropic(base_url=DEEPSEEK_URL, api_key=os.environ["DEEPSEEK_API_KEY"])


def deepseek_parse[T: BaseModel](model: str, system: str, user: str, schema: type[T]) -> tuple[T, Message]:
    """DeepSeek's Anthropic API ignores `output_config.format` (only `effort` is supported),
    so nothing constrains its output to the schema: the schema goes into the system prompt
    and the reply is validated here. Invalid JSON raises pydantic's ValidationError, a
    ValueError, which the evals record as a pipeline error (decision 10)."""
    for attempt in range(RATE_LIMIT_ATTEMPTS):
        try:
            response = deepseek().messages.create(
                model=model,
                max_tokens=16000,
                system=f"{system}\n\nReply with only a JSON object that matches this JSON schema, with no other text:\n"
                f"{json.dumps(schema.model_json_schema())}",
                messages=[{"role": "user", "content": user}],
            )
            break
        except anthropic.RateLimitError:  # 429: wait and ask again; the SDK's own two retries are too short
            if attempt == RATE_LIMIT_ATTEMPTS - 1:
                raise
            time.sleep(min(5 * 2**attempt, 60))
    text = "".join(b.text for b in response.content if b.type == "text")
    return schema.model_validate_json(text), response


def usage_of(response: Message) -> dict:
    # DeepSeek caches prompt prefixes on its own; `in` counts only the uncached input tokens.
    u = response.usage
    return {"in": u.input_tokens, "cached": u.cache_read_input_tokens or 0, "out": u.output_tokens}


def search(query_vector: np.ndarray, k: int = TOP_K, matrix: np.ndarray = vectors) -> list[Hit]:
    scores = matrix @ query_vector
    return [Hit(chunks[i], float(scores[i])) for i in np.argsort(-scores)[:k]]


def rerank(query: str, hits: list[Hit], k: int) -> list[Hit]:
    """Reorder hits with a Voyage reranker and keep the best k (decision 13, variant C)."""
    docs = [chunk_for_embedding(h.chunk) for h in hits]
    for attempt in range(RATE_LIMIT_ATTEMPTS):
        try:
            order = voyageai.Client().rerank(query, docs, model=RERANK_MODEL, top_k=k).results
            return [hits[o.index] for o in order]
        except voyageai.error.RateLimitError:
            if attempt == RATE_LIMIT_ATTEMPTS - 1:
                raise
            time.sleep(min(5 * 2**attempt, 60))


def retrieve(question: str, k: int = TOP_K) -> list[Hit]:
    return search(embed([question], "query")[0], k)


def excerpt(c: Chunk) -> str:
    return f'<excerpt id="{c.id}" title="{" > ".join(c.path)}">\n{c.text}\n</excerpt>'


def answer(question: str) -> Result:
    return generate(question, retrieve(question))


def generate(question: str, hits: list[Hit], model: str = ANSWER_MODEL) -> Result:
    """The answer step alone, for evals that retrieve many questions in one batch."""
    excerpts = "\n\n".join(excerpt(h.chunk) for h in hits)
    user = f"<excerpts>\n{excerpts}\n</excerpts>\n\nQuestion: {question}"
    schema = reply_schema([h.chunk.id for h in hits])
    started = time.perf_counter()
    if model.startswith("deepseek"):
        parsed, response = deepseek_parse(model, SYSTEM, user, schema)
    else:
        response = client.messages.parse(
            model=model, max_tokens=16000, system=SYSTEM, messages=[{"role": "user", "content": user}], output_format=schema
        )
        parsed = response.parsed_output
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"model stopped with {response.stop_reason!r}: {question}")
    reply = parsed.reply
    if isinstance(reply, Answer) and not reply.citations:  # ids outside the retrieved chunks are already ruled out by the schema
        raise ValueError("an answer without citations")
    return Result(question, hits, reply, usage_of(response), time.perf_counter() - started)


def render(result: Result) -> str:
    """What the passenger sees: the answer with its sources and a disclaimer, or the standard refusal."""
    if isinstance(result.reply, Refusal):
        return REFUSAL
    by_id = {h.chunk.id: h.chunk for h in result.hits}
    cited = [by_id[i] for i in result.reply.citations]
    lines = [result.reply.text, "", "Sources:"]
    lines += [f"- {' > '.join(c.path)} ({c.url})" for c in cited]
    if note := consumer_note(result.reply.citations):
        lines.append(note)
    lines.append(f"\n{disclaimer(cited[0].snapshot)}")
    return "\n".join(lines)


def consumer_note(citation_ids: list[str]) -> str | None:
    if NOT_APPLIED_TO_CONSUMERS & set(citation_ids):
        return "Note: Wizz Air states it does not apply GCC clauses 17.2.2, 17.2.5 and 18.2.9 to consumers."
    return None


def disclaimer(snapshot: str) -> str:
    return f"Not official advice. Based on Wizz Air documents saved on {snapshot}; check wizzair.com before you travel."


def main() -> None:
    result = answer(" ".join(sys.argv[1:]))
    for h in result.hits:
        print(f"  {h.score:.3f}  {h.chunk.id}")
    print()
    print(render(result))


if __name__ == "__main__":
    main()
