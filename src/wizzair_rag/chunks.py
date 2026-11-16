"""Split one snapshot into chunks: one unit of the source document = one chunk.

Units and their stable ids:
- Help Centre page: the intro and each accordion item (id from its data-label).
- Fares & bundles page: the intro and each bundle (id from the button id).
- GCC PDF: each clause like 15.1.6 with its sub-items 15.1.6.x (id = clause number),
  baggage definitions from section 2, and baggage sections of the Annex.
- Fees: the BAGGAGE FEES group and the WIZZ Priority rows (trolley bag).

Text stays verbatim; only UI strings (feedback widget, image disclaimer) are dropped
and whitespace is collapsed.

Run: uv run python -m wizzair_rag.chunks [YYYY-MM-DD]   (default: latest snapshot)
Writes data/chunks/<snapshot>/chunks.jsonl
"""

import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from typing import Callable

import pdfplumber

from wizzair_rag.download import RAW_DIR
from wizzair_rag.sources import SOURCES, Source

CHUNKS_DIR = Path("data/chunks")


@dataclass(frozen=True)
class Chunk:
    id: str  # "<source id>#<unit id>", stable across snapshots while the unit exists
    source: str
    carrier: str
    effective_from: str | None  # date the document states; None for web pages
    snapshot: str  # date we saved the document
    path: list[str]  # headings from the document title down to the unit
    page: int | None  # PDF page, None for web pages
    url: str
    text: str


def load_chunks(snapshot: str | None = None) -> list[Chunk]:
    """Chunks of one snapshot (default: the latest), in file order."""
    snapshot = snapshot or max(p.name for p in CHUNKS_DIR.iterdir())
    lines = (CHUNKS_DIR / snapshot / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    return [Chunk(**json.loads(line)) for line in lines]


def load_summaries(chunks: list[Chunk]) -> list[str]:
    """Level 2 summaries (written once in a chat session, decision 16), in the order of `chunks`; fails if one is missing."""
    lines = (CHUNKS_DIR / chunks[0].snapshot / "summaries.jsonl").read_text(encoding="utf-8").splitlines()
    by_id = {r["id"]: r["summary"] for r in map(json.loads, lines)}
    return [by_id[c.id] for c in chunks]


def make_chunk(source: Source, snapshot: str, unit: str, path: list[str], text: str, page: int | None = None) -> Chunk:
    url = f"{source.url}#page={page}" if page else source.url
    return Chunk(f"{source.id}#{unit}", source.id, source.carrier, source.effective_from, snapshot, path, page, url, text)


# ---------- HTML (Help Centre, bundles) ----------

UI_NOISE = {"Pictures are for illustration purpose only", "Close", "Accordions"}
# Call-to-action buttons ("TRACE BAG", "SUBMIT CLAIM"): a label without its link says nothing.
CTA_BUTTON = re.compile(r'<a [^>]*data-test="content-button"[\s\S]*?</a>')
INVISIBLE = dict.fromkeys(map(ord, "​‌‍‎‏"))


def html_to_text(html: str) -> str:
    html = re.sub(r"<(script|style|svg)[\s\S]*?</\1>", "", html)
    html = CTA_BUTTON.sub("", html)
    html = re.sub(r"<tr[^>]*>[\s\S]*?</tr>", table_row, html)
    html = re.sub(r"\s+", " ", html)  # line breaks in HTML source are spaces, as in a browser
    html = re.sub(r"<li[^>]*>", "\n- ", html)
    html = re.sub(r"</(p|li|h[1-6]|div|tr|ul|ol|section|button)>|<br\s*/?>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", "", html)).translate(INVISIBLE)
    lines = (" ".join(line.split()) for line in text.split("\n"))  # split() also eats nbsp
    return "\n".join(line for line in lines if line and line != "-" and line not in UI_NOISE)


def table_row(m: re.Match) -> str:
    """One table row on one line, "cell | cell | cell", so "Yes"/"No" keep their row."""
    cells = re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", m.group(0))
    return "<p>" + " | ".join(" ".join(html_to_text(c).split()) for c in cells) + "</p>"


def page_title(html: str) -> str:
    return html_to_text(re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html).group(1))


def cut(html: str, start: str, *ends: str) -> str:
    """The part of html after `start` and before the tag holding the first of `ends` found."""
    html = html[html.index(start) + len(start):]
    return html[: min(html.find(e) for e in ends if e in html)].rsplit("<", 1)[0]


def help_centre_chunks(source: Source, snapshot_dir: Path) -> list[Chunk]:
    html = (snapshot_dir / f"{source.id}.html").read_text(encoding="utf-8")
    title = page_title(html)
    body = cut(html, "</h1>", ">Recommended topics<", ">Need more help?<")
    # re.split with a group keeps the separators: [intro, item tag, item body, item tag, ...]
    parts = re.split(r'(<div class="accordion-item"[^>]*data-label="[^"]+"[^>]*>)', body)
    chunks = []
    if intro := html_to_text(parts[0]):
        chunks.append(make_chunk(source, snapshot_dir.name, "intro", [title], intro))
    for tag, item in zip(parts[1::2], parts[2::2]):
        label = re.search(r'data-label="([^"]+)"', tag).group(1)
        item = cut(item, "", "accordion-item__body__footer")  # drop "Did you find this helpful?"
        item_title = html_to_text(re.search(r'data-test="title"[^>]*>([\s\S]*?)</span>', item).group(1))
        chunks.append(make_chunk(source, snapshot_dir.name, label, [title, item_title], html_to_text(item)))
    return chunks


def bundle_chunks(source: Source, snapshot_dir: Path) -> list[Chunk]:
    html = (snapshot_dir / f"{source.id}.html").read_text(encoding="utf-8")
    title = page_title(html)
    body = cut(html, "</h1>", 'data-test="footer"')
    parts = re.split(r'(<button id="accordion-[^"]+"[^>]*>)', body)
    # The intro ends where the accordion list starts; its "Accordions" h2 is a hidden label.
    intro = html_to_text(parts[0].split('<div class="accordion-root')[0])
    chunks = [make_chunk(source, snapshot_dir.name, "intro", [title], intro)]
    for tag, item in zip(parts[1::2], parts[2::2]):
        unit = re.search(r'id="([^"]+)"', tag).group(1)
        text = html_to_text(item)  # starts with the bundle name, e.g. "BASIC FARE"
        chunks.append(make_chunk(source, snapshot_dir.name, unit, [title, text.split("\n")[0]], text))
    return chunks


# ---------- GCC PDF ----------

GCC_SECTIONS = ("15.", "17.2.", "18.2.")  # Baggage, Liability for Baggage, Baggage Claims
CLAUSE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.\s+(.*)$")  # "15.", "15.1.", ... "15.1.6.10."
DEFINITION = re.compile(r"^([A-Z][A-Z0-9 ,'’/()-]+?)\s*:\s*(.*)$")  # "CHECKED BAGGAGE: means ..."


@dataclass
class Clause:
    num: str
    page: int
    lines: list[str]  # first line holds the number (and the title, for headings)

    @property
    def level(self) -> int:
        return self.num.count(".") + 1

    @property
    def title(self) -> str:
        return self.lines[0].split(" ", 1)[1]

    @property
    def text(self) -> str:
        return " ".join(self.lines)  # PDF line breaks inside a clause are not paragraphs


def pdf_lines(path: Path) -> list[tuple[int, str]]:
    with pdfplumber.open(path) as pdf:
        return [
            (number, line.strip())
            for number, page in enumerate(pdf.pages, 1)
            for line in (page.extract_text() or "").split("\n")
            if line.strip() and not line.strip().isdigit()  # drop page numbers
        ]


def gcc_chunks(source: Source, snapshot_dir: Path) -> list[Chunk]:
    lines = pdf_lines(snapshot_dir / f"{source.id}.pdf")
    annex_at = next(i for i, (_, line) in enumerate(lines) if line == "Annex")
    snapshot = snapshot_dir.name

    # Body: numbered clauses. A plain "N." line counts as a new section only if N is the
    # next section number, so numbered lists inside the text do not break the structure.
    clauses: list[Clause] = []
    section = 0
    for page, line in lines[:annex_at]:
        m = CLAUSE.match(line)
        is_new = m and (m.group(1).count(".") > 0 or int(m.group(1)) == section + 1)
        if is_new:
            section = int(m.group(1).split(".")[0])
            clauses.append(Clause(m.group(1), page, [line]))
        elif clauses:
            clauses[-1].lines.append(line)

    titles = {c.num: c.title for c in clauses if c.level <= 2}
    chunks = []
    for i, c in enumerate(clauses):
        if not (c.num + ".").startswith(GCC_SECTIONS) or c.level not in (2, 3):
            continue
        children = []
        for child in clauses[i + 1:]:
            if not child.num.startswith(c.num + "."):
                break
            children.append(child)
        if c.level == 2 and children:
            continue  # a heading like "15.1. Checked Baggage"; its clauses are the chunks
        text = "\n".join([c.text] + [ch.text for ch in children])
        path = [titles[n] for n in (c.num.split(".")[0], ".".join(c.num.split(".")[:2])) if n != c.num]
        chunks.append(make_chunk(source, snapshot, c.num, path, text, c.page))

    # Section 2: definitions of baggage terms, one per chunk.
    defs: list[Clause] = []
    in_defs = False
    for page, line in lines[:annex_at]:
        if line.startswith("2. Meaning"):
            in_defs = True
        elif line.startswith("3. "):
            break
        elif in_defs and (m := DEFINITION.match(line)):
            defs.append(Clause(m.group(1).strip(), page, [line]))
        elif in_defs and defs:
            defs[-1].lines.append(line)
    for d in defs:
        if "BAGGAGE" in d.num or "PERSONAL PROPERTY" in d.num:
            slug = re.sub(r"[^a-z0-9]+", "-", d.num.lower()).strip("-")
            chunks.append(make_chunk(source, snapshot, f"def-{slug}", ["Definitions"], d.text, d.page))

    # Annex: "N. Title" sections; keep the ones about baggage.
    annex: list[Clause] = []
    for page, line in lines[annex_at:]:
        if (m := re.match(r"^(\d{1,2})\.\s+(.*)$", line)) and int(m.group(1)) == len(annex) + 1:
            annex.append(Clause(m.group(1), page, [line]))
        elif annex:
            annex[-1].lines.append(line)
    for a in annex:
        if "aggage" in a.title:
            text = a.lines[0] + "\n" + " ".join(a.lines[1:])  # heading on its own line
            chunks.append(make_chunk(source, snapshot, f"annex-{a.num}", ["Annex", a.title], text, a.page))
    return chunks


# ---------- Fees ----------

FEE_GROUPS = ("BAGGAGE FEES", "BOOKING FEES", "CHANGE FEES", "SERVICE FEES")


def fee_rows(text: str) -> str:
    """Fee table rows from the page innerText, one per line.

    The page shows a fee as "Name" above "CHANNEL<tab>method<tab>amount";
    here it becomes "Name (CHANNEL) | method | amount".
    """
    out: list[str] = []
    for line in text.split("\n"):
        cells = line.split("\t")
        if len(cells) == 3 and cells[0].isupper() and cells[0] != "NAME OF THE FEE":
            out[-1] = " | ".join([f"{out[-1]} ({cells[0]})", *cells[1:]])
        elif line.strip():
            out.append(" | ".join(cells))
    return "\n".join(out)


def fees_chunks(source: Source, snapshot_dir: Path) -> list[Chunk]:
    # The table is rendered by JS, so the snapshot keeps its text in fees-table.txt.
    text = (snapshot_dir / "fees-table.txt").read_text(encoding="utf-8")
    title = text.split("\n")[0]
    starts = [text.index(f"\n{g}\n") + 1 for g in FEE_GROUPS]
    groups = {g: text[s:e].strip() for g, s, e in zip(FEE_GROUPS, starts, starts[1:] + [len(text)])}

    baggage = fee_rows(groups["BAGGAGE FEES"])
    service = fee_rows(groups["SERVICE FEES"]).split("\n")
    # "SERVICE FEES", the column header, then only the WIZZ Priority rows.
    priority = "\n".join(service[:2] + [r for r in service if r.startswith("WIZZ Priority")])
    return [
        make_chunk(source, snapshot_dir.name, "baggage-fees", [title, "BAGGAGE FEES"], baggage),
        make_chunk(source, snapshot_dir.name, "wizz-priority", [title, "SERVICE FEES", "WIZZ Priority"], priority),
    ]


# ---------- Run ----------

CHUNKERS: dict[str, Callable[[Source, Path], list[Chunk]]] = {
    "hc-cabin-baggage": help_centre_chunks,
    "hc-checked-in-baggage": help_centre_chunks,
    "hc-special-baggage": help_centre_chunks,
    "hc-childrens-baggage": help_centre_chunks,
    "hc-restricted-items": help_centre_chunks,
    "hc-bags-reporting-procedure": help_centre_chunks,
    "fees-fares-bundles": bundle_chunks,
    "fees-all-services": fees_chunks,
    "gcc-wah-2023-03-01": gcc_chunks,
}


def build(snapshot_dir: Path) -> list[Chunk]:
    by_id = {s.id: s for s in SOURCES}
    chunks = [c for source_id, chunker in CHUNKERS.items() for c in chunker(by_id[source_id], snapshot_dir)]
    duplicates = [i for i, n in Counter(c.id for c in chunks).items() if n > 1]
    if duplicates:
        raise ValueError(f"duplicate chunk ids: {duplicates}")
    if empty := [c.id for c in chunks if not c.text.strip()]:
        raise ValueError(f"empty chunks: {empty}")
    return chunks


def main() -> None:
    snapshot = sys.argv[1] if len(sys.argv) > 1 else max(p.name for p in RAW_DIR.iterdir() if p.is_dir())
    chunks = build(RAW_DIR / snapshot)
    out = CHUNKS_DIR / snapshot / "chunks.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(asdict(c), ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")

    sizes = sorted(len(c.text) for c in chunks)
    print(f"{len(chunks)} chunks -> {out}")
    print(f"size: min {sizes[0]}, median {sizes[len(sizes) // 2]}, max {sizes[-1]} chars")
    for source_id, n in Counter(c.source for c in chunks).items():
        print(f"  {source_id}: {n}")


if __name__ == "__main__":
    main()
