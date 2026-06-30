from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

BlockType = Literal[
    "heading", "paragraph", "list", "table", "figure",
    "caption", "equation", "code", "reference", "footnote", "other",
]


class Block(BaseModel):
    type: BlockType
    text: str = ""
    level: int | None = None             # heading depth
    rows: list[list[str]] | None = None  # table cells
    caption: str | None = None           # figure/table caption
    section_path: list[str] = Field(default_factory=list)  # enclosing heading breadcrumb
    source_page_index: int | None = None


class ParsedDocument(BaseModel):
    """Structure-only IR. JSON-serializable; persisted as a blob. No image bytes."""

    source_mime: str
    blocks: list[Block] = Field(default_factory=list)


@dataclass
class RenderedPage:
    index: int
    png: bytes
    thumb: bytes | None = None


@dataclass
class ParseResult:
    """Parser output: serializable structure + binary page renders (kept separate)."""

    document: ParsedDocument
    pages: list[RenderedPage] = field(default_factory=list)


def _table_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header, *body = rows
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def linearize_blocks(blocks: list[Block]) -> str:
    """Flatten structured blocks into clean markdown text for the (A)-tier pipeline."""
    parts: list[str] = []
    for b in blocks:
        if b.type == "heading":
            parts.append(f"{'#' * (b.level or 1)} {b.text}".strip())
        elif b.type == "table" and b.rows:
            md = _table_to_markdown(b.rows)
            parts.append(f"{md}\n\n*{b.caption}*" if b.caption else md)
        elif b.type == "figure":
            parts.append(f"[Figure: {b.caption}]" if b.caption else "[Figure]")
        elif b.text:
            parts.append(b.text)
    return "\n\n".join(p for p in parts if p)


def assign_section_paths(blocks: list[Block]) -> None:
    """Set each block's section_path from the enclosing heading stack.

    Blocks must be in reading order. A heading's section_path is its ancestor
    headings (excluding itself); a content block's is every enclosing heading
    including the nearest one above it. Headings with no level are treated as
    level 1.
    """
    stack: list[tuple[int, str]] = []  # (level, text)
    for b in blocks:
        if b.type == "heading":
            lvl = b.level or 1
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            b.section_path = [text for _, text in stack]
            stack.append((lvl, b.text))
        else:
            b.section_path = [text for _, text in stack]
