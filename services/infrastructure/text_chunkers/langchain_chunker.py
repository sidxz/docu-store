import structlog
from langchain_text_splitters import RecursiveCharacterTextSplitter

from application.ports.text_chunker import TextChunker
from domain.value_objects.text_chunk import TextChunk

logger = structlog.get_logger()


class LangChainTextChunker(TextChunker):
    """Adapter for text chunking using LangChain's RecursiveCharacterTextSplitter.

    Uses character-based splitting with sentence-aware boundaries,
    making it model-agnostic. Chunk size and overlap are configured
    externally, so switching embedding models only requires changing
    configuration values.

    The RecursiveCharacterTextSplitter tries to split on natural
    boundaries in this order: paragraphs, newlines, sentences,
    words, characters — preserving semantic coherence.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        """Initialize the chunker.

        Args:
            chunk_size: Maximum number of characters per chunk.
                        Default 1000 chars ≈ 200-250 tokens for most models.
            chunk_overlap: Number of overlapping characters between consecutive
                          chunks. Preserves context at boundaries.

        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            is_separator_regex=False,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        logger.info(
            "langchain_text_chunker_initialized",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def chunk_text(self, text: str) -> list[TextChunk]:
        """Split text into overlapping chunks.

        If the text fits within chunk_size, returns a single chunk
        containing the full text.

        Args:
            text: The full text content to split

        Returns:
            List of TextChunk value objects, ordered by chunk_index

        """
        if not text or not text.strip():
            msg = "Text cannot be empty"
            raise ValueError(msg)

        # Use create_documents to get metadata with offsets
        docs = self._splitter.create_documents([text])

        total_chunks = len(docs)

        chunks = []
        for i, doc in enumerate(docs):
            # Calculate character offsets by finding the chunk in the original text
            # Start searching from where the previous chunk started to handle overlaps
            search_start = chunks[-1].start_char if chunks else 0
            start_char = text.find(doc.page_content, search_start)
            if start_char == -1:
                # Fallback: search from beginning
                start_char = text.find(doc.page_content)
            end_char = (
                start_char + len(doc.page_content) if start_char != -1 else len(doc.page_content)
            )

            chunks.append(
                TextChunk(
                    chunk_index=i,
                    text=doc.page_content,
                    start_char=max(start_char, 0),
                    end_char=end_char,
                    total_chunks=total_chunks,
                ),
            )

        logger.debug(
            "text_chunked",
            original_length=len(text),
            num_chunks=total_chunks,
            chunk_sizes=[len(c.text) for c in chunks],
        )

        return chunks
