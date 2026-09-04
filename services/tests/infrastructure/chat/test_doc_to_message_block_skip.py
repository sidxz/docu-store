"""A stored content block that no longer validates must not sink the message.

Content blocks with a chart.panel value that was later removed from the
Literal (e.g. an old "provenance" panel) fail ContentBlockDTO validation.
_doc_to_message must skip that one block, not raise and 500 the whole
recent-conversations list.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from infrastructure.chat.mongo_chat_repository import _doc_to_message


def _base_doc(structured_content: list[dict]) -> dict:
    return {
        "conversation_id": str(uuid4()),
        "message_id": str(uuid4()),
        "role": "assistant",
        "content": "hi",
        "structured_content": structured_content,
        "created_at": datetime(2026, 7, 1, tzinfo=UTC),
    }


def test_invalid_chart_block_is_skipped_valid_block_kept():
    valid_table = {"type": "table", "headers": ["a"], "rows": [["1"]]}
    invalid_chart = {
        "type": "chart",
        "chart": {
            "panel": "provenance",
            "title": "x",
            "x_label": "",
            "y_label": "",
            "series": [],
        },
    }
    doc = _base_doc([valid_table, invalid_chart])

    message = _doc_to_message(doc)

    assert message.structured_content is not None
    assert len(message.structured_content) == 1
    assert message.structured_content[0].type == "table"


def test_all_blocks_invalid_yields_none():
    invalid_chart = {
        "type": "chart",
        "chart": {"panel": "provenance", "title": "x", "x_label": "", "y_label": "", "series": []},
    }
    doc = _base_doc([invalid_chart])

    message = _doc_to_message(doc)

    assert message.structured_content is None
