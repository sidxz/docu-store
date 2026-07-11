"""Compound-label reconciliation backfill + blast-radius measurement.

Reconciles CSER-extracted compound labels against each document's own NER
compound_name tags, per artifact, via ReconcileCompoundLabelsUseCase. The fix is
applied at the aggregate source, so the running Temporal + read workers re-derive
BOTH the Mongo read model and the Qdrant compound vectors. No CSER, no GPU —
re-extraction is deliberately NOT used (deterministic OCR reproduces the same
wrong label).

--dry-run is the DEFAULT: it reports how many labels would change, by confusion
class, and writes NOTHING. Pass --apply to perform the reconciliation (requires
the workers running to propagate the emitted events, same as production).

Usage:
    uv run python scripts/reconcile_compound_labels.py                 # dry-run, all artifacts
    uv run python scripts/reconcile_compound_labels.py --apply         # apply, all artifacts
    uv run python scripts/reconcile_compound_labels.py <artifact_id>   # dry-run, one artifact
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from uuid import UUID

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from returns.result import Success

from application.use_cases.reconcile_compound_labels_use_case import (
    ReconcileCompoundLabelsUseCase,
)
from infrastructure.config import settings
from infrastructure.di.container import create_container

logger = structlog.get_logger()


def classify_change(before: str, after: str) -> str:
    """Human-readable glyph-swap class for the dry-run report, e.g. 'O->0'."""
    b = before.strip().upper().replace("-", "").replace(" ", "")
    a = after.strip().upper().replace("-", "").replace(" ", "")
    if len(b) != len(a):
        return "format/length"
    swaps = sorted({f"{x}->{y}" for x, y in zip(b, a, strict=False) if x != y})
    return ",".join(swaps) or "identical"


async def _artifact_names_and_pages(db, artifact_id: UUID) -> tuple[list[str], list[UUID]]:
    """Per-artifact candidate names (NER compound_name tags, all pages) and the
    page_ids that carry compound_mentions — read from page_read_models.
    """
    names: list[str] = []
    page_ids: list[UUID] = []
    cursor = db[settings.mongo_pages_collection].find(
        {"artifact_id": str(artifact_id)},
        {"page_id": 1, "compound_mentions": 1, "tag_mentions": 1, "_id": 0},
    )
    async for doc in cursor:
        for tm in doc.get("tag_mentions") or []:
            if tm.get("entity_type") == "compound_name" and tm.get("tag"):
                names.append(tm["tag"])
        if doc.get("compound_mentions"):
            page_ids.append(UUID(doc["page_id"]))
    return names, page_ids


async def run(artifact_ids: list[str] | None, apply: bool) -> None:
    container = create_container()
    reconcile_uc = container[ReconcileCompoundLabelsUseCase]
    mongo = AsyncIOMotorClient(settings.mongo_uri)
    db = mongo[settings.mongo_db]

    try:
        if artifact_ids:
            ids = [UUID(a) for a in artifact_ids]
        else:
            ids = [
                UUID(doc.get("artifact_id") or str(doc["_id"]))
                async for doc in db[settings.mongo_artifacts_collection].find(
                    {}, {"_id": 1, "artifact_id": 1},
                )
            ]

        report: Counter[str] = Counter()
        total_changed = 0
        for aid in ids:
            names, page_ids = await _artifact_names_and_pages(db, aid)
            if not names or not page_ids:
                continue
            for pid in page_ids:
                result = await reconcile_uc.execute(
                    pid, candidate_names=names, dry_run=not apply,
                )
                if not isinstance(result, Success):
                    logger.warning("reconcile_failed", artifact_id=str(aid), page_id=str(pid))
                    continue
                dto = result.unwrap()
                for change in dto.changes:
                    report[classify_change(change.before, change.after)] += 1
                    total_changed += 1
                    logger.info(
                        "reconcile_change",
                        artifact_id=str(aid),
                        page_id=str(pid),
                        before=change.before,
                        after=change.after,
                        applied=dto.applied,
                    )

        mode = "APPLIED" if apply else "DRY-RUN (no writes)"
        logger.info(
            "reconcile_summary",
            mode=mode,
            total_changed=total_changed,
            by_class=dict(report.most_common()),
        )
    finally:
        mongo.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_ids", nargs="*", help="Artifact IDs (default: all artifacts)")
    parser.add_argument(
        "--apply", action="store_true", help="Apply changes (default: dry-run, no writes)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.artifact_ids or None, apply=args.apply))
