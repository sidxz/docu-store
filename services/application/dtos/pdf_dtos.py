from pydantic import BaseModel


class PDFContent(BaseModel):
    file_path: str | None = None
    pages: list | None = None
    pages_png: list | None = None
    combined_content: str | None = None
    first_page_content: str | None = None
    last_page_content: str | None = None
