"""One-time backfill: materialize existing chat token usage into the ledger.

Joins conversations (owner/workspace) with their assistant messages'
``token_usage`` and upserts one ``token_usage_events`` doc per message with
``_id = chat:{message_id}`` — the same deterministic id live writes use, so
this is idempotent and safe alongside live traffic.

Usage:
    cd services && uv run python scripts/backfill_chat_token_usage.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import sys

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

from infrastructure.config import settings

logger = structlog.get_logger()


async def backfill(dry_run: bool) -> None:
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db]
    ledger = db[settings.mongo_token_usage_collection]

    upserted = 0
    skipped_no_usage = 0
    async for conv in db["conversations"].find(
        {}, {"conversation_id": 1, "workspace_id": 1, "owner_id": 1},
    ):
        cursor = db["chat_messages"].find(
            {
                "conversation_id": conv["conversation_id"],
                "role": "assistant",
                "token_usage": {"$ne": None},
            },
            {"message_id": 1, "token_usage": 1, "created_at": 1},
        )
        async for msg in cursor:
            tu = msg["token_usage"]
            if not tu.get("total"):
                skipped_no_usage += 1
                continue
            ws = conv.get("workspace_id")
            owner = conv.get("owner_id")
            doc = {
                "_id": f"chat:{msg['message_id']}",
                "workspace_id": str(ws) if ws else None,
                "user_id": str(owner) if owner else None,
                "kind": "chat",
                "source": "chat_message",
                "prompt": int(tu.get("prompt", 0)),
                "completion": int(tu.get("completion", 0)),
                "total": int(tu.get("total", 0)),
                "model": None,
                "ref": str(conv["conversation_id"]),
                "created_at": msg["created_at"],
            }
            if not dry_run:
                await ledger.replace_one({"_id": doc["_id"]}, doc, upsert=True)
            upserted += 1

    logger.info(
        "backfill.chat_token_usage.done",
        upserted=upserted,
        skipped_no_usage=skipped_no_usage,
        dry_run=dry_run,
    )
    client.close()


if __name__ == "__main__":
    asyncio.run(backfill(dry_run="--dry-run" in sys.argv))
