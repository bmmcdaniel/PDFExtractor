"""Text extraction in multiple formats: Markdown, Plain Text, XHTML, DOCX."""

import logging
import re
from collections.abc import Callable

import pymupdf
import pymupdf4llm
from docx import Document as DocxDocument

from core.pdf_handler import PDFHandler

log = logging.getLogger(__name__)


def _add_formatted_runs(para, text: str) -> None:
    """Parse Markdown inline formatting into python-docx Runs.

    Handles ***bold italic***, **bold**, and *italic*.
    """
    # Pattern matches ***bold italic***, **bold**, *italic*, or plain text
    pattern = re.compile(
        r"\*\*\*(.+?)\*\*\*"   # ***bold italic***
        r"|\*\*(.+?)\*\*"      # **bold**
        r"|\*(.+?)\*"          # *italic*
        r"|([^*]+)"            # plain text
    )
    for match in pattern.finditer(text):
        bold_italic, bold, italic, plain = match.groups()
        if bold_italic:
            run = para.add_run(bold_italic)
            run.bold = True
            run.italic = True
        elif bold:
            run = para.add_run(bold)
            run.bold = True
        elif italic:
            run = para.add_run(italic)
            run.italic = True
        elif plain:
            para.add_run(plain)


class TextExtractor:
    """Handles text extraction in multiple formats."""

    def __init__(self, pdf_handler: PDFHandler):
        """Initialize with an open PDFHandler."""
        self._handler = pdf_handler

    def extract_markdown(
        self,
        pages: list[int],
        output_path: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        """Extract text as Markdown using pymupdf4llm."""
        if progress_callback:
            progress_callback(0, len(pages))

        md_text = pymupdf4llm.to_markdown(
            self._handler.document,
            pages=pages,
            page_chunks=False,
            show_progress=False,
            table_strategy="lines_strict",
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_text)

        if progress_callback:
            progress_callback(len(pages), len(pages))

    def extract_plain_text(
        self,
        pages: list[int],
        output_path: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        """Extract text as plain text with form-feed page separators."""
        doc = self._handler.document
        text_parts = []

        for i, page_num in enumerate(pages):
            page = doc[page_num]
            text_parts.append(page.get_text("text"))
            if progress_callback:
                progress_callback(i + 1, len(pages))

        combined_text = "\f".join(text_parts)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(combined_text)

    def extract_xhtml(
        self,
        pages: list[int],
        output_path: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        """Extract text as clean, semantic XHTML."""
        doc = self._handler.document
        filename = self._handler.filename

        header = pymupdf.ConversionHeader("xhtml", filename=filename)
        trailer = pymupdf.ConversionTrailer("xhtml")

        xhtml_parts = [header]
        for i, page_num in enumerate(pages):
            page = doc[page_num]
            xhtml_parts.append(page.get_text("xhtml"))
            if progress_callback:
                progress_callback(i + 1, len(pages))
        xhtml_parts.append(trailer)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(xhtml_parts))

    def extract_docx(
        self,
        pages: list[int],
        output_path: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        """Extract text as a Word document using python-docx."""
        chunks = pymupdf4llm.to_markdown(
            self._handler.document,
            pages=pages,
            page_chunks=True,
            table_strategy="lines_strict",
        )

        docx_doc = DocxDocument()

        for i, chunk in enumerate(chunks):
            md_text = chunk["text"]

            for line in md_text.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue

                if stripped.startswith("### "):
                    docx_doc.add_heading(stripped[4:], level=3)
                elif stripped.startswith("## "):
                    docx_doc.add_heading(stripped[3:], level=2)
                elif stripped.startswith("# "):
                    docx_doc.add_heading(stripped[2:], level=1)
                else:
                    para = docx_doc.add_paragraph()
                    _add_formatted_runs(para, stripped)

            # Page break between pages (except after last)
            if i < len(chunks) - 1:
                docx_doc.add_page_break()

            if progress_callback:
                progress_callback(i + 1, len(chunks))

        docx_doc.save(output_path)
