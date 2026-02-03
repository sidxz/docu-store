from uuid import UUID

from domain.value_objects.compound_mention import CompoundMention
from pydantic import BaseModel


class CreatePageRequest(BaseModel):
    name: str


class AddCompoundMentionsRequest(BaseModel):
    page_id: UUID
    compound_mentions: list[CompoundMention]


class PageResponse(BaseModel):
    page_id: UUID
    name: str
    compound_mentions: list[CompoundMention]
