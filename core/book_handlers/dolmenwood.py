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
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import pymupdf

from core.book_handlers.base import BookHandler
from core.text_extractor import _title_case

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
_CENTRE_MIN_FRAC  = 0.13   # description x0 must be > pw*0.13
_CENTRE_MAX_FRAC  = 0.87   # description x1 must be < pw*0.87

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

    def transform_xhtml_page(self, xhtml_content: str) -> str:
        return restructure_hex_page(xhtml_content)

    @property
    def supports_fvtt(self) -> bool:
        return True

    def build_default_profile(self, doc: pymupdf.Document):
        """Return an ExtractionProfile tuned for the Dolmenwood Campaign Book.

        Three sections:
          pre-hex  (pages before Part Six)  — TOC level 2 grouping
          hex      (Part Six pages)         — one journal page per PDF page,
                                              with XHTML restructuring applied
          post-hex (pages after Part Six)   — TOC level 2 grouping

        Link rules:
          p. N     → Foundry link to the journal page that contains PDF page N
          hex NNNN → Foundry link to the hex-description journal page
        """
        from core.extraction_profile import (
            ExtractionProfile, SectionRule, LinkRule,
        )

        start, end = self._find_hex_range(doc)
        sections = []

        if start > 0:
            sections.append(SectionRule(
                name="Pre-Hex Content",
                page_start=0,
                page_end=start - 1,
                strategy="toc",
                toc_level=2,
                transform=False,
            ))

        if start != -1:
            hex_end = end - 1   # _find_hex_range returns exclusive end
            sections.append(SectionRule(
                name="Hex Descriptions",
                page_start=start,
                page_end=hex_end,
                strategy="page",
                transform=True,
            ))
            if hex_end + 1 < doc.page_count:
                sections.append(SectionRule(
                    name="Appendices",
                    page_start=hex_end + 1,
                    page_end=doc.page_count - 1,
                    strategy="toc",
                    toc_level=2,
                    transform=False,
                ))
        else:
            sections.append(SectionRule(
                name="Content",
                page_start=0,
                page_end=doc.page_count - 1,
                strategy="toc",
                toc_level=2,
                transform=False,
            ))

        return ExtractionProfile(
            journal_name="Dolmenwood Campaign Book",
            sections=sections,
            link_rules=[
                LinkRule(r"\bp\.?\s*(\d+)", "pdf_page", group=1),
                LinkRule(r"(?i)hex\s+(\d{4})", "semantic_key",
                         group=1, key_type="hex_number"),
            ],
        )

    def stem_to_title(self, stem: str) -> str:
        """Convert 'Hex_0508_The_Skeletal_Gardener' → 'The Skeletal Gardener (Hex 0508)'."""
        m = re.match(r'^Hex_(\d{4})_(.*)', stem)
        if m:
            name = m.group(2).replace("_", " ")
            return f"{name} (Hex {m.group(1)})"
        return stem.replace("_", " ")

    def stem_to_semantic_keys(self, stem: str) -> dict[str, str]:
        """Extract hex number from 'Hex_0508_…' for semantic link resolution."""
        m = re.match(r'^Hex_(\d{4})_', stem)
        return {"hex_number": m.group(1)} if m else {}

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
    titled = _title_case(description)
    safe = _UNSAFE_CHARS_RE.sub('', titled)
    underscored = re.sub(r'\s+', '_', safe)
    clean = re.sub(r'_+', '_', underscored).strip('_')
    return f"Hex_{hex_num}_{clean}"


# ── XHTML hex page parsing ────────────────────────────────────────────────────

_XHTML_NS = "http://www.w3.org/1999/xhtml"
_NS = f"{{{_XHTML_NS}}}"

_TAG_P   = f"{_NS}p"
_TAG_H1  = f"{_NS}h1"
_TAG_H2  = f"{_NS}h2"
_TAG_H3  = f"{_NS}h3"
_TAG_B   = f"{_NS}b"
_TAG_BR  = f"{_NS}br"
_TAG_IMG = f"{_NS}img"
_TAG_DIV = f"{_NS}div"

# Aspect ratio (width ÷ height) at or above which an image is the hex map.
# The hex map is roughly square; full-page illustrations are portrait-oriented.
_HEX_MAP_MIN_RATIO = 0.85

# Strip DOCTYPE before ET parsing; ET does not support external DTD references.
_DOCTYPE_RE = re.compile(r'<!DOCTYPE[^>]*>', re.DOTALL)

# The geographic-info paragraph starts with one of these strings.
_GEO_STARTS = ("Terrain:", "Terrain ")


@dataclass
class HexPageElements:
    """Structural components of a single Dolmenwood hex page.

    Fields that could not be identified are None (scalars) or [] (lists).
    All Element fields are live references into the same parsed tree, so
    modifying them and re-serialising doc_root reflects every change.

    Fields:
        doc_root        — the <html> root of the full parsed document
        page_div        — the <div id="page0"> containing all page content
        page_number     — folio page number string, e.g. "243"
        hex_number      — 4-digit hex code string, e.g. "0508"
        hex_name        — <h2> element containing the hex title
        hex_description — first substantial <p> after hex_name;
                          text may be doubled (see get_description_text)
        geographic_info — <p> element starting with "Terrain:"
        hex_map         — <p> containing the roughly-square hex-grid image
        features        — interleaved <h3>/<p> elements for all hex features
                          in document order
        other_images    — <p> elements containing portrait-format illustrations
        unclassified    — elements that matched no identification rule
    """
    doc_root: ET.Element
    page_div: ET.Element
    page_number: str | None
    hex_number: str | None
    hex_name: ET.Element | None
    hex_description: ET.Element | None
    geographic_info: ET.Element | None
    hex_map: ET.Element | None
    features: list[ET.Element]
    other_images: list[ET.Element]
    unclassified: list[ET.Element]


def parse_hex_page(xhtml_content: str) -> HexPageElements:
    """Identify the structural components of a Dolmenwood hex page XHTML file.

    *xhtml_content* is the full text of a single-page XHTML file produced
    by the extractor.  Returns a HexPageElements dataclass.

    Detection rules applied to each direct child of <div id="page0">:

      page_number    — <p> whose complete inner text is 1–4 digits
      hex_number     — <h1> whose inner text contains a 4-digit number
      hex_name       — first <h2> in the div
      hex_description — first substantial <p> (>20 chars) after the <h2>
                        that is not an image paragraph or the geographic line
      geographic_info — <p> whose inner text begins with "Terrain:"
      hex_map        — first <p><img> with width÷height ≥ _HEX_MAP_MIN_RATIO
      features       — all <h3> elements and remaining <p> elements after <h2>
      other_images   — <p><img> elements with portrait-format ratio
      unclassified   — any element that matched none of the above
    """
    content = _DOCTYPE_RE.sub('', xhtml_content, count=1)
    ET.register_namespace('', _XHTML_NS)
    doc_root = ET.fromstring(content)

    div = doc_root.find(f'.//{_TAG_DIV}[@id="page0"]')
    if div is None:
        raise ValueError("No <div id='page0'> found in XHTML content")

    page_number: str | None = None
    hex_number: str | None = None
    hex_name_el: ET.Element | None = None
    hex_desc_el: ET.Element | None = None
    geo_el: ET.Element | None = None
    hex_map_el: ET.Element | None = None
    features: list[ET.Element] = []
    other_images: list[ET.Element] = []
    unclassified: list[ET.Element] = []

    hex_name_found = False
    hex_desc_found = False

    for child in div:
        tag = child.tag
        text = ''.join(child.itertext()).strip()

        if tag == _TAG_P:
            # Page number: pure digits, ≤4 chars, before the hex name heading
            if not hex_name_found and not page_number and re.fullmatch(r'\d{1,4}', text):
                page_number = text
                continue

            # Image paragraph: classify by width-to-height aspect ratio
            img = child.find(_TAG_IMG)
            if img is not None:
                try:
                    ratio = int(img.get('width', 0)) / int(img.get('height', 1))
                except (ValueError, ZeroDivisionError):
                    ratio = 0.0
                if ratio >= _HEX_MAP_MIN_RATIO and hex_map_el is None:
                    hex_map_el = child
                else:
                    other_images.append(child)
                continue

            # Geographic info: inner text starts with "Terrain:"
            if any(text.startswith(s) for s in _GEO_STARTS):
                geo_el = child
                continue

            # Hex description: first substantial <p> after the hex name
            if hex_name_found and not hex_desc_found and len(text) > 20:
                hex_desc_el = child
                hex_desc_found = True
                continue

            if hex_name_found:
                features.append(child)
            else:
                unclassified.append(child)

        elif tag == _TAG_H1:
            m = re.search(r'\d{4}', text)
            if m:
                hex_number = m.group()
            else:
                unclassified.append(child)

        elif tag == _TAG_H2:
            if not hex_name_found:
                hex_name_el = child
                hex_name_found = True
            else:
                features.append(child)

        elif tag == _TAG_H3:
            if hex_name_found:
                features.append(child)
            else:
                unclassified.append(child)

        else:
            unclassified.append(child)

    return HexPageElements(
        doc_root=doc_root,
        page_div=div,
        page_number=page_number,
        hex_number=hex_number,
        hex_name=hex_name_el,
        hex_description=hex_desc_el,
        geographic_info=geo_el,
        hex_map=hex_map_el,
        features=features,
        other_images=other_images,
        unclassified=unclassified,
    )


def get_description_text(el: ET.Element) -> str:
    """Return the deduplicated text of a hex description element.

    PyMuPDF sometimes emits the hex description paragraph twice in a single
    <p> element (a known rendering artifact where the text appears once for
    each rendering layer).  When the inner text is an exact repetition of
    itself (separated by 0–2 characters), only the first copy is returned.
    Text that is not duplicated is returned unchanged.
    """
    text = ''.join(el.itertext()).strip()
    n = len(text)
    for sep_len in range(3):   # allow 0, 1, or 2 separator chars between copies
        half = (n - sep_len) // 2
        if half > 10 and 2 * half + sep_len == n and text[:half] == text[half + sep_len:]:
            return text[:half]
    return text


def _split_geo_sections(geo_el: ET.Element) -> ET.Element:
    """Return a single <p> with geographic sections separated by <br/> line breaks.

    Section labels (Terrain:, Lost/encounters:, Foraging:, etc.) are bold
    elements whose complete text ends with ':'.  Non-label bold text (monster
    names, item names) is left inside its section.  A <br/> is inserted
    immediately before each new section label so sections share one paragraph
    block with only a line-break between them (no paragraph spacing).

    Multi-element labels such as "Within the Ring of Chell (<i>p20</i>):"
    are handled naturally: only the final <b> ends with ':', so the preceding
    elements accumulate into the same section until the ':' is seen.
    """
    children = list(geo_el)

    # Identify child indices where a new section begins (a label after a prior label).
    section_breaks: set[int] = set()
    label_seen = False
    for i, child in enumerate(children):
        child_inner = ''.join(child.itertext()).strip()
        child_tail = (child.tail or '').strip()
        is_label = (child.tag == _TAG_B and child_inner.endswith(':')
                    and child_tail and child_inner[:1].isalpha())
        if is_label and label_seen:
            section_breaks.add(i)
        if is_label:
            label_seen = True

    result = ET.Element(_TAG_P)
    if geo_el.text and geo_el.text.strip():
        result.text = geo_el.text

    for i, child in enumerate(children):
        if i in section_breaks:
            result.append(ET.Element(_TAG_BR))
        result.append(child)

    return result


# Matches the start of a bold-numbered table row: <b>1 …, <b>12 …, <b>3. …
# (digit(s) immediately followed by a space or period inside a <b> tag).
_TABLE_ROW_B_RE = re.compile(r'<b[^>]*>\d{1,2}[\s.]')

# Matches the redundant column-header paragraph PyMuPDF emits above each table,
# e.g. <p><b>d6 Room</b></p> or <p><b>d8 Encounter</b></p>.
_TABLE_HEADER_P_RE = re.compile(r'<p[^>]*><b[^>]*>d\d+\s+\w+</b></p>\s*')

# Matches any <p> element (lazy, dotall).
_ANY_P_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.DOTALL)


def _split_table_paragraphs(html: str) -> str:
    """Split run-on table paragraphs into one <p> per row.

    PyMuPDF collapses multi-row tables into a single <p> where each row
    begins with a bold numbered entry such as <b>1 Study.</b>.  This
    function detects that pattern (≥2 numbered bold entries in one <p>)
    and splits it into individual paragraphs, one per row.

    The redundant column-header paragraph (e.g. <p><b>d6 Room</b></p>)
    that PyMuPDF emits immediately before the data paragraph is also removed.
    """
    # Remove the column-header paragraphs first.
    html = _TABLE_HEADER_P_RE.sub('', html)

    def _try_split(m: re.Match) -> str:
        inner = m.group(1)
        starts = [sm.start() for sm in _TABLE_ROW_B_RE.finditer(inner)]
        if len(starts) < 2:
            return m.group(0)   # not a table paragraph — leave unchanged
        parts = []
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(inner)
            parts.append(inner[start:end].rstrip())
        return '\n'.join(f'<p>{p}</p>' for p in parts if p)

    return _ANY_P_RE.sub(_try_split, html)


def restructure_hex_page(xhtml_content: str) -> str:
    """Reorder a Dolmenwood hex page XHTML into canonical reading order.

    Output order:
      1. <h2> title: "<hex name> – Hex <hex number>  Page <page number>"
      2. <p> hex description (with PyMuPDF's text-doubling artifact removed)
      3. <p> hex map image
      4. One <p> per labeled geographic section (Terrain:, Lost/encounters:, …)
      5. All remaining elements (features, other images, unclassified) in their
         original document order.

    Pages that cannot be identified as hex pages (no hex_number detected) are
    returned unchanged so non-hex pages in the same extraction pass are safe.
    """
    els = parse_hex_page(xhtml_content)
    if els.hex_number is None:
        return xhtml_content

    div = els.page_div

    # Build the set of elements that move to a fixed new position.
    consumed: set[int] = set()
    for child in div:
        if child.tag == _TAG_H1:
            consumed.add(id(child))
        elif child.tag == _TAG_P and ''.join(child.itertext()).strip() == (els.page_number or ''):
            consumed.add(id(child))
    for el in (els.hex_name, els.hex_description, els.geographic_info, els.hex_map):
        if el is not None:
            consumed.add(id(el))

    new_children: list[ET.Element] = []

    # 1. Title
    title = ET.Element(_TAG_H2)
    b = ET.SubElement(title, _TAG_B)
    name_text = _title_case(''.join(els.hex_name.itertext()).strip()) if els.hex_name is not None else ''
    b.text = f"{name_text} – Hex {els.hex_number} Page {els.page_number or '?'}"
    new_children.append(title)

    # 2. Hex description (deduplicated)
    if els.hex_description is not None:
        if len(els.hex_description) == 0:   # plain-text <p>: safe to overwrite .text
            els.hex_description.text = get_description_text(els.hex_description)
        new_children.append(els.hex_description)

    # 3. Hex map
    if els.hex_map is not None:
        new_children.append(els.hex_map)

    # 4. Geographic info: one <p> with <br/> between sections
    if els.geographic_info is not None:
        new_children.append(_split_geo_sections(els.geographic_info))

    # 5. Everything else in original document order
    for child in div:
        if id(child) not in consumed:
            new_children.append(child)

    # Replace the div's children in place (doc_root tree is updated automatically)
    for child in list(div):
        div.remove(child)
    for child in new_children:
        div.append(child)

    # Re-serialise, restoring the XML/DOCTYPE prolog that ET stripped
    html_idx = xhtml_content.find('<html')
    prolog = xhtml_content[:html_idx] if html_idx != -1 else ''
    return prolog + ET.tostring(els.doc_root, encoding='unicode')
