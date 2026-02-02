from __future__ import annotations

from typing import Any

from eventsourcing.domain import Aggregate, event

from domain.exceptions import ValidationError
from domain.value_objects.compound import Compound


class Page(Aggregate):
    INITIAL_VERSION = 0  # required for KurrentDB/EventStoreDB

    class Created(Aggregate.Created):
        name: str

    class CompoundsAdded(Aggregate.Event):
        # Store JSON-ready dicts (not Compound objects)
        compounds: list[dict[str, Any]]

    @classmethod
    def create(cls, name: str) -> Page:
        return cls(name=name)

    @event(Created)
    def __init__(self, name: str) -> None:
        self.name = name
        self.compounds: list[Compound] = []

    def add_compounds(self, compounds: list[Compound]) -> None:
        if not compounds:
            raise ValidationError("Compounds cannot be empty")

        # Convert to JSON-friendly primitives (datetime/UUID become strings)
        payload: list[dict[str, Any]] = [
            c.model_dump(mode="json", exclude_none=True) for c in compounds
        ]

        self.trigger_event(self.CompoundsAdded, compounds=payload)

    @event(CompoundsAdded)
    def compounds_added(self, compounds: list[dict[str, Any]]) -> None:
        # Rehydrate rich value objects from stored dicts
        self.compounds.extend(Compound.model_validate(c) for c in compounds)
