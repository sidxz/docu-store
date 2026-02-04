from enum import Enum


class MimeType(str, Enum):
    """Represent supported MIME types for ingested artifacts."""

    PDF = "application/pdf"

    PPT = "application/vnd.ms-powerpoint"
    PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    DOC = "application/msword"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
