from typing import Any

from document_parsing.document_parser import DocumentParser
from document_parsing.docx.docx_parser import DocxParser

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def get_document_parser(
    document: Any,
    content_type: str,
) -> DocumentParser:

    if content_type == DOCX_MIME_TYPE:
        return DocxParser(document)

    raise ValueError(f"Unsupported document content type: {content_type}")
