from langchain_community.document_loaders import PyPDFLoader

from application.dtos.pdf_dtos import PDFContent
from application.ports.blob_store import BlobStore
from application.ports.pdf_service import PDFService
from domain.exceptions import InfrastructureError, ValidationError


class PyPDFService(PDFService):
    def __init__(self, blob_store: BlobStore) -> None:
        self.blob_store = blob_store

    def parse(self, storage_key: str) -> PDFContent:
        """Load PDF from blob store and returns its text content.

        Args:
            storage_key: Key to retrieve the PDF from blob store

        Returns:
            PDFContent with parsed PDF data

        Raises:
            ValidationError: If storage_key is invalid
            InfrastructureError: If PDF retrieval or parsing fails

        """
        # Validate input
        if not storage_key or not isinstance(storage_key, str):
            msg = f"Invalid storage_key: {storage_key!r}"
            raise ValidationError(msg)

        try:
            # Get file path from blob store using context manager
            with self.blob_store.get_file(storage_key) as file_path:
                # Load PDF using PyPDFLoader
                loader = PyPDFLoader(str(file_path))
                loaded_docs = loader.load()
        except Exception as e:
            msg = f"Error parsing PDF (key: {storage_key}): {e!s}"
            raise InfrastructureError(msg) from e

        if not loaded_docs:
            msg = f"No content extracted from PDF: {storage_key}"
            raise InfrastructureError(msg)

        first_page_content = loaded_docs[0].page_content
        combined_content = " ".join(doc.page_content for doc in loaded_docs)
        last_page_content = loaded_docs[-1].page_content

        return PDFContent(
            file_path=storage_key,
            pages=loaded_docs,
            combined_content=combined_content,
            first_page_content=first_page_content,
            last_page_content=last_page_content,
        )
