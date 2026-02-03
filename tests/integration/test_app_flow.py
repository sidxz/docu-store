from domain.value_objects.compound_mention import CompoundMention
from eventsourcing.application import Application
from returns.result import Success

from application.dtos.page_dtos import AddCompoundMentionsRequest, CreatePageRequest
from application.use_cases.page_use_cases import AddCompoundMentionsUseCase
from infrastructure.di.container import create_container


def test_page_compound_mentions_roundtrip():
    # 1. Setup Container and App
    container = create_container()
    app = container[Application]

    # 2. Create a Page
    # Assuming your application service or use cases are used here.
    # For a raw test, we can use the app directly if we exposed methods,
    # but let's use the repository to check the state.
    from application.ports.repositories.page_repository import PageRepository

    repo = container[PageRepository]

    from application.use_cases.page_use_cases import CreatePageUseCase

    create_page_request = CreatePageRequest(name="Test Discovery Page")
    create_uc = container[CreatePageUseCase]
    result = create_uc.execute(request=create_page_request)
    print(f"Create Page Result: {result}")
    assert isinstance(result, Success)
    page_response = result.unwrap()
    page_id = page_response.id
    print(f"Created Page with ID: {page_id}")

    sample_compound_mentions = [
        CompoundMention(smiles="CCO", extracted_name="Ethanol"),
        CompoundMention(smiles="C1=CC=CC=C1", extracted_name="Benzene"),
    ]

    add_compound_mentions_uc = container[AddCompoundMentionsUseCase]
    add_compound_mentions_request = AddCompoundMentionsRequest(
        page_id=page_id, compound_mentions=sample_compound_mentions
    )
    add_compound_mentions_uc.execute(request=add_compound_mentions_request)

    # Check if added correctly
    rehydrated_page = repo.get_by_id(page_id)
    print(f"Rehydrated Page: {rehydrated_page}")
    assert rehydrated_page.name == "Test Discovery Page"

    assert len(rehydrated_page.compound_mentions) == 2
    assert rehydrated_page.compound_mentions[0].smiles == "CCO"
    assert isinstance(rehydrated_page.compound_mentions[0], CompoundMention)
    assert isinstance(rehydrated_page.compound_mentions[0], CompoundMention)

    print(f"Successfully rehydrated {len(rehydrated_page.compound_mentions)} compound_mentions!")


if __name__ == "__main__":
    # Quick manual run
    test_page_compound_mentions_roundtrip()
