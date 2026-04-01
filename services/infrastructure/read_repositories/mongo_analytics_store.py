"""MongoDB adapter for AnalyticsReadModel port."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.stats_dtos import (
    ChatLatencyStatsResponse,
    CitationFrequencyResponse,
    CitedArtifactEntry,
    GroundingBucket,
    GroundingStatsResponse,
    KnowledgeGapEntry,
    KnowledgeGapsResponse,
    SearchQualityStats,
    SearchQualityStatsResponse,
    StepLatencyStats,
    TokenUsageBucket,
    TokenUsageStatsResponse,
    UncitedArtifactEntry,
)


class MongoAnalyticsStore:
    """Aggregation queries over chat_messages and user_activity collections."""

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        artifacts_collection_name: str,
    ) -> None:
        self._db = client[db_name]
        self._artifacts_collection_name = artifacts_collection_name

    async def _conversation_ids_for_workspace(self, workspace_id: UUID) -> list[str]:
        """Pre-fetch conversation IDs belonging to a workspace."""
        return await self._db["conversations"].distinct(
            "conversation_id",
            {"workspace_id": str(workspace_id)},
        )

    def _workspace_match_for_messages(
        self,
        base_match: dict,
        conv_ids: list[str] | None,
    ) -> dict:
        """Merge a conversation_id filter into an existing $match dict."""
        if conv_ids is not None:
            return {**base_match, "conversation_id": {"$in": conv_ids}}
        return base_match

    async def get_token_usage(
        self,
        period_days: int,
        *,
        workspace_id: UUID | None = None,
    ) -> TokenUsageStatsResponse:
        since = datetime.now(UTC) - timedelta(days=period_days)

        conv_ids = (
            await self._conversation_ids_for_workspace(workspace_id) if workspace_id else None
        )

        match = self._workspace_match_for_messages(
            {"role": "assistant", "created_at": {"$gte": since}},
            conv_ids,
        )

        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {
                        "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                        "mode": {"$ifNull": ["$query_context.query_type", "unknown"]},
                    },
                    "total_tokens": {"$sum": {"$ifNull": ["$token_usage.total", 0]}},
                    "prompt_tokens": {"$sum": {"$ifNull": ["$token_usage.prompt", 0]}},
                    "completion_tokens": {"$sum": {"$ifNull": ["$token_usage.completion", 0]}},
                    "message_count": {"$sum": 1},
                },
            },
            {"$sort": {"_id.date": 1}},
        ]

        cursor = self._db["chat_messages"].aggregate(pipeline)
        results = await cursor.to_list(length=500)

        buckets = [
            TokenUsageBucket(
                date=r["_id"]["date"],
                mode=r["_id"]["mode"],
                total_tokens=r["total_tokens"],
                prompt_tokens=r["prompt_tokens"],
                completion_tokens=r["completion_tokens"],
                message_count=r["message_count"],
            )
            for r in results
        ]

        total_tokens = sum(b.total_tokens for b in buckets)
        total_messages = sum(b.message_count for b in buckets)

        return TokenUsageStatsResponse(
            buckets=buckets,
            total_tokens=total_tokens,
            total_messages=total_messages,
        )

    async def get_chat_latency(
        self,
        period_days: int,
        *,
        workspace_id: UUID | None = None,
    ) -> ChatLatencyStatsResponse:
        since = datetime.now(UTC) - timedelta(days=period_days)

        conv_ids = (
            await self._conversation_ids_for_workspace(workspace_id) if workspace_id else None
        )

        match = self._workspace_match_for_messages(
            {"role": "assistant", "created_at": {"$gte": since}, "agent_trace": {"$ne": None}},
            conv_ids,
        )

        pipeline = [
            {"$match": match},
            {"$unwind": "$agent_trace.steps"},
            {
                "$project": {
                    "step_name": "$agent_trace.steps.step",
                    "duration_ms": {
                        "$cond": {
                            "if": {
                                "$and": [
                                    {"$ne": ["$agent_trace.steps.started_at", None]},
                                    {"$ne": ["$agent_trace.steps.completed_at", None]},
                                ],
                            },
                            "then": {
                                "$subtract": [
                                    {
                                        "$toLong": {
                                            "$dateFromString": {
                                                "dateString": "$agent_trace.steps.completed_at",
                                                "onError": None,
                                            },
                                        },
                                    },
                                    {
                                        "$toLong": {
                                            "$dateFromString": {
                                                "dateString": "$agent_trace.steps.started_at",
                                                "onError": None,
                                            },
                                        },
                                    },
                                ],
                            },
                            "else": None,
                        },
                    },
                },
            },
            {"$match": {"duration_ms": {"$ne": None, "$gt": 0}}},
            {
                "$group": {
                    "_id": "$step_name",
                    "durations": {"$push": "$duration_ms"},
                    "count": {"$sum": 1},
                    "avg_ms": {"$avg": "$duration_ms"},
                    "max_ms": {"$max": "$duration_ms"},
                },
            },
            {"$sort": {"count": -1}},
        ]

        cursor = self._db["chat_messages"].aggregate(pipeline)
        results = await cursor.to_list(length=50)

        steps: list[StepLatencyStats] = []
        all_durations: list[float] = []
        for r in results:
            durations = sorted(r["durations"])
            count = len(durations)
            p50 = durations[count // 2] if count else 0
            p95 = durations[int(count * 0.95)] if count else 0
            steps.append(
                StepLatencyStats(
                    step_name=r["_id"] or "unknown",
                    count=count,
                    avg_ms=round(r["avg_ms"], 1),
                    p50_ms=round(p50, 1),
                    p95_ms=round(p95, 1),
                    max_ms=round(r["max_ms"], 1),
                ),
            )
            all_durations.extend(durations)

        all_durations.sort()
        total = len(all_durations)

        return ChatLatencyStatsResponse(
            steps=steps,
            overall_avg_ms=round(sum(all_durations) / total, 1) if total else 0,
            overall_p95_ms=round(all_durations[int(total * 0.95)], 1) if total else 0,
        )

    async def get_search_quality(
        self,
        period_days: int,
        *,
        workspace_id: UUID | None = None,
    ) -> SearchQualityStatsResponse:
        since = datetime.now(UTC) - timedelta(days=period_days)

        # user_activity stores workspace_id directly
        base_match: dict = {"type": "search", "created_at": {"$gte": since}}
        if workspace_id:
            base_match["workspace_id"] = str(workspace_id)

        pipeline = [
            {"$match": base_match},
            {
                "$group": {
                    "_id": "$search_mode",
                    "total_searches": {"$sum": 1},
                    "zero_result_count": {
                        "$sum": {"$cond": [{"$eq": [{"$ifNull": ["$result_count", 1]}, 0]}, 1, 0]},
                    },
                    "total_results": {"$sum": {"$ifNull": ["$result_count", 0]}},
                },
            },
        ]

        cursor = self._db["user_activity"].aggregate(pipeline)
        results = await cursor.to_list(length=20)

        modes: list[SearchQualityStats] = []
        grand_total = 0
        grand_zero = 0
        for r in results:
            total = r["total_searches"]
            zero = r["zero_result_count"]
            grand_total += total
            grand_zero += zero
            modes.append(
                SearchQualityStats(
                    search_mode=r["_id"] or "unknown",
                    total_searches=total,
                    zero_result_count=zero,
                    zero_result_rate=round(zero / total, 3) if total else 0,
                    avg_result_count=round(r["total_results"] / total, 1) if total else 0,
                ),
            )

        return SearchQualityStatsResponse(
            modes=modes,
            total_searches=grand_total,
            overall_zero_result_rate=round(grand_zero / grand_total, 3) if grand_total else 0,
        )

    async def get_grounding_stats(
        self,
        period_days: int,
        *,
        workspace_id: UUID | None = None,
    ) -> GroundingStatsResponse:
        since = datetime.now(UTC) - timedelta(days=period_days)

        conv_ids = (
            await self._conversation_ids_for_workspace(workspace_id) if workspace_id else None
        )

        base_match: dict = {
            "role": "assistant",
            "created_at": {"$gte": since},
            "agent_trace.grounding_confidence": {"$ne": None},
        }
        match = self._workspace_match_for_messages(base_match, conv_ids)

        pipeline = [
            {"$match": match},
            {
                "$group": {
                    "_id": {"$ifNull": ["$query_context.query_type", "unknown"]},
                    "total": {"$sum": 1},
                    "grounded": {
                        "$sum": {
                            "$cond": [{"$eq": ["$agent_trace.grounding_is_grounded", True]}, 1, 0],
                        },
                    },
                    "not_grounded": {
                        "$sum": {
                            "$cond": [{"$ne": ["$agent_trace.grounding_is_grounded", True]}, 1, 0],
                        },
                    },
                    "avg_confidence": {"$avg": "$agent_trace.grounding_confidence"},
                },
            },
        ]

        cursor = self._db["chat_messages"].aggregate(pipeline)
        results = await cursor.to_list(length=20)

        modes: list[GroundingBucket] = []
        grand_total = 0
        grand_grounded = 0
        total_confidence = 0.0
        for r in results:
            total = r["total"]
            grounded = r["grounded"]
            grand_total += total
            grand_grounded += grounded
            total_confidence += r["avg_confidence"] * total
            modes.append(
                GroundingBucket(
                    mode=r["_id"],
                    total_messages=total,
                    grounded_count=grounded,
                    not_grounded_count=r["not_grounded"],
                    grounded_rate=round(grounded / total, 3) if total else 0,
                    avg_confidence=round(r["avg_confidence"], 3),
                ),
            )

        return GroundingStatsResponse(
            modes=modes,
            overall_grounded_rate=round(grand_grounded / grand_total, 3) if grand_total else 0,
            overall_avg_confidence=round(total_confidence / grand_total, 3) if grand_total else 0,
        )

    async def get_knowledge_gaps(
        self,
        period_days: int,
        *,
        workspace_id: UUID | None = None,
    ) -> KnowledgeGapsResponse:
        since = datetime.now(UTC) - timedelta(days=period_days)

        conv_ids = (
            await self._conversation_ids_for_workspace(workspace_id) if workspace_id else None
        )

        base_match: dict = {
            "role": "assistant",
            "created_at": {"$gte": since},
            "query_context.ner_entities.0": {"$exists": True},
        }
        match = self._workspace_match_for_messages(base_match, conv_ids)

        pipeline = [
            # Assistant messages with NER entities detected in the query
            {"$match": match},
            # Flag "gap" messages: no sources or answer not grounded
            {
                "$addFields": {
                    "_is_gap": {
                        "$or": [
                            {"$eq": [{"$size": {"$ifNull": ["$sources", []]}}, 0]},
                            {"$eq": ["$agent_trace.grounding_is_grounded", False]},
                        ],
                    },
                },
            },
            {"$unwind": "$query_context.ner_entities"},
            {
                "$group": {
                    "_id": {
                        "text": {"$toLower": "$query_context.ner_entities.entity_text"},
                        "type": "$query_context.ner_entities.entity_type",
                    },
                    "query_count": {"$sum": 1},
                    "gap_count": {"$sum": {"$cond": ["$_is_gap", 1, 0]}},
                    "display_text": {"$first": "$query_context.ner_entities.entity_text"},
                },
            },
            {"$match": {"gap_count": {"$gt": 0}}},
            {"$sort": {"gap_count": -1, "query_count": -1}},
            {"$limit": 30},
        ]

        cursor = self._db["chat_messages"].aggregate(pipeline)
        results = await cursor.to_list(length=30)

        gaps = [
            KnowledgeGapEntry(
                entity_text=r["display_text"],
                entity_type=r["_id"]["type"] or "unknown",
                query_count=r["query_count"],
                gap_count=r["gap_count"],
                gap_rate=round(r["gap_count"] / r["query_count"], 3) if r["query_count"] else 0,
            )
            for r in results
        ]

        # Count total unique entities in period (for context)
        count_pipeline = [
            {"$match": match},
            {"$unwind": "$query_context.ner_entities"},
            {"$group": {"_id": {"$toLower": "$query_context.ner_entities.entity_text"}}},
            {"$count": "total"},
        ]
        count_result = await self._db["chat_messages"].aggregate(count_pipeline).to_list(length=1)
        total_unique = count_result[0]["total"] if count_result else 0

        return KnowledgeGapsResponse(
            gaps=gaps,
            total_unique_entities=total_unique,
            total_gap_entities=len(gaps),
        )

    async def get_citation_frequency(
        self,
        period_days: int,
        *,
        workspace_id: UUID | None = None,
    ) -> CitationFrequencyResponse:
        since = datetime.now(UTC) - timedelta(days=period_days)

        conv_ids = (
            await self._conversation_ids_for_workspace(workspace_id) if workspace_id else None
        )

        match = self._workspace_match_for_messages(
            {"role": "assistant", "created_at": {"$gte": since}, "sources.0": {"$exists": True}},
            conv_ids,
        )

        pipeline = [
            {"$match": match},
            {"$unwind": "$sources"},
            {
                "$group": {
                    "_id": "$sources.artifact_id",
                    "artifact_title": {"$max": "$sources.artifact_title"},
                    "citation_count": {"$sum": 1},
                    "unique_conversations": {"$addToSet": "$conversation_id"},
                },
            },
            {
                "$addFields": {
                    "unique_conversation_count": {"$size": "$unique_conversations"},
                },
            },
            {
                "$project": {
                    "artifact_title": 1,
                    "citation_count": 1,
                    "unique_conversation_count": 1,
                },
            },
            {"$sort": {"citation_count": -1}},
        ]

        cursor = self._db["chat_messages"].aggregate(pipeline)
        all_cited = await cursor.to_list(length=500)

        cited_entries = [
            CitedArtifactEntry(
                artifact_id=r["_id"],
                artifact_title=r["artifact_title"],
                citation_count=r["citation_count"],
                unique_conversation_count=r["unique_conversation_count"],
            )
            for r in all_cited
        ]

        most_cited = cited_entries[:10]
        least_cited = list(reversed(cited_entries[-10:])) if len(cited_entries) > 10 else []

        # Find never-cited artifacts by comparing against the artifacts read model
        cited_ids = {r["_id"] for r in all_cited}
        artifacts_coll = self._db[self._artifacts_collection_name]

        artifacts_filter: dict = {"artifact_id": {"$nin": list(cited_ids)}}
        if workspace_id:
            artifacts_filter["workspace_id"] = str(workspace_id)

        total_artifacts = await artifacts_coll.count_documents(
            {"workspace_id": str(workspace_id)} if workspace_id else {},
        )

        never_cited_cursor = artifacts_coll.find(
            artifacts_filter,
            {"artifact_id": 1, "title_mention.title": 1, "source_filename": 1, "_id": 0},
        ).limit(20)
        never_cited = [
            UncitedArtifactEntry(
                artifact_id=doc["artifact_id"],
                artifact_title=(
                    (doc.get("title_mention") or {}).get("title") or doc.get("source_filename")
                ),
            )
            async for doc in never_cited_cursor
        ]

        return CitationFrequencyResponse(
            most_cited=most_cited,
            least_cited=least_cited,
            never_cited=never_cited,
            never_cited_count=max(0, total_artifacts - len(cited_entries)),
            total_artifacts=total_artifacts,
        )
