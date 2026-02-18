"""PDF document loading, thumbnail generation, and page access."""

import logging
from pathlib import Path

import pymupdf
from PIL import Image

log = logging.getLogger(__name__)


class PDFHandler:
    """Manages PDF document loading and page access."""

    def __init__(self, filepath: str):
        """Open PDF document. Raises ValueError for invalid/encrypted PDFs."""
        self._filepath = filepath
        self._path = Path(filepath)

        try:
            self._doc = pymupdf.open(filepath)
        except Exception as exc:
            raise ValueError(f"PDF file is corrupted or cannot be read.\n{exc}") from exc

        if self._doc.is_encrypted:
            self._doc.close()
            raise ValueError(
                "PDF is password-protected. Password-protected PDFs "
                "are not supported in this version."
            )

        if not self._doc.is_pdf:
            self._doc.close()
            raise ValueError("Selected file is not a valid PDF.")

    @property
    def filepath(self) -> str:
        """Return the original file path."""
        return self._filepath

    @property
    def filename(self) -> str:
        """Return the filename without path (e.g., 'document.pdf')."""
        return self._path.name

    @property
    def stem(self) -> str:
        """Return the filename without extension (e.g., 'document')."""
        return self._path.stem

    @property
    def page_count(self) -> int:
        """Return total number of pages."""
        return len(self._doc)

    @property
    def document(self) -> pymupdf.Document:
        """Return the underlying pymupdf.Document for direct access."""
        return self._doc

    def get_page(self, page_num: int) -> pymupdf.Page:
        """Get page object for the given 0-based page index."""
        return self._doc[page_num]

    def get_thumbnail(self, page_num: int, width: int = 120, height: int = 160,
                       hidpi: bool = False) -> Image.Image:
        """Generate thumbnail PIL Image for the given 0-based page index.

        The returned image is sized to fit within width x height while preserving
        aspect ratio.  Set hidpi=True to render at 2x for preview quality.
        """
        page = self._doc[page_num]
        scale = 2 if hidpi else 1
        target_w = width * scale
        target_h = height * scale

        # Calculate zoom to fit within target dimensions
        page_rect = page.rect
        zoom_x = target_w / page_rect.width
        zoom_y = target_h / page_rect.height
        zoom = min(zoom_x, zoom_y)

        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False, annots=False)

        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return img

    def close(self):
        """Close PDF document and release resources."""
        if self._doc and not self._doc.is_closed:
            self._doc.close()
