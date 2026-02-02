from eventsourcing.application import Application
from returns.result import Success

from application.dtos.page_dtos import AddCompoundsRequest, CreatePageRequest
from application.use_cases.page_use_cases import AddCompoundsUseCase
from domain.value_objects.compound import Compound
from infrastructure.di.container import create_container


def test_page_compounds_roundtrip():
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

    sample_compounds = [
        Compound(smiles="CCO", extracted_name="Ethanol"),
        Compound(smiles="C1=CC=CC=C1", extracted_name="Benzene"),
    ]

    add_compounds_uc = container[AddCompoundsUseCase]
    add_compounds_request = AddCompoundsRequest(page_id=page_id, compounds=sample_compounds)
    add_compounds_uc.execute(request=add_compounds_request)

    # Check if added correctly
    rehydrated_page = repo.get_by_id(page_id)
    print(f"Rehydrated Page: {rehydrated_page}")
    assert rehydrated_page.name == "Test Discovery Page"

    assert len(rehydrated_page.compounds) == 2
    assert rehydrated_page.compounds[0].smiles == "CCO"
    assert isinstance(rehydrated_page.compounds[0], Compound)
    assert isinstance(rehydrated_page.compounds[0], Compound)

    print(f"Successfully rehydrated {len(rehydrated_page.compounds)} compounds!")


if __name__ == "__main__":
    # Quick manual run
    test_page_compounds_roundtrip()
