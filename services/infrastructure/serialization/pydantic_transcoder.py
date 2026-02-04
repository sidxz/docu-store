from eventsourcing.persistence import Transcoding
from pydantic import BaseModel


class PydanticTranscoding(Transcoding):
    """Adapter for Event Sourcing to work with Pydantic.

    Used for serializing and deserializing Pydantic models in event sourcing,
    both while writing and rehydrating.
    """

    def __init__(self, model_type: type[BaseModel]) -> None:
        self.type = model_type
        self.name = model_type.__name__

    def encode(self, obj: BaseModel) -> dict:
        # Export to dict for human-readable storage
        return obj.model_dump(mode="json")

    def decode(self, data: dict) -> BaseModel:
        # Rehydrate from dict
        return self.type.model_validate(data)
