from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.artifact_dtos import ArtifactResponse
from application.dtos.page_dtos import PageResponse
from application.ports.repositories.artifact_read_models import ArtifactReadModel
from application.ports.repositories.page_read_models import PageReadModel
from infrastructure.config import Settings


class MongoReadRepository(PageReadModel, ArtifactReadModel):
    def __init__(self, client: AsyncIOMotorClient, settings: Settings) -> None:
        self.client = client
        self.db = self.client[settings.mongo_db]
        self.pages = self.db[settings.mongo_pages_collection]
        self.artifacts = self.db[settings.mongo_artifacts_collection]

    async def get_page_by_id(self, page_id: UUID) -> PageResponse | None:
        doc = await self.pages.find_one({"page_id": str(page_id)})
        if not doc:
            return None
        # Map MongoDB _id (ObjectId) to page_id field
        doc["page_id"] = doc.get("page_id") or str(doc.pop("_id"))
        return PageResponse(**doc)

    async def get_pages_by_id(self, page_ids: list[UUID]) -> list[PageResponse]:
        """Fetch multiple pages by their IDs in a single query."""
        if not page_ids:
            return []

        cursor = self.pages.find({"page_id": {"$in": [str(pid) for pid in page_ids]}})
        pages = []
        async for doc in cursor:
            doc["page_id"] = doc.get("page_id") or str(doc.pop("_id"))
            pages.append(PageResponse(**doc))
        # Sort by index to maintain page order
        pages.sort(key=lambda p: p.index)
        return pages

    async def get_artifact_by_id(self, artifact_id: UUID) -> ArtifactResponse | None:
        doc = await self.artifacts.find_one({"artifact_id": str(artifact_id)})
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

    async def list_artifacts(self, skip: int = 0, limit: int = 100) -> list[ArtifactResponse]:
        """List all artifacts with pagination."""
        cursor = self.artifacts.find().skip(skip).limit(limit)
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
