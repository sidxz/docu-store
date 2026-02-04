from uuid import UUID

from returns.result import Failure, Result, Success

from application.dtos.page_dtos import PageResponse
from application.ports.repositories.page_read_models import PageReadModel


class GetPageByIdQuery:
    def __init__(self, page_read_model: PageReadModel):
        self.page_read_model = page_read_model

    async def execute(self, page_id: UUID) -> Result[PageResponse, str]:
        try:
            page_data = await self.page_read_model.get_page_by_id(page_id)
            if page_data is None:
                return Failure(f"Page with ID {page_id} not found")

            page_response = PageResponse(
                page_id=UUID(page_data["page_id"]),
                artifact_id=UUID(page_data["artifact_id"]),
                name=page_data["name"],
                compound_mentions=page_data["compound_mentions"],
            )
            return Success(page_response)
        except ValueError as e:
            return Failure(f"Data error: {e!s}")
