from enum import StrEnum


class SourceClass(StrEnum):
    """Where a document came from, and so what may be done with it.

    Carried into the Qdrant payload, which is the point: entity ACLs are applied
    upstream as an artifact allowlist that falls back to workspace-wide when the
    permission service is unreachable, whereas a payload filter is evaluated
    inside Qdrant and cannot fail open the same way.
    """

    INTERNAL = "internal"
    LITERATURE_OA = "literature_oa"
