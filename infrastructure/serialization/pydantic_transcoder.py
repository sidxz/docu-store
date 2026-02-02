from eventsourcing.persistence import Transcoding
from pydantic import BaseModel


class PydanticTranscoding(Transcoding):
    """Adapter that allows the Event Sourcing library to speak 'Pydantic'.
    Used for serializing and deserializing Pydantic models in event sourcing, both while writing and rehydrating
    """

    def __init__(self, type: type[BaseModel]):
        self.type = type
        self.name = type.__name__

    def encode(self, obj: BaseModel) -> dict:
        # Export to dict for human-readable storage
        return obj.model_dump(mode="json")

    def decode(self, data: dict) -> BaseModel:
        # Rehydrate from dict
        return self.type.model_validate(data)
