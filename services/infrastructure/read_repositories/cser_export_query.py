"""Query filter for the CSER training export.

Split out from the Mongo adapter so the filter — the part with actual logic —
is testable without a database.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID


def build_cser_export_query(
    workspace_id: UUID,
    *,
    only_reviewed: bool,
    since: datetime | None,
) -> dict:
    """Build the Mongo filter for pages to include in a training export.

    ``only_reviewed`` keys on the correction EXISTING, never on the mentions
    themselves: a page a human corrected to an empty list is a reviewed
    negative, and filtering it out would quietly drop the examples that teach
    the detector where structures are not.
    """
    query: dict = {"workspace_id": str(workspace_id), "is_deleted": {"$ne": True}}

    if only_reviewed:
        query["human_corrections.compound_mentions"] = {"$exists": True}
        if since is not None:
            query["human_corrections.compound_mentions.corrected_at"] = {"$gte": since}
    else:
        # Bootstrapping: machine output too. Explicitly NOT ground truth.
        query["compound_mentions"] = {"$exists": True, "$ne": []}

    return query
