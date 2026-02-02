from uuid import UUID

from pydantic import BaseModel

from domain.value_objects.compound import Compound


class CreatePageRequest(BaseModel):
    name: str


class AddCompoundsRequest(BaseModel):
    page_id: UUID
    compounds: list[Compound]


class PageResponse(BaseModel):
    page_id: UUID
    name: str
    compounds: list[Compound]
