"""Document text extraction: PDF (pdfplumber), DOCX (python-docx), TXT/MD (direct read).

Each extractor has a 30-second timeout fallback. Results are returned as plain strings
and stored in Document.content_text for later use by the AI planner.
"""

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

_EXTRACT_TIMEOUT = 30  # seconds


def _extract_pdf(file_path: str) -> str:
    import pdfplumber

    with pdfplumber.open(file_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _extract_docx(file_path: str) -> str:
    from docx import Document as DocxDoc

    doc = DocxDoc(file_path)
    return "\n".join(p.text for p in doc.paragraphs)


def _extract_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_text(file_path: str, doc_type: str) -> str:
    """Extract text from a document file.

    Runs in a thread pool with a 30-second timeout. Returns empty string on failure.
    """
    dispatch = {
        "pdf": _extract_pdf,
        "docx": _extract_docx,
        "txt": _extract_text,
        "md": _extract_text,
    }

    fn = dispatch.get(doc_type, _extract_text)

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, file_path)
            return future.result(timeout=_EXTRACT_TIMEOUT)
    except (FutureTimeout, Exception):
        return ""
