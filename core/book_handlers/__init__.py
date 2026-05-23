"""Registry of book-specific extraction handlers.

HOW TO REGISTER A NEW BOOK
----------------------------
1.  Write your handler in core/book_handlers/yourbook.py
    (copy dolmenwood.py as a starting point).

2.  Import it here and append an instance to HANDLERS:

        from core.book_handlers.yourbook import YourBookHandler
        HANDLERS.append(YourBookHandler())

3.  Done.  The application checks HANDLERS in order and uses the first
    handler whose detect() method returns True.

DETECTION ORDER
----------------
Handlers are checked in the order they appear in HANDLERS.  If two
books could conceivably be confused, put the more specific one first.
In practice this is unlikely to matter, but worth knowing.
"""

from __future__ import annotations

import pymupdf

from core.book_handlers.base import BookHandler
from core.book_handlers.dolmenwood import DolmenwoodHandler

# ── Add new handlers here ─────────────────────────────────────────────────────
HANDLERS: list[BookHandler] = [
    DolmenwoodHandler(),
    # YourBookHandler(),   ← add future entries here
]
# ─────────────────────────────────────────────────────────────────────────────


def get_handler(doc: pymupdf.Document) -> BookHandler | None:
    """Return the first handler that recognises *doc*, or None.

    Called on the main thread every time the user clicks Extract Text,
    so every handler's detect() must be fast (plain-text scan of a few
    pages is fine; image rendering is not).
    """
    for handler in HANDLERS:
        if handler.detect(doc):
            return handler
    return None
