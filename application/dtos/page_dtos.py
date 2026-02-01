from uuid import UUID

from pydantic import BaseModel

from domain.value_objects.compound import Compound


class CreatePageRequest(BaseModel):
    name: str


class PageResponse(BaseModel):
    id: UUID
    name: str
    compounds: list[Compound]
