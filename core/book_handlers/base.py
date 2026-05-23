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
    # Optional — subclasses MAY override this.
    # ------------------------------------------------------------------

    @property
    def detection_message(self) -> str:
        """Two-line message shown in the detection dialog.

        Override this to give users book-specific context, e.g.
        "Special handling for hex pages?" rather than the generic text.
        """
        return f"{self.name} detected.\nUse special per-page file naming?"
