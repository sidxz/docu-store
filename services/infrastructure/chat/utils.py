"""Shared utilities for the chat/RAG pipeline."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.dtos.chat_dtos import ChatMessageDTO
    from infrastructure.chat.models import SmilesContext

CITATION_RE = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")


def extract_cited_indices(answer: str) -> set[int]:
    """Extract the set of citation indices actually used in the answer text."""
    indices: set[int] = set()
    for group in CITATION_RE.findall(answer):
        for part in group.split(","):
            indices.add(int(part.strip()))
    return indices


def build_conversation_context(
    history: list[ChatMessageDTO],
    max_chars: int = 300,
) -> str:
    """Build a concise context string from recent conversation history."""
    if not history:
        return ""
    lines = []
    for msg in history[-6:]:
        role = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role}: {msg.content[:max_chars]}")
    return "\n".join(lines)


def build_follow_up_context(
    history: list[ChatMessageDTO],
    budget: int | None = None,
) -> str:
    """Build a richer context string from recent conversation history.

    Allocates budget per message pair, with the most recent pair getting 2x share.
    User messages get full text; assistant messages get truncated text + citation
    summary + query_context summary.
    """
    from infrastructure.config import settings

    if not history:
        return ""

    total_budget = budget or settings.chat_follow_up_context_budget

    # Collect recent pairs (user + assistant)
    recent = history[-10:]
    pairs: list[tuple[ChatMessageDTO | None, ChatMessageDTO | None]] = []
    i = 0
    while i < len(recent):
        user_msg = recent[i] if recent[i].role == "user" else None
        asst_msg = None
        if user_msg and i + 1 < len(recent) and recent[i + 1].role == "assistant":
            asst_msg = recent[i + 1]
            i += 2
        elif user_msg:
            i += 1
        else:
            # Standalone assistant message
            asst_msg = recent[i]
            i += 1
        pairs.append((user_msg, asst_msg))

    if not pairs:
        return ""

    # Budget allocation: last pair gets 2x
    n_pairs = len(pairs)
    total_shares = n_pairs + 1  # last pair counts as 2
    per_share = total_budget // max(total_shares, 1)

    lines: list[str] = []
    for idx, (user_msg, asst_msg) in enumerate(pairs):
        is_last = idx == n_pairs - 1
        pair_budget = per_share * 2 if is_last else per_share

        if user_msg:
            user_budget = pair_budget // 2 if asst_msg else pair_budget
            lines.append(f"User: {user_msg.content[:user_budget]}")

        if asst_msg:
            asst_budget = pair_budget // 2 if user_msg else pair_budget
            # Truncated content
            content_budget = min(600, asst_budget)
            content_preview = asst_msg.content[:content_budget]
            parts = [f"Assistant: {content_preview}"]

            # Citation summary
            if asst_msg.sources:
                cite_summaries = [
                    f"[{s.citation_index}] {s.artifact_title or 'doc'}"
                    for s in asst_msg.sources[:5]
                ]
                parts.append(f"  Citations: {', '.join(cite_summaries)}")

            # Query context summary
            if asst_msg.query_context:
                qc = asst_msg.query_context
                qc_parts: list[str] = []
                if qc.query_type:
                    qc_parts.append(f"type={qc.query_type}")
                if qc.ner_entities:
                    ent_strs = [e.get("entity_text", "") for e in qc.ner_entities[:5]]
                    qc_parts.append(f"entities=[{', '.join(ent_strs)}]")
                if qc.authors:
                    qc_parts.append(f"authors=[{', '.join(qc.authors[:3])}]")
                if qc_parts:
                    parts.append(f"  Context: {'; '.join(qc_parts)}")

            lines.append("\n".join(parts))

    result = "\n".join(lines)

    if settings.chat_debug:
        import structlog

        _log = structlog.get_logger("infrastructure.chat.utils")
        grounded_count = sum(
            1
            for m in history
            if m.role == "assistant" and m.query_context and m.query_context.grounded
        )
        _log.info(
            "chat.debug.follow_up_context",
            history_len=len(history),
            pairs=len(pairs),
            grounded_msgs=grounded_count,
            context_chars=len(result),
            budget=total_budget,
        )

    return result


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences wrapping JSON output from LLMs."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.removesuffix("```")
        cleaned = cleaned.strip()
    return cleaned


def replace_smiles_with_names(
    text: str,
    smiles_ctx: SmilesContext | None,
) -> str:
    """Replace raw SMILES strings in text with resolved compound names.

    Uses detected_originals (user-typed forms) for matching and replaces
    with the primary extracted_id from resolved compounds.
    Falls back to detected (canonical forms) if originals are not available.
    """
    if not smiles_ctx or not smiles_ctx.resolved:
        return text

    # Build mapping: canonical_smiles -> primary compound name
    canonical_to_name: dict[str, str] = {}
    for compound in smiles_ctx.resolved:
        if compound.extracted_ids:
            canonical_to_name[compound.canonical_smiles] = compound.extracted_ids[0]

    if not canonical_to_name:
        return text

    # detected_originals[i] corresponds to detected[i] (canonical)
    originals = smiles_ctx.detected_originals or smiles_ctx.detected
    canonicals = smiles_ctx.detected

    result = text
    for orig, canon in zip(originals, canonicals):
        name = canonical_to_name.get(canon)
        if name:
            result = result.replace(orig, name)
            # Also replace canonical form if different from original
            if canon != orig:
                result = result.replace(canon, name)

    return result
