"""Compatibility wrapper for document loading logic."""

from knowledge.knowledge_loader import (
    load_documents_from_dir,
    load_file,
    load_pdf,
    load_docx,
    load_txt,
)

__all__ = [
    "load_documents_from_dir",
    "load_file",
    "load_pdf",
    "load_docx",
    "load_txt",
]
