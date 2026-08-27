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

    No ``is_deleted`` clause: page deletion is a hard ``delete_one`` on the
    read model (see ``MongoReadModelMaterializer.delete_page``), not a soft
    flag, so a deleted page is already absent from the collection — there is
    nothing to filter.
    """
    query: dict = {"workspace_id": str(workspace_id)}

    if only_reviewed:
        query["human_corrections.compound_mentions"] = {"$exists": True}
        if since is not None:
            # Stored as `.isoformat()` by the projector (a string, not a BSON
            # date — see page_projector.py's human_correction_recorded), so
            # comparing must use the string form too. ISO-8601 sorts
            # lexicographically in timestamp order, so `$gte` on the string
            # is correct. Do NOT "fix" this back to a raw datetime: Mongo
            # never equates a date to a string, so that silently matches
            # nothing.
            query["human_corrections.compound_mentions.corrected_at"] = {
                "$gte": since.isoformat(),
            }
    else:
        # Bootstrapping: machine output too. Explicitly NOT ground truth.
        query["compound_mentions"] = {"$exists": True, "$ne": []}

    return query
