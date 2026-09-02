"""Shared utilities for the chat/RAG pipeline."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.dtos.chat_dtos import ChatMessageDTO
    from infrastructure.chat.models import SmilesContext

CITATION_RE = re.compile(r"\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")

# Heuristic: sentences that are likely factual claims (contain numbers, units, names)
_FACTUAL_INDICATORS = re.compile(
    r"(\d+\.?\d*\s*(uM|nM|mM|mg|kg|%|IC50|EC50|Ki|Kd|μM|μg|mol))"
    r"|(\b(was|is|are|were|found|showed|demonstrated|reported|measured|determined)\b)",
    re.IGNORECASE,
)

# A citation trailing its sentence — "…0.19 µM. [2]" — splits off as a fragment
# of its own, which the length filter below would then discard, leaving the claim
# it supports counted as uncited. Merge such fragments back into the sentence
# they belong to. Done after the split rather than by rewriting the answer: the
# boundaries are already decided here, so this cannot create or destroy one, and
# cannot drag a citation backward across an abbreviation's period the way a
# text-level substitution does.
#
# Only a citation isolated as its OWN fragment gets rescued this way. A citation
# trailing the middle of a multi-sentence answer stays glued to the sentence that
# follows it instead — an accepted undercount, pinned by
# test_a_mid_answer_trailing_citation_is_not_attributed_backwards. Pulling a
# leading citation run back onto the previous fragment would rescue that shape
# too, but it also reintroduces the abbreviation regression ("…, i.e. [1]
# Compound 44 …"), since a fragment boundary made by an abbreviation's period is
# indistinguishable from a real one at this layer. The undercount is the safe
# direction: it can only trigger more verification than needed, never less.
_CITATION_ONLY = re.compile(r"(?:\[\d{1,2}(?:\s*,\s*\d{1,2})*\]\s*)+")


def compute_citation_coverage(answer: str) -> dict[str, int | float]:
    """Parse answer, classify sentences, compute coverage ratio."""
    # Split into sentences (rough but effective)
    split = re.split(r"(?<=[.!?])\s+", answer.strip())

    merged: list[str] = []
    for fragment in split:
        stripped = fragment.strip()
        if merged and _CITATION_ONLY.fullmatch(stripped):
            merged[-1] = f"{merged[-1]} {stripped}"
        else:
            merged.append(fragment)

    sentences = [s.strip() for s in merged if len(s.strip()) > 10]

    factual_sentences = 0
    cited_sentences = 0

    for sentence in sentences:
        # Skip headers, list markers, introductory phrases
        if sentence.startswith("#") or sentence.startswith("-") or sentence.startswith("*"):
            continue
        if sentence.endswith(":"):
            continue

        is_factual = bool(_FACTUAL_INDICATORS.search(sentence))
        has_citation = bool(CITATION_RE.search(sentence))

        if is_factual:
            factual_sentences += 1
            if has_citation:
                cited_sentences += 1

    ratio = cited_sentences / factual_sentences if factual_sentences > 0 else 1.0

    return {
        "total_sentences": len(sentences),
        "factual_sentences": factual_sentences,
        "cited_sentences": cited_sentences,
        "ratio": ratio,
    }


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
