"""Local resume extraction (PDF/DOCX -> plain text). No LLM involved.

Kept fast and synchronous (spec section 5). Returns None when no usable file is
provided so the prompt builder can omit the resume block entirely.
"""

import io
from typing import Iterator, Optional

from pypdf import PdfReader
from docx import Document
from docx.document import Document as _DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from app.config import RESUME_CHAR_CAP


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _iter_block_items(parent) -> Iterator[object]:
    """Yield Paragraphs and Tables from a document/cell in document order.

    python-docx's `document.paragraphs` skips anything inside tables, which is
    where many resume templates put their actual content. Walking the body's
    XML children lets us capture both, in order.
    """
    if isinstance(parent, _DocxDocument):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError(f"Unsupported parent type: {type(parent)!r}")

    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def _extract_docx(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    lines = []

    def walk(container) -> None:
        for block in _iter_block_items(container):
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if text:
                    lines.append(text)
            elif isinstance(block, Table):
                for row in block.rows:
                    # Recurse into each cell so nested tables are captured too.
                    for cell in row.cells:
                        walk(cell)

    walk(document)
    return "\n".join(lines)


def extract_resume_text(data: Optional[bytes], filename: Optional[str]) -> Optional[str]:
    """Extract plain text from raw resume bytes.

    Dispatches on file extension. Returns None if no data, unsupported type, or
    nothing meaningful could be extracted. Output is truncated to RESUME_CHAR_CAP.
    """
    if not data or not filename:
        return None

    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            text = _extract_pdf(data)
        elif name.endswith(".docx"):
            text = _extract_docx(data)
        else:
            # Unsupported type (e.g. legacy .doc) — skip rather than guess.
            return None
    except Exception:
        # Corrupt/unreadable file: treat as "no resume" instead of failing the request.
        return None

    text = (text or "").strip()
    if not text:
        return None

    if len(text) > RESUME_CHAR_CAP:
        text = text[:RESUME_CHAR_CAP]

    return text
