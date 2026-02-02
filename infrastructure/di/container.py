from eventsourcing.application import Application
from lagom import Container

from application.ports.repositories.page_repository import PageRepository
from application.use_cases.page_use_cases import AddCompoundsUseCase, CreatePageUseCase
from domain.value_objects.compound import Compound
from infrastructure.config import settings
from infrastructure.event_sourced_repositories.page_repository import EventSourcedPageRepository
from infrastructure.serialization.pydantic_transcoder import PydanticTranscoding


class DocuStoreApplication(Application):
    """Subclassing Application is the recommended way to register custom transcodings
    in the latest versions of the eventsourcing library.
    """

    def register_transcodings(self, transcoder):
        super().register_transcodings(transcoder)
        transcoder.register(PydanticTranscoding(Compound))


def create_container() -> Container:
    container = Container()

    # Initialize our custom Application subclass
    docu_store_application = DocuStoreApplication(
        env={
            "PERSISTENCE_MODULE": "eventsourcing_kurrentdb",
            "KURRENTDB_URI": settings.eventstoredb_uri,
        },
    )

    container[Application] = docu_store_application

    container[PageRepository] = lambda c: EventSourcedPageRepository(
        application=c[Application],
    )

    container[CreatePageUseCase] = lambda c: CreatePageUseCase(
        page_repository=c[PageRepository],
    )

    container[AddCompoundsUseCase] = lambda c: AddCompoundsUseCase(
        page_repository=c[PageRepository],
    )

    return container
