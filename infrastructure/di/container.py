from eventsourcing.application import Application
from lagom import Container

from application.ports.repositories.page_repository import PageRepository
from application.use_cases.page_use_cases import CreatePageUseCase
from infrastructure.config import settings
from infrastructure.EventSourcedRepositories.page_repository import EventSourcedPageRepository


def create_container() -> Container:
    container = Container()

    # Create Application ONCE
    docu_store_application = Application(
        env={
            "PERSISTENCE_MODULE": "eventsourcing_kurrentdb",
            "KURRENTDB_URI": settings.eventstoredb_uri,
        },
    )

    # Register as singleton instance
    container[Application] = docu_store_application

    container[PageRepository] = lambda c: EventSourcedPageRepository(
        application=c[Application],
    )

    # Application Use Cases and other dependencies can be registered here
    container[CreatePageUseCase] = lambda c: CreatePageUseCase(
        page_repository=c[PageRepository],
    )

    return container
