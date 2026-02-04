from application.dtos.artifact_dtos import ArtifactResponse
from domain.aggregates.artifact import Artifact


class ArtifactMapper:
    @staticmethod
    def to_artifact_response(artifact: Artifact) -> ArtifactResponse:
        """Map an Artifact aggregate to an ArtifactResponse DTO.

        Args:
            artifact: The Artifact aggregate to map

        Returns:
            ArtifactResponse: The mapped response DTO

        """
        return ArtifactResponse(
            artifact_id=artifact.id,
            source_uri=artifact.source_uri,
            source_filename=artifact.source_filename,
            artifact_type=artifact.artifact_type,
            mime_type=artifact.mime_type,
            storage_location=artifact.storage_location,
            pages=tuple(artifact.pages),
            title_mention=artifact.title_mention,
            tags=list(artifact.tags),
            summary_candidate=artifact.summary_candidate,
        )
