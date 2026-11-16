"""A local demo page for the assistant: one HTML file, no framework, no deploy.

Run: uv run --env-file .env python -m wizzair_rag.demo     then open http://127.0.0.1:8000
Every question is a real call to the pipeline (Voyage embedding + Haiku answer), a fraction of a cent.
"""

import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from wizzair_rag.rag import REFUSAL, Refusal, Result, answer, chunks, consumer_note, disclaimer

PAGE = Path(__file__).with_name("demo.html").read_bytes()
MAX_QUESTION = 500


def payload(result: Result) -> dict:
    """What the page shows: the reply, its sources, and every retrieved chunk with its score."""
    cited_ids = [] if isinstance(result.reply, Refusal) else result.reply.citations
    hits = [{"id": h.chunk.id, "title": " > ".join(h.chunk.path), "url": h.chunk.url, "score": round(h.score, 3), "cited": h.chunk.id in cited_ids} for h in result.hits]
    base = {"hits": hits, "total_chunks": len(chunks), "seconds": round(result.seconds, 1), "snapshot": result.hits[0].chunk.snapshot}
    if isinstance(result.reply, Refusal):
        return base | {"kind": "refusal", "text": REFUSAL}
    return base | {"kind": "answer", "text": result.reply.text, "note": consumer_note(cited_ids), "disclaimer": disclaimer(base["snapshot"])}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/":
            return self.send_error(404)
        self.respond(200, "text/html; charset=utf-8", PAGE)

    def do_POST(self) -> None:
        if self.path != "/ask":
            return self.send_error(404)
        try:
            question = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["question"].strip()
            if not question or len(question) > MAX_QUESTION:
                return self.respond(400, "application/json", json.dumps({"error": f"Ask a question of 1-{MAX_QUESTION} characters."}).encode())
            body = json.dumps(payload(answer(question))).encode()
        except Exception as e:  # the page shows the message; the terminal keeps the traceback
            traceback.print_exc()
            return self.respond(500, "application/json", json.dumps({"error": f"{type(e).__name__}: {e}"}).encode())
        self.respond(200, "application/json", body)

    def respond(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print("http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
