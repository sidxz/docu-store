from eventsourcing.domain import Aggregate, event

from domain.exceptions import ValidationError
from domain.value_objects.compound import Compound


class Page(Aggregate):
    INITIAL_VERSION = 0  # Required for KurrentDB/EventStoreDB

    @event("Created")
    def __init__(self, name: str) -> None:
        self.name = name
        self.compounds: list[Compound] = []

    @event("CompoundsAdded")
    def add_compounds(self, compounds: list[Compound]) -> None:
        if not compounds:
            msg = "Compounds cannot be empty"
            raise ValidationError(msg)
        self.compounds.extend(compounds)
