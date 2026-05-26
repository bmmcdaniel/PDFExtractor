"""Abstract base class for book-specific extraction handlers.

HOW TO ADD A NEW BOOK
---------------------
1.  Create a new file: core/book_handlers/yourbook.py
2.  Import and subclass BookHandler.
3.  Implement the three required members: `name`, `detect()`, and
    `build_filename_map()`.  Override `detection_message` if you want
    custom dialog text.
4.  In core/book_handlers/__init__.py, import your class and append an
    instance to HANDLERS.

That's it.  The rest of the application (app.py, dialogs.py, text_extractor.py)
requires no changes.

WHAT `build_filename_map` MUST RETURN
--------------------------------------
A dict mapping PDF page index (0-based) to a *partial* filename stem.
The caller prepends the user's chosen base name automatically, so your
stem should NOT include it.

    Good:  {191: "Hex_0101_The_Spectral_Manse"}
           → final file: "DCB_Hex_0101_The_Spectral_Manse.xhtml"

    Bad:   {191: "DCB_Hex_0101_The_Spectral_Manse"}
           → final file: "DCB_DCB_Hex_0101_The_Spectral_Manse.xhtml"

Pages absent from the dict fall back to the default sequential name
(e.g. "DCB_001.xhtml"), so you only need to return entries for pages
that deserve a special name.

WHAT `detect` MUST DO
----------------------
Return True as quickly and cheaply as possible — it is called on the
main thread every time the user clicks "Extract Text".  Reading a few
pages of plain text (via doc[i].get_text("text")) is fine.  Avoid
anything that loads images, renders pages, or walks many hundreds of
pages.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pymupdf


class BookHandler(ABC):
    """Contract that every book-specific handler must satisfy."""

    # ------------------------------------------------------------------
    # Required — subclasses MUST implement these.
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable book title shown in the detection dialog.

        Keep it short and unambiguous, e.g. "Dolmenwood Campaign Book".
        """

    @abstractmethod
    def detect(self, doc: pymupdf.Document) -> bool:
        """Return True if *doc* appears to be this specific book.

        Tip: search for a combination of strings that is unique to this
        book — e.g. title + subtitle on the first few pages.  Use
        case-insensitive matching in case the PDF has unexpected casing.
        """

    @abstractmethod
    def build_filename_map(
        self, doc: pymupdf.Document, pages: list[int]
    ) -> dict[int, str]:
        """Return a mapping of page index → partial filename stem.

        Only include pages that deserve a non-default name.  Pages not
        in the returned dict will be named sequentially by the caller.

        The stem must NOT include the user's base name or the file
        extension — the caller handles both.  See module docstring for
        a worked example.
        """

    # ------------------------------------------------------------------
    # Optional — subclasses MAY override these.
    # ------------------------------------------------------------------

    @property
    def detection_message(self) -> str:
        """Two-line message shown in the detection dialog.

        Override this to give users book-specific context, e.g.
        "Special handling for hex pages?" rather than the generic text.
        """
        return f"{self.name} detected.\nUse special per-page file naming?"

    def transform_xhtml_page(self, xhtml_content: str) -> str:
        """Optionally restructure a per-page XHTML file after extraction.

        Called once per hex page (i.e. pages that appear in the filename_map)
        when the user has chosen special handling.  The default implementation
        is a no-op; override to reorder elements, fix duplicated text, etc.

        *xhtml_content* is a complete, well-formed XHTML document string.
        Return the transformed string (or *xhtml_content* unchanged if no
        transformation applies to this particular page).
        """
        return xhtml_content

    @property
    def supports_fvtt(self) -> bool:
        """Return True if this handler supports Foundry VTT journal export."""
        return False

    def build_default_profile(self, doc: pymupdf.Document):
        """Return a default ExtractionProfile for *doc*, or None.

        Override to provide a book-specific profile with correct section
        boundaries and link rules.  Return None to fall back to the
        UI-driven TOC-level selection.

        Import ExtractionProfile inside the method body to avoid a circular
        import at module load time.
        """
        return None

    def stem_to_title(self, stem: str) -> str:
        """Convert a filename stem to a human-readable journal page title.

        Called for every page that has a filename_map entry when building
        journal groups for FVTT output.  Override to produce a title that
        fits the book's naming convention.

        Default: replace underscores with spaces.
        """
        return stem.replace("_", " ")

    def stem_to_semantic_keys(self, stem: str) -> dict[str, str]:
        """Extract semantic link keys from a filename stem.

        Returns a dict mapping key_type → key_value.  These entries are
        collected into a semantic index used by resolve_links() to resolve
        "@semantic_key" link rules in the profile.

        Default: no semantic keys (empty dict).
        """
        return {}
