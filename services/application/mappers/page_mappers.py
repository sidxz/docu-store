from application.dtos.page_dtos import PageResponse
from domain.aggregates.page import Page


class PageMapper:
    """Mapper for converting Page domain objects to DTOs."""

    @staticmethod
    def to_page_response(page: Page) -> PageResponse:
        """Map a Page aggregate to a PageResponse DTO.

        Args:
            page: The Page aggregate to map

        Returns:
            PageResponse: The mapped response DTO

        """
        return PageResponse(
            page_id=page.id,
            artifact_id=page.artifact_id,
            name=page.name,
            index=page.index,
            compound_mentions=page.compound_mentions,
            tag_mentions=page.tag_mentions,
            text_mention=page.text_mention,
            summary_candidate=page.summary_candidate,
        )
