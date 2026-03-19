import time
from datetime import datetime, timezone
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.artifact_dtos import ArtifactResponse
from application.dtos.browse_dtos import (
    ArtifactBrowseItemDTO,
    BrowseCategoriesResponse,
    BrowseFoldersResponse,
    TagCategoryDTO,
    TagFolderDTO,
    TagPageSource,
)
from application.dtos.dashboard_dtos import DashboardStatsResponse
from application.dtos.page_dtos import PageResponse
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.dashboard_read_models import DashboardReadModel
from application.ports.repositories.page_read_models import PageReadModel
from application.ports.repositories.tag_browse_read_model import TagBrowseReadModel
from infrastructure.config import Settings

_dashboard_cache: dict[tuple, tuple[float, DashboardStatsResponse]] = {}
_DASHBOARD_CACHE_TTL = 60.0  # seconds

ENTITY_TYPE_DISPLAY_NAMES: dict[str, str] = {
    "target": "Target",
    "compound_name": "Compound",
    "gene_name": "Gene",
    "screening_method": "Method",
    "author": "Author",
    "date": "Date",
    "accession_number": "Accession",
    "disease": "Disease",
}


class MongoReadRepository(PageReadModel, ArtifactReadModel, DashboardReadModel, TagBrowseReadModel):
    def __init__(self, client: AsyncIOMotorClient, settings: Settings) -> None:
        self.client = client
        self.db = self.client[settings.mongo_db]
        self.pages = self.db[settings.mongo_pages_collection]
        self.artifacts = self.db[settings.mongo_artifacts_collection]

    async def get_page_by_id(
        self,
        page_id: UUID,
        workspace_id: UUID | None = None,
    ) -> PageResponse | None:
        query: dict = {"page_id": str(page_id)}
        if workspace_id is not None:
            query["workspace_id"] = str(workspace_id)
        doc = await self.pages.find_one(query)
        if not doc:
            return None
        # Map MongoDB _id (ObjectId) to page_id field
        doc["page_id"] = doc.get("page_id") or str(doc.pop("_id"))
        return PageResponse(**doc)

    async def get_pages_by_id(
        self,
        page_ids: list[UUID],
        workspace_id: UUID | None = None,
    ) -> list[PageResponse]:
        """Fetch multiple pages by their IDs in a single query."""
        if not page_ids:
            return []

        query: dict = {"page_id": {"$in": [str(pid) for pid in page_ids]}}
        if workspace_id is not None:
            query["workspace_id"] = str(workspace_id)
        cursor = self.pages.find(query)
        pages = []
        async for doc in cursor:
            doc["page_id"] = doc.get("page_id") or str(doc.pop("_id"))
            pages.append(PageResponse(**doc))
        # Sort by index to maintain page order
        pages.sort(key=lambda p: p.index)
        return pages

    async def get_artifact_by_id(
        self,
        artifact_id: UUID,
        workspace_id: UUID | None = None,
    ) -> ArtifactResponse | None:
        query: dict = {"artifact_id": str(artifact_id)}
        if workspace_id is not None:
            query["workspace_id"] = str(workspace_id)
        doc = await self.artifacts.find_one(query)
        if not doc:
            return None
        # Map MongoDB _id (ObjectId) to artifact_id field
        doc["artifact_id"] = doc.get("artifact_id") or str(doc.pop("_id"))
        # Fetch full page objects instead of just IDs
        if doc.get("pages"):
            page_ids = [UUID(page_id) for page_id in doc["pages"]]
            doc["pages"] = await self.get_pages_by_id(page_ids)
        else:
            doc["pages"] = []
        return ArtifactResponse(**doc)

    async def list_artifacts(
        self,
        workspace_id: UUID | None = None,
        skip: int = 0,
        limit: int = 100,
        allowed_artifact_ids: list[UUID] | None = None,
        sort_by: str = "updated_at",
        sort_order: int = -1,
    ) -> list[ArtifactResponse]:
        """List all artifacts with pagination, scoped by workspace and permissions."""
        query = {}
        if workspace_id is not None:
            query["workspace_id"] = str(workspace_id)
        if allowed_artifact_ids is not None:
            query["artifact_id"] = {"$in": [str(aid) for aid in allowed_artifact_ids]}
        cursor = self.artifacts.find(query).sort(sort_by, sort_order).skip(skip).limit(limit)
        artifacts = []
        async for doc in cursor:
            # Map MongoDB _id (ObjectId) to artifact_id field
            doc["artifact_id"] = doc.get("artifact_id") or str(doc.pop("_id"))
            # Convert page IDs from strings to UUIDs
            if doc.get("pages"):
                doc["pages"] = tuple(UUID(page_id) for page_id in doc["pages"])
            else:
                doc["pages"] = ()
            artifacts.append(ArtifactResponse(**doc))
        return artifacts

    # ── DashboardReadModel implementation ────────────────────────────

    async def get_dashboard_stats(
        self,
        workspace_id: UUID | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> DashboardStatsResponse:
        """Aggregate workspace statistics with a short TTL cache."""
        cache_key = (
            str(workspace_id),
            frozenset(str(aid) for aid in allowed_artifact_ids)
            if allowed_artifact_ids is not None
            else None,
        )
        now = time.monotonic()
        cached = _dashboard_cache.get(cache_key)
        if cached and now - cached[0] < _DASHBOARD_CACHE_TTL:
            return cached[1]

        # Build workspace + permission filter (shared with other queries)
        query: dict = {}
        if workspace_id is not None:
            query["workspace_id"] = str(workspace_id)
        if allowed_artifact_ids is not None:
            query["artifact_id"] = {"$in": [str(aid) for aid in allowed_artifact_ids]}

        # Artifact-level stats: count, page total, summary count
        artifact_pipeline: list[dict] = [
            {"$match": query},
            {
                "$group": {
                    "_id": None,
                    "total_artifacts": {"$sum": 1},
                    "total_pages": {
                        "$sum": {"$size": {"$ifNull": ["$pages", []]}},
                    },
                    "with_summary": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$ne": [{"$ifNull": ["$summary_candidate.summary", None]}, None]},
                                        {"$ne": ["$summary_candidate.summary", ""]},
                                    ],
                                },
                                1,
                                0,
                            ],
                        },
                    },
                },
            },
        ]
        artifact_result = await self.artifacts.aggregate(artifact_pipeline).to_list(1)
        artifact_stats = artifact_result[0] if artifact_result else {}

        # Page-level stats: compound mention count (pages have workspace_id)
        page_query: dict = {}
        if workspace_id is not None:
            page_query["workspace_id"] = str(workspace_id)
        if allowed_artifact_ids is not None:
            page_query["artifact_id"] = {"$in": [str(aid) for aid in allowed_artifact_ids]}

        compound_pipeline: list[dict] = [
            {"$match": page_query},
            {
                "$group": {
                    "_id": None,
                    "total_compounds": {
                        "$sum": {"$size": {"$ifNull": ["$compound_mentions", []]}},
                    },
                },
            },
        ]
        compound_result = await self.pages.aggregate(compound_pipeline).to_list(1)
        compound_stats = compound_result[0] if compound_result else {}

        stats = DashboardStatsResponse(
            total_artifacts=artifact_stats.get("total_artifacts", 0),
            total_pages=artifact_stats.get("total_pages", 0),
            total_compounds=compound_stats.get("total_compounds", 0),
            with_summary=artifact_stats.get("with_summary", 0),
        )
        _dashboard_cache[cache_key] = (now, stats)
        return stats

    # ── TagBrowseReadModel implementation ────────────────────────────

    def _browse_base_match(
        self,
        workspace_id: UUID | None,
        allowed_artifact_ids: list[UUID] | None,
    ) -> dict:
        """Build the common $match stage for workspace + permission filtering."""
        match: dict = {}
        if workspace_id is not None:
            match["workspace_id"] = str(workspace_id)
        if allowed_artifact_ids is not None:
            match["artifact_id"] = {"$in": [str(aid) for aid in allowed_artifact_ids]}
        return match

    async def get_tag_categories(
        self,
        workspace_id: UUID | None = None,
        limit: int = 5,
        sticky_categories: list[str] | None = None,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> BrowseCategoriesResponse:
        base_match = self._browse_base_match(workspace_id, allowed_artifact_ids)

        pipeline: list[dict] = []
        if base_match:
            pipeline.append({"$match": base_match})

        pipeline.append(
            {
                "$facet": {
                    # Branch 1: tag_mentions grouped by entity_type
                    "tag_mentions": [
                        {"$unwind": "$tag_mentions"},
                        {"$match": {"tag_mentions.entity_type": {"$ne": None}}},
                        {
                            "$group": {
                                "_id": "$tag_mentions.entity_type",
                                "artifact_ids": {"$addToSet": "$artifact_id"},
                                "distinct_tags": {
                                    "$addToSet": {"$toLower": "$tag_mentions.tag"},
                                },
                            },
                        },
                        {
                            "$project": {
                                "entity_type": "$_id",
                                "artifact_count": {"$size": "$artifact_ids"},
                                "distinct_count": {"$size": "$distinct_tags"},
                            },
                        },
                    ],
                    # Branch 2: authors
                    "authors": [
                        {"$match": {"author_mentions.0": {"$exists": True}}},
                        {"$unwind": "$author_mentions"},
                        {
                            "$group": {
                                "_id": None,
                                "artifact_ids": {"$addToSet": "$artifact_id"},
                                "distinct_names": {
                                    "$addToSet": {"$toLower": "$author_mentions.name"},
                                },
                            },
                        },
                        {
                            "$project": {
                                "artifact_count": {"$size": "$artifact_ids"},
                                "distinct_count": {"$size": "$distinct_names"},
                            },
                        },
                    ],
                    # Branch 3: dates
                    "dates": [
                        {"$match": {"presentation_date.date": {"$ne": None}}},
                        {
                            "$group": {
                                "_id": None,
                                "artifact_ids": {"$addToSet": "$artifact_id"},
                                "distinct_years": {
                                    "$addToSet": {"$year": {"$toDate": "$presentation_date.date"}},
                                },
                            },
                        },
                        {
                            "$project": {
                                "artifact_count": {"$size": "$artifact_ids"},
                                "distinct_count": {"$size": "$distinct_years"},
                            },
                        },
                    ],
                    # Total artifact count
                    "total": [{"$count": "count"}],
                },
            },
        )

        results = await self.artifacts.aggregate(pipeline).to_list(1)
        facets = results[0] if results else {}

        categories: dict[str, TagCategoryDTO] = {}

        # Merge tag_mentions facet
        for item in facets.get("tag_mentions", []):
            et = item["entity_type"]
            categories[et] = TagCategoryDTO(
                entity_type=et,
                display_name=ENTITY_TYPE_DISPLAY_NAMES.get(et, et.replace("_", " ").title()),
                artifact_count=item["artifact_count"],
                distinct_count=item["distinct_count"],
            )

        # Merge author facet
        for item in facets.get("authors", []):
            categories["author"] = TagCategoryDTO(
                entity_type="author",
                display_name="Author",
                artifact_count=item["artifact_count"],
                distinct_count=item["distinct_count"],
            )

        # Merge date facet
        for item in facets.get("dates", []):
            categories["date"] = TagCategoryDTO(
                entity_type="date",
                display_name="Date",
                artifact_count=item["artifact_count"],
                distinct_count=item["distinct_count"],
            )

        # Inject sticky categories (always present even if count 0)
        for sticky in sticky_categories or []:
            if sticky not in categories:
                categories[sticky] = TagCategoryDTO(
                    entity_type=sticky,
                    display_name=ENTITY_TYPE_DISPLAY_NAMES.get(
                        sticky, sticky.replace("_", " ").title()
                    ),
                    artifact_count=0,
                    distinct_count=0,
                )

        # Sort by artifact_count desc, apply limit
        sorted_cats = sorted(categories.values(), key=lambda c: c.artifact_count, reverse=True)
        total = facets.get("total", [{}])[0].get("count", 0) if facets.get("total") else 0

        return BrowseCategoriesResponse(
            categories=sorted_cats[:limit],
            total_artifacts=total,
        )

    async def get_tag_folders(
        self,
        entity_type: str,
        workspace_id: UUID | None = None,
        parent: str | None = None,
        skip: int = 0,
        limit: int = 50,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> BrowseFoldersResponse:
        base_match = self._browse_base_match(workspace_id, allowed_artifact_ids)

        if entity_type == "author":
            folders = await self._get_author_folders(base_match, skip, limit)
        elif entity_type == "date":
            folders = await self._get_date_folders(base_match, parent, skip, limit)
        else:
            folders = await self._get_tag_folders(base_match, entity_type, skip, limit)

        return BrowseFoldersResponse(
            entity_type=entity_type,
            parent=parent,
            folders=folders,
            total_folders=len(folders),
        )

    async def _get_tag_folders(
        self, base_match: dict, entity_type: str, skip: int, limit: int
    ) -> list[TagFolderDTO]:
        match_stage: dict = {**base_match, "tag_mentions.entity_type": entity_type}
        pipeline: list[dict] = [
            {"$match": match_stage},
            {"$unwind": "$tag_mentions"},
            {"$match": {"tag_mentions.entity_type": entity_type}},
            {
                "$group": {
                    "_id": {"$toLower": "$tag_mentions.tag"},
                    "display_name": {"$first": "$tag_mentions.tag"},
                    "artifact_ids": {"$addToSet": "$artifact_id"},
                },
            },
            {
                "$project": {
                    "tag_value": "$_id",
                    "display_name": 1,
                    "artifact_count": {"$size": "$artifact_ids"},
                },
            },
            {"$sort": {"artifact_count": -1}},
            {"$skip": skip},
            {"$limit": limit},
        ]
        docs = await self.artifacts.aggregate(pipeline).to_list(limit)
        return [
            TagFolderDTO(
                tag_value=d["tag_value"],
                display_name=d["display_name"],
                artifact_count=d["artifact_count"],
            )
            for d in docs
        ]

    async def _get_author_folders(
        self, base_match: dict, skip: int, limit: int
    ) -> list[TagFolderDTO]:
        match_stage: dict = {**base_match, "author_mentions.0": {"$exists": True}}
        pipeline: list[dict] = [
            {"$match": match_stage},
            {"$unwind": "$author_mentions"},
            {
                "$group": {
                    "_id": {"$toLower": "$author_mentions.name"},
                    "display_name": {"$first": "$author_mentions.name"},
                    "artifact_ids": {"$addToSet": "$artifact_id"},
                },
            },
            {
                "$project": {
                    "tag_value": "$_id",
                    "display_name": 1,
                    "artifact_count": {"$size": "$artifact_ids"},
                },
            },
            {"$sort": {"artifact_count": -1}},
            {"$skip": skip},
            {"$limit": limit},
        ]
        docs = await self.artifacts.aggregate(pipeline).to_list(limit)
        return [
            TagFolderDTO(
                tag_value=d["tag_value"],
                display_name=d["display_name"],
                artifact_count=d["artifact_count"],
            )
            for d in docs
        ]

    async def _get_date_folders(
        self, base_match: dict, parent: str | None, skip: int, limit: int
    ) -> list[TagFolderDTO]:
        match_stage: dict = {**base_match, "presentation_date.date": {"$ne": None}}

        if parent is None:
            # Group by year
            pipeline: list[dict] = [
                {"$match": match_stage},
                {
                    "$group": {
                        "_id": {"$year": {"$toDate": "$presentation_date.date"}},
                        "artifact_ids": {"$addToSet": "$artifact_id"},
                    },
                },
                {
                    "$project": {
                        "tag_value": {"$toString": "$_id"},
                        "display_name": {"$toString": "$_id"},
                        "artifact_count": {"$size": "$artifact_ids"},
                    },
                },
                {"$sort": {"tag_value": -1}},
                {"$skip": skip},
                {"$limit": limit},
            ]
            docs = await self.artifacts.aggregate(pipeline).to_list(limit)
            return [
                TagFolderDTO(
                    tag_value=d["tag_value"],
                    display_name=d["display_name"],
                    artifact_count=d["artifact_count"],
                    has_children=True,
                )
                for d in docs
            ]
        else:
            # Group by month within a year
            year = int(parent)
            start = datetime(year, 1, 1, tzinfo=timezone.utc).isoformat()
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc).isoformat()
            match_stage["presentation_date.date"] = {"$gte": start, "$lt": end}

            month_names = [
                "", "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December",
            ]

            pipeline = [
                {"$match": match_stage},
                {
                    "$group": {
                        "_id": {"$month": {"$toDate": "$presentation_date.date"}},
                        "artifact_ids": {"$addToSet": "$artifact_id"},
                    },
                },
                {
                    "$project": {
                        "month_num": "$_id",
                        "artifact_count": {"$size": "$artifact_ids"},
                    },
                },
                {"$sort": {"month_num": 1}},
                {"$skip": skip},
                {"$limit": limit},
            ]
            docs = await self.artifacts.aggregate(pipeline).to_list(limit)
            return [
                TagFolderDTO(
                    tag_value=f"{parent}-{d['month_num']:02d}",
                    display_name=month_names[d["month_num"]],
                    artifact_count=d["artifact_count"],
                )
                for d in docs
            ]

    async def get_folder_artifacts(
        self,
        entity_type: str,
        tag_value: str,
        workspace_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
        allowed_artifact_ids: list[UUID] | None = None,
    ) -> list[ArtifactBrowseItemDTO]:
        base_match = self._browse_base_match(workspace_id, allowed_artifact_ids)

        if entity_type == "author":
            return await self._get_folder_artifacts_simple(
                query={
                    **base_match,
                    "author_mentions": {
                        "$elemMatch": {"name": {"$regex": f"^{tag_value}$", "$options": "i"}},
                    },
                },
                skip=skip,
                limit=limit,
            )

        if entity_type == "date":
            query = {**base_match}
            if "-" in tag_value:
                year, month = tag_value.split("-", 1)
                month_int = int(month)
                start = datetime(int(year), month_int, 1, tzinfo=timezone.utc).isoformat()
                if month_int == 12:
                    end = datetime(int(year) + 1, 1, 1, tzinfo=timezone.utc).isoformat()
                else:
                    end = datetime(int(year), month_int + 1, 1, tzinfo=timezone.utc).isoformat()
                query["presentation_date.date"] = {"$gte": start, "$lt": end}
            else:
                year_int = int(tag_value)
                start = datetime(year_int, 1, 1, tzinfo=timezone.utc).isoformat()
                end = datetime(year_int + 1, 1, 1, tzinfo=timezone.utc).isoformat()
                query["presentation_date.date"] = {"$gte": start, "$lt": end}
            return await self._get_folder_artifacts_simple(query=query, skip=skip, limit=limit)

        # NER tag browse — use aggregation to extract page-level provenance
        return await self._get_folder_artifacts_with_provenance(
            base_match=base_match,
            entity_type=entity_type,
            tag_value=tag_value,
            skip=skip,
            limit=limit,
        )

    async def _get_folder_artifacts_simple(
        self, query: dict, skip: int, limit: int
    ) -> list[ArtifactBrowseItemDTO]:
        """Fetch folder artifacts without tag provenance (authors, dates)."""
        projection = {
            "artifact_id": 1,
            "title_mention.title": 1,
            "source_filename": 1,
            "artifact_type": 1,
            "pages": 1,
            "presentation_date.date": 1,
            "author_mentions.name": 1,
            "_id": 0,
        }
        cursor = self.artifacts.find(query, projection).skip(skip).limit(limit)
        return [self._doc_to_browse_item(doc) async for doc in cursor]

    async def _get_folder_artifacts_with_provenance(
        self,
        base_match: dict,
        entity_type: str,
        tag_value: str,
        skip: int,
        limit: int,
    ) -> list[ArtifactBrowseItemDTO]:
        """Fetch folder artifacts with page-level provenance for the browsed tag."""
        match_stage = {
            **base_match,
            "tag_mentions": {
                "$elemMatch": {
                    "entity_type": entity_type,
                    "tag": {"$regex": f"^{tag_value}$", "$options": "i"},
                },
            },
        }

        pipeline: list[dict] = [
            {"$match": match_stage},
            # Extract the matched tag's sources array
            {
                "$addFields": {
                    "_matched_tag": {
                        "$arrayElemAt": [
                            {
                                "$filter": {
                                    "input": {"$ifNull": ["$tag_mentions", []]},
                                    "cond": {
                                        "$and": [
                                            {"$eq": ["$$this.entity_type", entity_type]},
                                            {"$eq": [{"$toLower": "$$this.tag"}, tag_value]},
                                        ],
                                    },
                                },
                            },
                            0,
                        ],
                    },
                },
            },
            {
                "$project": {
                    "artifact_id": 1,
                    "title_mention.title": 1,
                    "source_filename": 1,
                    "artifact_type": 1,
                    "pages": 1,
                    "presentation_date.date": 1,
                    "author_mentions.name": 1,
                    "tag_page_sources": {"$ifNull": ["$_matched_tag.sources", []]},
                    "_id": 0,
                },
            },
            {"$skip": skip},
            {"$limit": limit},
        ]

        items: list[ArtifactBrowseItemDTO] = []
        async for doc in self.artifacts.aggregate(pipeline):
            item = self._doc_to_browse_item(doc)
            # Attach provenance from the aggregation pipeline
            raw_sources = doc.get("tag_page_sources", [])
            if raw_sources:
                item.tag_page_sources = [
                    TagPageSource(
                        page_id=s["page_id"],
                        page_index=s["page_index"],
                    )
                    for s in raw_sources
                    if "page_id" in s and "page_index" in s
                ]
            items.append(item)
        return items

    @staticmethod
    def _doc_to_browse_item(doc: dict) -> ArtifactBrowseItemDTO:
        """Convert a MongoDB document to an ArtifactBrowseItemDTO."""
        pd = doc.get("presentation_date", {})
        pd_date = pd.get("date") if pd else None
        return ArtifactBrowseItemDTO(
            artifact_id=doc["artifact_id"],
            title=doc.get("title_mention", {}).get("title") if doc.get("title_mention") else None,
            source_filename=doc.get("source_filename"),
            artifact_type=doc.get("artifact_type", "UNCLASSIFIED"),
            page_count=len(doc.get("pages", [])),
            presentation_date=pd_date,
            author_names=[a["name"] for a in doc.get("author_mentions", [])],
        )

    async def ensure_browse_indexes(self) -> None:
        """Create indexes to support browse aggregation pipelines. Idempotent."""
        await self.artifacts.create_index(
            [("workspace_id", 1), ("tag_mentions.entity_type", 1), ("tag_mentions.tag", 1)],
            name="idx_browse_tags",
        )
        await self.artifacts.create_index(
            [("workspace_id", 1), ("tag_mentions.entity_type", 1), ("tag_mentions.tag_normalized", 1)],
            name="idx_browse_tags_normalized",
        )
        await self.artifacts.create_index(
            [("workspace_id", 1), ("author_mentions.name", 1)],
            name="idx_browse_authors",
        )
        await self.artifacts.create_index(
            [("workspace_id", 1), ("presentation_date.date", 1)],
            name="idx_browse_dates",
        )
