from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient

from application.dtos.page_dtos import PageResponse
from application.ports.repositories.page_read_models import PageReadModel
from infrastructure.config import Settings


class MongoReadRepository(PageReadModel):
    def __init__(self, client: AsyncIOMotorClient, settings: Settings):
        self.client = client
        self.db = self.client[settings.mongo_db]
        self.pages = self.db[settings.mongo_pages_collection]

    async def get_page_by_id(self, page_id: UUID) -> PageResponse | None:
        doc = await self.pages.find_one({"page_id": str(page_id)})
        if not doc:
            return None
        # Map MongoDB _id (ObjectId) to id field (UUID string)
        doc["id"] = str(doc.pop("_id"))
        return PageResponse(**doc)
