"""Document retrieval tool (required tool #1).

- Extracts text from the six PDFs, splits into section chunks.
- Ranks chunks with a small, dependency-free BM25 (keeps the HF Space light and
  fully offline -- no embedding API needed).
- ACCESS CONTROL: customer-specific agreements are only retrievable by that
  customer's account (or by internal staff). A customer of ACCT-002 can never
  retrieve Northstar's contract, even if the model asks for it.
- RELIABILITY: every returned chunk is annotated with its authority tier and
  status, and deprecated docs are demoted, so the agent can resolve conflicts.
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass

from app.auth.context import UserContext
from app.config import DOCS_DIR
from app.reliability.sources import (
    PRECEDENCE_NOTE,
    SOURCES,
    SourceDoc,
    source_for_filename,
)
from app.tools.registry import Tool, ToolResult, registry

try:
    import pdfplumber  # type: ignore
    _HAS_PDFPLUMBER = True
except Exception:  # noqa: BLE001
    _HAS_PDFPLUMBER = False


# --------------------------- chunking ---------------------------------------
@dataclass
class Chunk:
    doc_id: str
    section: str
    text: str
    source: SourceDoc


_WORD = re.compile(r"[a-z0-9]+")


def _tokenize(s: str) -> list[str]:
    return _WORD.findall(s.lower())


def _extract_text(path: str) -> str:
    if _HAS_PDFPLUMBER:
        try:
            with pdfplumber.open(path) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception:  # noqa: BLE001
            pass
    # Fallback to pdftotext binary.
    import subprocess

    try:
        out = subprocess.run(
            ["pdftotext", "-layout", path, "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.stdout
    except Exception:  # noqa: BLE001
        return ""


def _split_sections(doc_id: str, text: str, source: SourceDoc) -> list[Chunk]:
    """Split on numbered section headers like '1. Scope', keeping a header line."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    chunks: list[Chunk] = []
    cur_title = "Overview"
    cur_lines: list[str] = []

    header_re = re.compile(r"^\s*(\d+)\.\s+(.{2,80})$")

    def flush():
        body = "\n".join(cur_lines).strip()
        if body:
            chunks.append(Chunk(doc_id=doc_id, section=cur_title, text=body, source=source))

    for ln in lines:
        m = header_re.match(ln)
        if m:
            flush()
            cur_title = f"{m.group(1)}. {m.group(2).strip()}"
            cur_lines = [ln.strip()]
        else:
            cur_lines.append(ln)
    flush()
    # Guard against a doc with no numbered headers.
    if not chunks and text.strip():
        chunks.append(Chunk(doc_id=doc_id, section="Full document", text=text.strip(), source=source))
    return chunks


# --------------------------- BM25 index -------------------------------------
class _BM25:
    def __init__(self, docs_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = docs_tokens
        self.N = len(docs_tokens)
        self.avgdl = sum(len(d) for d in docs_tokens) / max(self.N, 1)
        self.df: Counter = Counter()
        for d in docs_tokens:
            for term in set(d):
                self.df[term] += 1
        self.tf = [Counter(d) for d in docs_tokens]

    def _idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def score(self, query_tokens: list[str], idx: int) -> float:
        tf = self.tf[idx]
        dl = len(self.docs[idx])
        s = 0.0
        for term in query_tokens:
            if term not in tf:
                continue
            idf = self._idf(term)
            freq = tf[term]
            denom = freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            s += idf * (freq * (self.k1 + 1)) / denom
        return s


# --------------------------- index build ------------------------------------
class DocumentIndex:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self.bm25: _BM25 | None = None
        self.built = False
        self.error: str | None = None

    def build(self) -> None:
        self.chunks = []
        for doc_id, source in SOURCES.items():
            path = os.path.join(DOCS_DIR, source.filename)
            if not os.path.exists(path):
                continue
            text = _extract_text(path)
            self.chunks.extend(_split_sections(doc_id, text, source))
        if not self.chunks:
            self.error = "No documents indexed (are the PDFs in app/data/documents/?)."
            self.built = False
            return
        self.bm25 = _BM25([_tokenize(c.text + " " + c.section) for c in self.chunks])
        self.built = True
        self.error = None

    def _visible(self, ctx: UserContext, chunk: Chunk) -> bool:
        """Access control: scope agreements to their account."""
        src = chunk.source
        if src.is_agreement and ctx.is_customer:
            return src.account_id == ctx.account_id
        return True

    def search(self, ctx: UserContext, query: str, top_k: int = 5) -> list[tuple[Chunk, float]]:
        if not self.built or self.bm25 is None:
            return []
        q = _tokenize(query)
        scored = []
        for i, chunk in enumerate(self.chunks):
            if not self._visible(ctx, chunk):
                continue
            base = self.bm25.score(q, i)
            if base <= 0:
                continue
            # Demote deprecated sources so they rank below current guidance.
            if chunk.source.is_deprecated:
                base *= 0.4
            scored.append((chunk, base))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


INDEX = DocumentIndex()
INDEX.build()


def rebuild_index() -> DocumentIndex:
    INDEX.build()
    return INDEX


# --------------------------- tool handlers ----------------------------------
def search_documents(ctx: UserContext, query: str, top_k: int = 5) -> ToolResult:
    hits = INDEX.search(ctx, query, top_k=top_k)
    if not hits:
        return ToolResult(
            ok=True,
            data=[],
            message="No matching policy/document sections found.",
            meta={"precedence": PRECEDENCE_NOTE},
        )
    results = []
    for chunk, score in hits:
        src = chunk.source
        results.append(
            {
                "doc_id": src.doc_id,
                "title": src.title,
                "section": chunk.section,
                "authority_tier": src.authority_tier,
                "status": src.status,
                "doc_type": src.doc_type,
                "effective": src.effective,
                "account_id": src.account_id,
                "excerpt": chunk.text[:900],
                "relevance": round(score, 3),
            }
        )
    return ToolResult(
        ok=True,
        data=results,
        message=f"Found {len(results)} relevant section(s). Apply source precedence when they conflict.",
        meta={"precedence": PRECEDENCE_NOTE},
    )


def get_document(ctx: UserContext, doc_id: str) -> ToolResult:
    src = SOURCES.get(doc_id)
    if src is None:
        return ToolResult(ok=False, message=f"Unknown document '{doc_id}'.")
    # Access control on full-document reads too.
    if src.is_agreement and ctx.is_customer and src.account_id != ctx.account_id:
        return ToolResult(ok=False, message="You are not authorised to view that agreement.")
    full = "\n\n".join(c.text for c in INDEX.chunks if c.doc_id == doc_id)
    return ToolResult(
        ok=True,
        data={"doc_id": doc_id, "title": src.title, "status": src.status,
              "authority_tier": src.authority_tier, "text": full},
        message=f"Full text of {src.title}.",
        meta={"precedence": PRECEDENCE_NOTE},
    )


def register_document_tools() -> None:
    registry.register(
        Tool(
            name="search_documents",
            description=(
                "Search ParcelPilot policies, SOPs, product docs, and customer "
                "agreements for relevant sections. Returns excerpts annotated with "
                "authority_tier (1=customer agreement, 2=current policy/SOP, "
                "3=product docs, 9=deprecated) and status. Use this for any rule, "
                "SLA, fee, credit, capability, or known-issue question. When results "
                "conflict, follow source precedence and prefer lower authority_tier."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look up, e.g. 'cancellation fee BOOKED before pickup'."},
                    "top_k": {"type": "integer", "description": "Max sections to return (default 5)."},
                },
                "required": ["query"],
            },
            handler=search_documents,
        )
    )
    registry.register(
        Tool(
            name="get_document",
            description="Read the full text of a specific document by doc_id (e.g. 'cancellation_sop_v4', 'northstar_agreement').",
            parameters={
                "type": "object",
                "properties": {"doc_id": {"type": "string"}},
                "required": ["doc_id"],
            },
            handler=get_document,
        )
    )
