"""Block-aware chunking: keep tables intact, bind headings to their content,
cap size at block boundaries. Pure (no models, no IO). Falls back to a naive
char split only for a single oversized block.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from application.dtos.parsed_document import Block, _table_to_markdown, linearize_blocks


@dataclass
class BlockChunk:
    text: str
    block_type: str
    section_path: list[str] = field(default_factory=list)
    is_table: bool = False
    is_figure: bool = False
    caption: str | None = None


def _char_split(text: str, max_chars: int) -> list[str]:
    # ponytail: naive slice for the rare single-block overflow; upgrade to a
    # sentence-aware splitter only if oversized prose blocks prove common.
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def _table_group_chunk(header: list[str], rows: list[list[str]], b: Block) -> BlockChunk:
    md = _table_to_markdown([header, *rows])
    text = f"{md}\n\n*{b.caption}*" if b.caption else md
    return BlockChunk(
        text=text, block_type="table", section_path=b.section_path,
        is_table=True, caption=b.caption,
    )


def _table_chunks(b: Block, max_chars: int) -> list[BlockChunk]:
    rows = b.rows or []
    if not rows:
        if b.caption:
            return [BlockChunk(text=b.caption, block_type="table",
                               section_path=b.section_path, is_table=True, caption=b.caption)]
        return []
    header, body = rows[0], rows[1:]
    full = _table_to_markdown(rows)
    if len(full) <= max_chars or not body:
        return [_table_group_chunk(header, body, b)]
    # split body rows into header-prefixed groups under max_chars
    out: list[BlockChunk] = []
    group: list[list[str]] = []
    for row in body:
        group.append(row)
        if len(_table_to_markdown([header, *group])) > max_chars and len(group) > 1:
            group.pop()
            out.append(_table_group_chunk(header, group, b))
            group = [row]
    if group:
        out.append(_table_group_chunk(header, group, b))
    return out


def chunk_blocks(blocks: list[Block], *, max_chars: int = 1000) -> list[BlockChunk]:
    chunks: list[BlockChunk] = []
    buf: list[Block] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        text = linearize_blocks(buf)
        if text.strip():
            chunks.append(BlockChunk(
                text=text, block_type=buf[0].type, section_path=buf[0].section_path,
            ))
        buf, buf_len = [], 0

    for b in blocks:
        if b.type == "table":
            flush()
            chunks.extend(_table_chunks(b, max_chars))
        elif b.type == "figure":
            flush()
            cap = b.caption or ""
            chunks.append(BlockChunk(
                text=f"[Figure: {cap}]" if cap else "[Figure]",
                block_type="figure", section_path=b.section_path,
                is_figure=True, caption=b.caption or None,
            ))
        elif b.type == "heading":
            flush()  # a heading starts a fresh chunk and binds following content
            buf, buf_len = [b], len(b.text)
        else:
            piece = b.text or ""
            if not piece:
                continue
            if len(piece) > max_chars:
                flush()
                for sub in _char_split(piece, max_chars):
                    chunks.append(BlockChunk(
                        text=sub, block_type=b.type, section_path=b.section_path,
                    ))
                continue
            if buf and buf_len + len(piece) > max_chars:
                flush()
            buf.append(b)
            buf_len += len(piece)
    flush()
    return chunks


def chunk_payload(c: BlockChunk) -> dict:
    """Qdrant per-chunk payload for a BlockChunk. Single source of truth for
    the structure-signal keys — imported by both embed paths so they never drift.
    """
    payload: dict = {
        "block_type": c.block_type,
        "is_table": c.is_table,
        "is_figure": c.is_figure,
        "section_path": c.section_path,
        "section_path_normalized": [s.lower() for s in c.section_path],
    }
    if c.caption:
        payload["caption"] = c.caption
    return payload


def scope_table_entities(
    candidates: list[tuple[str, str | None]],
    local_text: str,
) -> dict:
    """Scope a table chunk's entity tags to entities that actually appear in the
    table's own local text (caption / section / headers / cells), instead of the
    page-wide NER union. A candidate is kept only if its surface form occurs in
    local_text on a word boundary (case-insensitive) — so 'rho' does not match
    'rhodamine'. Returns {tags, tag_normalized, entity_types}; empty lists when
    nothing matches (precision over recall: a wrong target tag pollutes chat, a
    missing one degrades to doc-level + vector match). Pure: no IO, no models.
    """
    low = local_text.lower()
    tags: list[str] = []
    tag_normalized: list[str] = []
    entity_types: set[str] = set()
    seen: set[str] = set()
    for tag, entity_type in candidates:
        norm = tag.lower()
        if not norm:
            continue
        if not re.search(r"\b" + re.escape(norm) + r"\b", low):
            continue
        if norm not in seen:
            seen.add(norm)
            tags.append(tag)
            tag_normalized.append(norm)
        if entity_type:
            entity_types.add(entity_type)
    return {
        "tags": tags,
        "tag_normalized": tag_normalized,
        "entity_types": sorted(entity_types),
    }
