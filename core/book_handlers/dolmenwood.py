"""Book handler for the Dolmenwood Campaign Book (Necrotic Gnome).

This module is a self-contained example of how to implement BookHandler
for a real product.  Read the comments to understand which parts are
Dolmenwood-specific and which are patterns you can copy when adding a
new book.

WHAT MAKES THIS BOOK SPECIAL
------------------------------
Pages 192–391 (1-based) form the "Hex Descriptions" section.  Each page
describes one hex of the game map.  The hex number (e.g. "0101") and hex
name (e.g. "THE SPECTRAL MANSE") appear in the page header.  We use
those to build a meaningful filename such as:

    DCB_Hex_0101_The_Spectral_Manse.xhtml

instead of the generic sequential name DCB_192.xhtml.

HOW THE DETECTION WORKS
------------------------
We search the first 10 pages for two strings that together uniquely
identify this book:
  - "campaign book"
  - "adventure and peril in fairytale woods"

Both checks are case-insensitive.  When adapting for another book,
replace these with strings that appear together only in that title.
Two strings are usually enough to avoid false positives; avoid strings
so common they could appear in unrelated documents.

HOW THE HEX SECTION IS LOCATED
--------------------------------
We scan every page and compare its first line of text to "part six" and
"part seven" (case-insensitive).  The section divider pages start with
exactly those strings, so a first-line match is specific enough to
avoid false positives from cross-references in body text.

For another book you would replace "part six" / "part seven" with
whatever structural markers delimit the section you care about.  If
your book uses page numbers to bound the section you can hard-code
them, but first-line / structural detection is more robust across
revised editions.

HOW HEX INFO IS EXTRACTED FROM EACH PAGE
------------------------------------------
Both even (left-hand) and odd (right-hand) pages carry:
  - The hex number ("0101") in a large font (≥16 pt) near the top
    (y < 60 pt), hugging the outer edge (left edge on even pages,
    right edge on odd pages).
  - The hex name ("THE SPECTRAL MANSE") in a medium font (13–18 pt)
    near the top (y < 60 pt), horizontally centred.

We use PyMuPDF's get_text("dict") to read each span's bounding box and
font size and apply simple threshold tests.  When adapting for another
book, inspect your book's pages with get_text("dict") to find the
bounding-box / size signatures of whatever per-page identifiers you
want to extract.
"""

from __future__ import annotations

import re

import pymupdf

from core.book_handlers.base import BookHandler

# ── Detection ─────────────────────────────────────────────────────────────────

# Strings that together uniquely identify this book (searched case-insensitively).
# For a different book, replace these with two strings from *its* title page.
_DETECT_STRINGS = (
    "campaign book",
    "adventure and peril in fairytale woods",
)

# ── Section boundaries ────────────────────────────────────────────────────────

# We detect the hex section by comparing the first line of each page to these
# strings.  Matching only the first line avoids false positives from pages that
# cite "Part Seven" as a cross-reference in body text.
#
# For a different book, replace these with the first-line text of whatever
# section divider pages bracket your special section.
_SECTION_START_FIRST_LINE = "part six"    # section divider before hex pages
_SECTION_END_FIRST_LINE   = "part seven"  # section divider after hex pages

# ── Per-page header extraction ────────────────────────────────────────────────

# Matches a standalone 4-digit hex number such as "0101".
# For a different book, replace with whatever pattern your page identifiers
# follow (e.g. a chapter number, a monster ID, etc.).
_HEX_NUM_RE = re.compile(r'^\d{4}$')

# Font-size thresholds (in points) for identifying header elements.
# Inspect your book's pages with get_text("dict") to calibrate these.
_HEX_NUM_MIN_SIZE  = 16   # hex numbers are printed at ~20 pt
_DESC_MIN_SIZE     = 13   # descriptions are printed at ~16.6 pt
_DESC_MAX_SIZE     = 18

# Fraction of page width used to decide "left edge", "right edge", "centre".
# The hex number sits in the outer margin; the description is centred.
_EDGE_FRACTION    = 0.35   # x < pw*0.35 → left edge; x > pw*0.65 → right edge
_CENTRE_MIN_FRAC  = 0.15   # description x0 must be > pw*0.15
_CENTRE_MAX_FRAC  = 0.85   # description x1 must be < pw*0.85

# Vertical limit: only examine text in the top 60 pt of the page.
_HEADER_MAX_Y = 60

# ── Typographic normalisation ─────────────────────────────────────────────────

# PDFs often contain Unicode typographic characters (curly quotes, em-dashes)
# or their Windows-1252 equivalents.  We replace them with plain ASCII so that
# filenames are consistent across operating systems.
#
# Extend this table if your book uses other special characters.
_NORMALISE = str.maketrans({
    '\x91': "'", '\x92': "'",       # CP-1252 left/right single quotes
    '\x93': '"', '\x94': '"',       # CP-1252 left/right double quotes
    '\x96': '-', '\x97': '-',       # CP-1252 en/em dash
    '\xad': '',                      # soft hyphen → remove
    '‘': "'", '’': "'",   # Unicode curly single quotes
    '“': '"', '”': '"',   # Unicode curly double quotes
    '–': '-', '—': '-',   # Unicode en/em dash
})

# Characters that are illegal in Windows filenames (and several other OS).
_UNSAFE_CHARS_RE = re.compile(r'[\x00-\x1f\x7f-\x9f\\/:*?"<>|]')


# ── Handler class ─────────────────────────────────────────────────────────────

class DolmenwoodHandler(BookHandler):
    """BookHandler for the Dolmenwood Campaign Book."""

    # ── BookHandler interface ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "Dolmenwood Campaign Book"

    @property
    def detection_message(self) -> str:
        return "Dolmenwood Campaign Book detected.\nSpecial handling for hex pages?"

    def detect(self, doc: pymupdf.Document) -> bool:
        """Return True if the first 10 pages contain both detection strings."""
        for i in range(min(10, doc.page_count)):
            text = doc[i].get_text("text").lower()
            if all(s in text for s in _DETECT_STRINGS):
                return True
        return False

    def build_filename_map(
        self, doc: pymupdf.Document, pages: list[int]
    ) -> dict[int, str]:
        """Return {page_idx: "Hex_NNNN_Title"} for hex pages in *pages*.

        Pages outside the hex section or within it but lacking a
        detectable hex header (e.g. full-page illustrations) are absent
        from the returned dict — the caller falls back to sequential
        naming for those.
        """
        start, end = self._find_hex_range(doc)
        if start == -1:
            return {}
        result: dict[int, str] = {}
        for page_idx in pages:
            if start <= page_idx < end:
                info = self._extract_hex_info(doc[page_idx])
                if info:
                    result[page_idx] = _make_stem(*info)
        return result

    # ── Private helpers ────────────────────────────────────────────────────

    def _find_hex_range(self, doc: pymupdf.Document) -> tuple[int, int]:
        """Locate the Hex Descriptions section by its divider pages.

        Returns (start_idx, end_idx) where start_idx is the page
        immediately after the Part Six divider and end_idx is the
        Part Seven divider page (exclusive).  Returns (-1, page_count)
        if the section is not found.

        Why first-line matching?  Pages within the section cite "Part
        Seven" as a cross-reference, so a full-text search yields false
        positives.  The actual divider pages start with exactly "Part
        Six" / "Part Seven" and nothing else precedes that text.
        """
        start = -1
        end = doc.page_count
        for i in range(doc.page_count):
            first_line = doc[i].get_text("text").split('\n', 1)[0].strip().lower()
            if start == -1 and first_line == _SECTION_START_FIRST_LINE:
                start = i + 1   # hex pages begin on the page after the divider
            elif start != -1 and first_line == _SECTION_END_FIRST_LINE:
                end = i         # hex pages end before the Part Seven divider
                break
        return start, end

    def _extract_hex_info(
        self, page: pymupdf.Page
    ) -> tuple[str, str] | None:
        """Return (hex_number, description) from the page header, or None.

        Layout (mirrored on odd/even pages):
          Even (left-hand):  hex number at top-LEFT, description centred.
          Odd  (right-hand): hex number at top-RIGHT, description centred.

        We identify each element by a combination of:
          • vertical position  (y < _HEADER_MAX_Y)
          • font size          (large for number, medium for description)
          • horizontal zone    (outer edge vs. centre)

        If either element cannot be found the page is treated as having
        no special header (e.g. a full-page illustration) and None is
        returned.
        """
        pw = page.rect.width
        hex_num: str | None = None
        desc_spans: list[tuple[float, str]] = []   # (x0, text) for left→right ordering

        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:   # skip image blocks
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    # Normalise typographic characters before any further use.
                    txt = span["text"].translate(_NORMALISE).strip()
                    if not txt:
                        continue

                    bbox = span["bbox"]
                    y0, size = bbox[1], span["size"]
                    x0, x1  = bbox[0], bbox[2]

                    if y0 > _HEADER_MAX_Y:
                        continue   # below the header band — skip

                    if size >= _HEX_NUM_MIN_SIZE and _HEX_NUM_RE.match(txt):
                        # Large font, 4-digit text, at the outer page edge.
                        if x1 < pw * _EDGE_FRACTION or x0 > pw * (1 - _EDGE_FRACTION):
                            hex_num = txt

                    elif (_DESC_MIN_SIZE <= size < _DESC_MAX_SIZE
                          and not _HEX_NUM_RE.match(txt)
                          and x0 > pw * _CENTRE_MIN_FRAC
                          and x1 < pw * _CENTRE_MAX_FRAC):
                        # Medium-large font, not a hex number, horizontally centred.
                        desc_spans.append((x0, txt))

        if not hex_num or not desc_spans:
            return None

        # Sort left→right in case the title wraps across multiple spans.
        desc_spans.sort()
        description = ' '.join(t for _, t in desc_spans).strip()
        return hex_num, description


# ── Filename builder ──────────────────────────────────────────────────────────

def _make_stem(hex_num: str, description: str) -> str:
    """Build a filesystem-safe partial stem: Hex_0101_The_Spectral_Manse.

    Steps:
      1. Apply Python's str.title() for title-case capitalisation.
         (Note: str.title() is naive — letters after any non-alpha
          character are uppercased, e.g. "O'Brien" → "O'Brien".)
      2. Strip control characters and Windows-unsafe filename characters.
      3. Replace runs of whitespace with underscores.
      4. Prepend "Hex_" and the hex number.

    For a different book, rename the prefix ("Hex_") and adjust the
    formatting to match whatever identifier pattern that book uses.
    """
    titled = description.title()
    safe = _UNSAFE_CHARS_RE.sub('', titled)
    underscored = re.sub(r'\s+', '_', safe)
    clean = re.sub(r'_+', '_', underscored).strip('_')
    return f"Hex_{hex_num}_{clean}"
