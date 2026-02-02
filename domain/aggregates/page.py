from __future__ import annotations

from eventsourcing.domain import Aggregate, event

from domain.exceptions import ValidationError
from domain.value_objects.compound import Compound


class Page(Aggregate):
    """The Aggregate Root for a Page.

    It is now purely focused on domain logic and state transitions.
    """

    INITIAL_VERSION = 0

    @classmethod
    def create(cls, name: str) -> Page:
        """Factory method that creates a new Page aggregate."""
        return cls(name=name)

    class Created(Aggregate.Created):
        """Defines the structure of the Page Created event."""

        name: str

    @event(Created)  # Links this handler to the Created event class above
    def __init__(self, name: str) -> None:
        self.name = name
        self.compounds: list[Compound] = []

    class CompoundsAdded(Aggregate.Event):
        # We use the rich type here. The infrastructure layer
        # (transcoder) will handle the JSON serialization.
        compounds: list[Compound]

    # ============================================================================
    # COMMAND METHOD - Add Compounds
    # ============================================================================

    def add_compounds(self, compounds: list[Compound]) -> None:
        if not compounds:
            raise ValidationError("Compounds cannot be empty")

        # Trigger event with rich Value Objects
        self.trigger_event(self.CompoundsAdded, compounds=compounds)

    @event(CompoundsAdded)
    def _apply_compounds_added(self, compounds: list[Compound]) -> None:
        self.compounds.extend(compounds)
