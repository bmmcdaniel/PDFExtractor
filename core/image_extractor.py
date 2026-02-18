"""Image extraction with deduplication and format conversion."""

import logging
import os
from collections.abc import Callable

import pymupdf
from PIL import Image

from core.pdf_handler import PDFHandler

log = logging.getLogger(__name__)


class ImageExtractor:
    """Handles image extraction with deduplication and format conversion."""

    def __init__(self, pdf_handler: PDFHandler):
        """Initialize with an open PDFHandler."""
        self._handler = pdf_handler

    def extract(
        self,
        pages: list[int],
        output_dir: str,
        format: str = "native",
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        """Extract images from selected pages.

        Images are deduplicated by xref -- if the same image appears on
        multiple selected pages, it is extracted only once.

        Args:
            pages: List of 0-based page indices.
            output_dir: Directory to save extracted images.
            format: Output format -- "native", "png", "jpeg", or "webp".
            progress_callback: Optional callback(current, total).

        Returns:
            Number of unique images extracted.
        """
        doc = self._handler.document
        os.makedirs(output_dir, exist_ok=True)

        # Collect unique xrefs across selected pages
        seen_xrefs: set[int] = set()
        unique_xrefs: list[int] = []

        for page_num in pages:
            page = doc[page_num]
            for img in page.get_images():
                xref = img[0]
                if xref not in seen_xrefs:
                    seen_xrefs.add(xref)
                    unique_xrefs.append(xref)

        total = len(unique_xrefs)
        if progress_callback:
            progress_callback(0, total)

        for i, xref in enumerate(unique_xrefs):
            if format == "native":
                self._extract_native(doc, xref, output_dir)
            elif format == "png":
                self._extract_png(doc, xref, output_dir)
            elif format == "jpeg":
                self._extract_jpeg(doc, xref, output_dir)
            elif format == "webp":
                self._extract_webp(doc, xref, output_dir)

            if progress_callback:
                progress_callback(i + 1, total)

        return total

    def _extract_native(
        self, doc: pymupdf.Document, xref: int, output_dir: str
    ) -> None:
        """Extract image in its original format."""
        base_image = doc.extract_image(xref)
        image_ext = base_image["ext"]
        image_bytes = base_image["image"]

        output_path = os.path.join(output_dir, f"img_{xref}.{image_ext}")
        with open(output_path, "wb") as f:
            f.write(image_bytes)

    def _extract_png(
        self, doc: pymupdf.Document, xref: int, output_dir: str
    ) -> None:
        """Extract image converted to PNG."""
        pix = pymupdf.Pixmap(doc, xref)

        # Convert CMYK to RGB if needed
        if pix.n - pix.alpha > 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

        output_path = os.path.join(output_dir, f"img_{xref}.png")
        pix.save(output_path)

    def _extract_jpeg(
        self, doc: pymupdf.Document, xref: int, output_dir: str
    ) -> None:
        """Extract image converted to JPEG."""
        pix = pymupdf.Pixmap(doc, xref)

        # Convert CMYK to RGB if needed
        if pix.n - pix.alpha > 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

        # JPEG does not support alpha -- strip it
        if pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)

        output_path = os.path.join(output_dir, f"img_{xref}.jpg")
        pix.save(output_path, output="jpeg", jpg_quality=95)

    def _extract_webp(
        self, doc: pymupdf.Document, xref: int, output_dir: str
    ) -> None:
        """Extract image converted to WebP via Pillow."""
        pix = pymupdf.Pixmap(doc, xref)

        # Convert CMYK to RGB if needed
        if pix.n - pix.alpha > 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

        mode = "RGBA" if pix.alpha else "RGB"
        img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)

        output_path = os.path.join(output_dir, f"img_{xref}.webp")
        img.save(output_path, "WEBP", quality=90)
