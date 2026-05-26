"""DCB-specific multi-journal Foundry VTT export.

Produces one JSON file per Part-level (level-1) TOC entry, with:
  - Level-2 TOC entries mapping to individual journal pages
  - Hex pages (Part Six) producing one journal page per PDF page
  - Images extracted to disk and referenced by Foundry /user-data/ URL
  - Cross-journal @UUID links for page-number and hex-number references
  - A generated import macro (import_dcb.js)

Output structure under {foundry_data_path}/dcb/:
  Part_One_Secrets_of_Dolmenwood.json
  Part_Two_...json
  ...
  images/
    p0191_00.png   (page 191, image 0)
    ...
  import_dcb.js
"""

from __future__ import annotations

import base64
import json
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pymupdf

from core.extraction_profile import LinkRule
from core.text_extractor import (
    _extract_page_div_content,
    _normalize_xhtml_headers,
    _sanitize_xml,
    _strip_soft_hyphens,
)
from core.book_handlers.dolmenwood import restructure_hex_page, _split_table_paragraphs


# ── Utilities ──────────────────────────────────────────────────────────────────

def _make_id() -> str:
    return secrets.token_hex(8)


def _slugify(title: str) -> str:
    """Convert a journal title to a safe filename stem (max 80 chars)."""
    slug = re.sub(r"[^\w\s-]", "", title)
    slug = re.sub(r"[\s_]+", "_", slug.strip())
    return slug[:80]


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class _FPage:
    """One Foundry JournalEntryPage."""
    page_id: str
    title: str
    pdf_pages: list[int]                      # 0-based PDF page indices
    is_hex: bool = False
    semantic_keys: dict[str, str] = field(default_factory=dict)


@dataclass
class _FJournal:
    """One Foundry JournalEntry."""
    journal_id: str
    title: str
    pages: list[_FPage] = field(default_factory=list)


# ── TOC parsing ────────────────────────────────────────────────────────────────

def _parse_journals(
    doc: pymupdf.Document,
    pages_set: set[int],
    hex_pages: set[int],
    filename_map: dict[int, str],
    handler,                    # DolmenwoodHandler — for title/key helpers
) -> list[_FJournal]:
    """Parse the DCB TOC into Foundry journals and pages with pre-assigned IDs.

    Level-1 TOC entries → individual Foundry journals.
    Level-2 TOC entries → pages within their parent journal.
    Pages in the hex range → each PDF page becomes its own journal page.
    Pages before the first level-1 entry → a "Preface" journal (if any).
    """
    toc = doc.get_toc()  # [[level, title, page_1based], ...]

    l1_entries: list[tuple[str, int]] = [
        (title, pg - 1) for level, title, pg in toc if level == 1
    ]

    journals: list[_FJournal] = []

    # Pages before the first level-1 entry (cover, ToC pages, etc.)
    if l1_entries and l1_entries[0][1] > 0:
        pre = [p for p in range(0, l1_entries[0][1]) if p in pages_set]
        if pre:
            j = _FJournal(journal_id=_make_id(), title="Preface")
            j.pages.append(_FPage(page_id=_make_id(), title="Preface", pdf_pages=pre))
            journals.append(j)

    for ji, (l1_title, l1_start) in enumerate(l1_entries):
        journal_end = (
            l1_entries[ji + 1][1] if ji + 1 < len(l1_entries) else doc.page_count
        )

        journal = _FJournal(journal_id=_make_id(), title=l1_title)

        # Level-2 entries within this journal
        l2_entries: list[tuple[str, int]] = [
            (title, pg - 1)
            for level, title, pg in toc
            if level == 2 and l1_start <= pg - 1 < journal_end
        ]

        # Build (group_title, pdf_pages_list) tuples from level-2 entries
        if l2_entries:
            groups: list[tuple[str, list[int]]] = []
            # Pages between the level-1 start and the first level-2 entry
            pre = [p for p in range(l1_start, l2_entries[0][1]) if p in pages_set]
            if pre:
                groups.append((l1_title, pre))
            for li, (l2_title, l2_start) in enumerate(l2_entries):
                l2_end = (
                    l2_entries[li + 1][1] if li + 1 < len(l2_entries) else journal_end
                )
                grp = [p for p in range(l2_start, l2_end) if p in pages_set]
                if grp:
                    groups.append((l2_title, grp))
        else:
            # No level-2 entries: entire journal is one group
            all_pg = [p for p in range(l1_start, journal_end) if p in pages_set]
            groups = [(l1_title, all_pg)] if all_pg else []

        # Expand each group: hex pages split to individual pages; non-hex stay together
        for group_title, group_pages in groups:
            non_hex = [p for p in group_pages if p not in hex_pages]
            hex_in_group = [p for p in group_pages if p in hex_pages]

            if non_hex:
                journal.pages.append(_FPage(
                    page_id=_make_id(),
                    title=group_title,
                    pdf_pages=non_hex,
                ))

            for hp in hex_in_group:
                stem = filename_map.get(hp)
                if stem:
                    title = handler.stem_to_title(stem)
                    sem_keys = handler.stem_to_semantic_keys(stem)
                else:
                    title = f"Page {hp + 1}"
                    sem_keys = {}
                journal.pages.append(_FPage(
                    page_id=_make_id(),
                    title=title,
                    pdf_pages=[hp],
                    is_hex=True,
                    semantic_keys=sem_keys,
                ))

        if journal.pages:
            journals.append(journal)

    return journals


# ── Split-heading merge ───────────────────────────────────────────────────────

_STRIP_TAGS_RE = re.compile(r'<[^>]+>')

# Matches two consecutive headings of the same level with no intervening block.
# Used to detect headings that PyMuPDF split across layout lines (the first
# element ends with a trailing newline or space from the PDF line-wrap point).
_SAME_LEVEL_H_PAIR_RE = re.compile(
    r'<(h[1-6])([^>]*)>(.*?)</\1>\s*<\1[^>]*>(.*?)</\1>',
    re.DOTALL,
)


def _merge_split_headings(html: str) -> str:
    """Merge consecutive same-level headings when the first ends with whitespace.

    PyMuPDF emits &#xa; (a newline XML entity) at PDF layout line-wrap points
    inside headings, then continues the heading text in a second element of the
    same level.  The result looks like::

        <h1>Welcome, Master \\n</h1><h1>Of Dolmens</h1>

    which renders as two headings instead of one.  When the first heading's
    plain text ends with whitespace the two are merged into a single element.
    Runs until stable so three-part splits are also handled.
    """
    def _replace(m: re.Match) -> str:
        tag, attrs = m.group(1), m.group(2)
        first_inner, second_inner = m.group(3), m.group(4)
        first_text = _STRIP_TAGS_RE.sub('', first_inner)
        # PyMuPDF encodes the line-wrap point as &#xa; (XML newline entity).
        # The entity ends with ';', so .rstrip() won't detect it — normalise first.
        first_text_norm = (first_text
                           .replace('&#xa;', '\n').replace('&#xA;', '\n')
                           .replace('&#10;', '\n'))
        if first_text_norm != first_text_norm.rstrip():   # trailing whitespace → split
            first_clean = (first_inner
                           .replace('&#xa;', '').replace('&#xA;', '').replace('&#10;', '')
                           .rstrip())
            merged = first_clean + ' ' + second_inner.strip()
            return f'<{tag}{attrs}>{merged}</{tag}>'
        return m.group(0)

    prev = None
    while prev != html:
        prev = html
        html = _SAME_LEVEL_H_PAIR_RE.sub(_replace, html)
    return html


# ── Drop-cap absorption ────────────────────────────────────────────────────────

# Pass 1: match any h1–h6 element so we can inspect its text content.
# No back-reference on the closing tag; PyMuPDF XHTML is always well-formed so
# <h1> will only ever close with </h1>, making mismatches impossible.
_DROP_CAP_H_RE = re.compile(r'<h[1-6][^>]*>(.*?)</h[1-6]>', re.DOTALL)

# Pass 2: fold the sentinel into the next block-level opening tag so that the
# drop-cap letter becomes the first character inside the paragraph.
_DROP_CAP_FOLD_RE = re.compile(
    r'<!--dropcap:([A-Za-z])-->\s*(<(?:p|h[1-6])[^>]*>)',
)


# Matches text where every character is a single letter (or |) separated by
# spaces — the signature of a spaced-letter running header from the PDF.
_SPACED_LETTERS_RE = re.compile(r'^[A-Za-z|]( {1,2}[A-Za-z|])+$')

# Matches any block-level element (p or h1–h6) with back-reference closing tag.
_BLOCK_RE = re.compile(r'<(p|h[1-6])[^>]*>(.*?)</\1>', re.DOTALL)


def _remove_running_headers(html: str) -> str:
    """Remove paragraphs and headings that are PDF running headers.

    Running headers use spaced lettering ('P a r t O n e | S e c r e t s …')
    which appears as alternating single characters and spaces.  They show up
    on every page of a section and are meaningless in a journal context.
    """
    def _replace(m: re.Match) -> str:
        text = _STRIP_TAGS_RE.sub('', m.group(2)).strip()
        return '' if _SPACED_LETTERS_RE.match(text) else m.group(0)

    return _BLOCK_RE.sub(_replace, html)


def _remove_artifact_page_numbers(html: str) -> str:
    """Remove <p> elements whose sole content is a bare page number (1–4 digits).

    PyMuPDF emits PDF running headers/footers as standalone paragraphs.  A
    <p> whose stripped inner text is entirely digits is almost certainly one
    of these artifacts.  Hex pages handle this via restructure_hex_page; this
    pass covers all other pages.
    """
    def _replace(m: re.Match) -> str:
        text = _STRIP_TAGS_RE.sub('', m.group(1)).strip()
        return '' if re.fullmatch(r'\d{1,4}', text) else m.group(0)

    return re.sub(r'<p[^>]*>(.*?)</p>', _replace, html, flags=re.DOTALL)


def _absorb_drop_caps(html: str) -> str:
    """Fold single-letter headings (drop caps) into the following block element.

    PyMuPDF classifies large decorative first-letters as <h1>/<h2> because of
    their font size.  When a heading's text content is exactly one alpha
    character, we want to remove the heading and prepend that character to the
    next <p> or heading.

    The naive single-regex approach consumes the following opening tag in its
    match, which causes the engine to skip over a drop-cap heading when it
    immediately follows another heading (the preceding heading's match consumes
    the drop-cap heading's opening tag as its own group).  Two passes avoid this:

    Pass 1 — scan every h1–h6 independently; replace single-letter ones with
              an HTML-comment sentinel <!--dropcap:X-->.
    Pass 2 — merge each sentinel into the next block's opening tag.
    """
    def _to_sentinel(m: re.Match) -> str:
        text = _STRIP_TAGS_RE.sub('', m.group(1)).strip()
        if len(text) == 1 and text.isalpha():
            return f'<!--dropcap:{text}-->'
        return m.group(0)

    html = _DROP_CAP_H_RE.sub(_to_sentinel, html)
    return _DROP_CAP_FOLD_RE.sub(lambda m: m.group(2) + m.group(1), html)


def _deduplicate_headings(html: str) -> str:
    """Remove PyMuPDF text-doubling artifact from heading elements.

    PyMuPDF sometimes renders heading text twice inside a single element
    (one copy per rendering layer).  When the stripped inner text is an
    exact repetition of itself (separated by 0–2 characters), only the
    first copy is kept.  Inline tags in the heading are replaced by the
    plain-text first half, which is acceptable because section subtitle
    headings in the DCB are plain text.
    """
    def _dedup(m: re.Match) -> str:
        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)
        text = _STRIP_TAGS_RE.sub('', inner).strip()
        n = len(text)
        for sep_len in range(3):
            half = (n - sep_len) // 2
            if half > 10 and 2 * half + sep_len == n and text[:half] == text[half + sep_len:]:
                return open_tag + text[:half] + close_tag
        return m.group(0)

    return re.sub(r'(<h[1-6][^>]*>)(.*?)(</h[1-6]>)', _dedup, html, flags=re.DOTALL)


def _convert_italic_headings(html: str) -> str:
    """Convert heading elements whose sole content is <i>…</i> to paragraphs.

    Section-opener pages use <h2><i>decorative quote…</i></h2> for flavour
    text.  In Foundry this renders as a huge bold heading; converting to <p>
    gives body-text styling and also allows _absorb_drop_caps to fold the
    preceding single-letter drop-cap into the paragraph naturally.
    """
    def _replace(m: re.Match) -> str:
        inner = m.group(2).strip()
        if inner.startswith('<i>') and inner.endswith('</i>') and inner.count('<i>') == 1:
            return '<p>' + inner + '</p>'
        return m.group(0)

    return re.sub(r'(<h[1-6][^>]*>)(.*?)(</h[1-6]>)', _replace, html, flags=re.DOTALL)


def _fix_section_opener_headings(html: str) -> str:
    """Fix attribution and stray-punctuation headings on Part intro pages.

    After _convert_italic_headings converts the decorative quote to <p>, two
    heading artefacts remain on every Part opener:

      <h2>—attribution Name, Title</h2>  →  <p>—attribution Name, Title</p>
      <h2>"</h2>                          →  removed (stray lone punctuation
                                              from a second rendering layer)
    """
    def _replace(m: re.Match) -> str:
        inner = _STRIP_TAGS_RE.sub('', m.group(2)).strip()

        # Stray lone punctuation heading (e.g. a closing curly-quote " on its own)
        if len(inner) <= 2 and not any(c.isalnum() for c in inner):
            return ''

        # Attribution line: starts with an em-dash or en-dash
        if inner and inner[0] in '–—':
            return '<p>' + m.group(2) + '</p>'

        return m.group(0)

    return re.sub(r'(<h[1-6][^>]*>)(.*?)(</h[1-6]>)', _replace, html, flags=re.DOTALL)


# Matches <h*> whose content begins with the same 4-digit hex number twice,
# the signature of the settlement-heading doubling artifact:
# "1604 1604—isolated Village, Desc. —isolated Village, Desc."
_SETTLE_DOUBLE_HEX_RE = re.compile(
    r'(<h[1-6][^>]*>)(\d{4}) \2(.+?)(</h[1-6]>)',
    re.DOTALL,
)


def _fix_settlement_headings(html: str) -> str:
    """Collapse PyMuPDF's doubled settlement heading into a clean single copy.

    PyMuPDF doubles settlement sub-headings as "{hex} {hex}—{desc}. —{desc}."
    This collapses them to "{hex}—{desc}." by verifying the two description
    copies match and keeping only the first.
    """
    def _replace(m: re.Match) -> str:
        open_tag = m.group(1)
        hex_num  = m.group(2)
        rest     = m.group(3)   # "—isolated Village, Desc. —isolated Village, Desc."
        close_tag = m.group(4)

        sep = re.search(r'\.\s+[–—]', rest)
        if not sep:
            return m.group(0)

        first_desc  = rest[:sep.start() + 1].lstrip('–—‐‒').strip()
        second_desc = rest[sep.end():].strip().rstrip('.')

        if first_desc.rstrip('.').lower() != second_desc.lower():
            return m.group(0)

        sep_char = rest[0] if rest[0] in '–—' else '—'
        return f'{open_tag}{hex_num}{sep_char}{first_desc}{close_tag}'

    return _SETTLE_DOUBLE_HEX_RE.sub(_replace, html)


# Matches a contiguous block of 2+ numbered table-row <p> elements as produced
# by _split_table_paragraphs.  Each row begins with <b>N …</b> where N is 1–2
# digits, matching _TABLE_ROW_B_RE.
_ROW_BLOCK_RE = re.compile(
    r'(?:<p><b[^>]*>\d{1,2}[\s.].*?</p>[ \t]*\n?){2,}',
    re.DOTALL,
)
_ROW_INNER_RE = re.compile(r'<p>(<b[^>]*>(\d{1,2})[\s.].*?)</p>', re.DOTALL)


def _sort_interleaved_table_rows(html: str) -> str:
    """Re-sort table rows that _split_table_paragraphs emitted in two-column order.

    PyMuPDF reads a two-column encounter table left-to-right within each PDF
    line, producing the interleaved sequence 1, 11, 2, 12, 3, 13 …  This
    function finds contiguous runs of numbered <p> rows that are out of
    numerical order and sorts them, restoring the natural 1, 2, 3 … sequence.
    Runs already in order are left untouched.
    """
    def _sort_block(m: re.Match) -> str:
        block = m.group(0)
        rows = _ROW_INNER_RE.findall(block)
        if not rows:
            return block
        nums = [int(r[1]) for r in rows]
        if nums == sorted(nums):
            return block                   # already in order — nothing to do
        sorted_rows = sorted(rows, key=lambda r: int(r[1]))
        return '\n'.join(f'<p>{r[0]}</p>' for r in sorted_rows)

    return _ROW_BLOCK_RE.sub(_sort_block, html)


# ── Image externalization ──────────────────────────────────────────────────────

# Matches <img ... src="data:image/TYPE;base64,DATA" ...>
# PyMuPDF emits newline-wrapped base64 (MIME line width ~76), so capture
# everything between 'base64,' and the closing quote, then strip whitespace
# before decoding.
_DATA_URI_RE = re.compile(r'src="data:image/([^;]+);base64,([^"]+)"', re.DOTALL)


def _externalize_images(
    html: str,
    images_dir: Path,
    foundry_dcb_url: str,
    page_label: str,
) -> str:
    """Decode base64 data URIs, write image files, rewrite src to /user-data/ URL.

    *foundry_dcb_url* is the full Foundry URL prefix for the dcb directory,
    e.g. '/user-data/worlds/my-world/user_data/dcb'.
    """
    counter = [0]

    def _replace(m: re.Match) -> str:
        ext = m.group(1)
        if ext == "jpeg":
            ext = "jpg"
        n = counter[0]
        counter[0] += 1
        filename = f"{page_label}_{n:02d}.{ext}"
        try:
            b64_clean = m.group(2).translate(str.maketrans('', '', ' \t\n\r'))
            (images_dir / filename).write_bytes(base64.b64decode(b64_clean))
        except Exception:
            return m.group(0)   # leave unchanged on decode error
        return f'src="{foundry_dcb_url}/images/{filename}"'

    return _DATA_URI_RE.sub(_replace, html)


# ── Cross-journal link resolution ──────────────────────────────────────────────

# Matches heading tags (h1–h6) so link rules are not applied inside headings.
_HEADING_TAG_RE = re.compile(r'(<h[1-6][^>]*>.*?</h[1-6]>)', re.DOTALL)


def _resolve_links(
    html: str,
    link_rules: list[LinkRule],
    page_id_map: dict[str, tuple[str, str]],
    semantic_index: dict[str, dict[str, tuple[str, str]]],
) -> str:
    """Replace matched text patterns with Foundry cross-journal @UUID links.

    page_id_map:    printed page label → (journal_id, page_id)
    semantic_index: key_type → {key_value → (journal_id, page_id)}

    Links are not inserted inside heading tags.
    """
    def _apply_rules(text: str) -> str:
        for rule in link_rules:
            regex = re.compile(rule.pattern)

            def _replace(m: re.Match, _rule: LinkRule = rule) -> str:
                original = m.group(0)
                key = m.group(_rule.group)
                entry = None

                if _rule.resolve == "pdf_page":
                    entry = page_id_map.get(key)   # key is the printed label, e.g. "26"
                elif _rule.resolve == "semantic_key":
                    entry = semantic_index.get(_rule.key_type, {}).get(key)

                if entry is None:
                    return original
                journal_id, page_id = entry
                return (
                    f"@UUID[JournalEntry.{journal_id}"
                    f".JournalEntryPage.{page_id}]{{{original}}}"
                )

            text = regex.sub(_replace, text)
        return text

    # Split on heading tags; apply rules only to non-heading segments.
    segments = _HEADING_TAG_RE.split(html)
    return "".join(
        seg if _HEADING_TAG_RE.fullmatch(seg) else _apply_rules(seg)
        for seg in segments
    )


# ── Hex neighbour links ────────────────────────────────────────────────────────

# Six directions clockwise from north, with column/row deltas for odd and even
# columns (odd-q offset: odd columns are shifted "up" relative to even columns).
_HEX_DIRS_ODD = [
    ("N",  ( 0, -1)),
    ("NE", (+1, -1)),
    ("SE", (+1,  0)),
    ("S",  ( 0, +1)),
    ("SW", (-1,  0)),
    ("NW", (-1, -1)),
]
_HEX_DIRS_EVEN = [
    ("N",  ( 0, -1)),
    ("NE", (+1,  0)),
    ("SE", (+1, +1)),
    ("S",  ( 0, +1)),
    ("SW", (-1, +1)),
    ("NW", (-1,  0)),
]


def _hex_neighbor_links(
    hex_num: str,
    semantic_index: dict[str, dict[str, tuple[str, str]]],
) -> str:
    """Return an HTML paragraph of neighbour links in clockwise order from N.

    Format: <p>(SE: @UUID[...]{0201}) (S: @UUID[...]{0102})</p>
    Returns an empty string if no valid neighbours exist.
    """
    col = int(hex_num[:2])
    row = int(hex_num[2:])
    dirs = _HEX_DIRS_ODD if col % 2 == 1 else _HEX_DIRS_EVEN
    hex_index = semantic_index.get("hex_number", {})

    parts: list[str] = []
    for label, (dc, dr) in dirs:
        nc, nr = col + dc, row + dr
        if nc < 1 or nr < 1:
            continue
        neighbor = f"{nc:02d}{nr:02d}"
        entry = hex_index.get(neighbor)
        if entry is None:
            continue
        j_id, p_id = entry
        link = f"@UUID[JournalEntry.{j_id}.JournalEntryPage.{p_id}]{{{neighbor}}}"
        parts.append(f"({label}: {link})")

    return f"<p>{' '.join(parts)}</p>" if parts else ""


def _insert_after_hex_map(html: str, paragraph: str) -> str:
    """Insert *paragraph* immediately after the closing </p> of the hex map image."""
    img_pos = html.find("<img")
    if img_pos == -1:
        return html + paragraph
    end_p = html.find("</p>", img_pos)
    if end_p == -1:
        return html + paragraph
    insert_at = end_p + len("</p>")
    return html[:insert_at] + paragraph + html[insert_at:]


# ── Printed page-label map ─────────────────────────────────────────────────────

def _build_label_map(doc: pymupdf.Document) -> dict[str, int]:
    """Return {printed_label: 0-based_pdf_index} for decimal-numbered pages.

    Uses the PDF's page-label metadata (e.g. front-matter in Roman numerals,
    content pages in Arabic).  Only decimal-style ranges are included because
    the link rule pattern only matches decimal page references.

    Falls back to 1-based sequential numbering if the PDF has no label metadata,
    which preserves the previous behaviour for label-less PDFs.
    """
    try:
        ranges = doc.get_page_labels()
    except Exception:
        ranges = []

    if not ranges:
        return {str(i + 1): i for i in range(doc.page_count)}

    result: dict[str, int] = {}
    for ri, rng in enumerate(ranges):
        start = rng["startpage"]
        end = (ranges[ri + 1]["startpage"] if ri + 1 < len(ranges) else doc.page_count)
        style = rng.get("style", "D")
        prefix = rng.get("prefix", "")
        first = rng.get("firstpagenum", 1)

        if style not in ("D", ""):
            continue   # skip Roman-numeral / letter ranges

        for page_idx in range(start, end):
            label = prefix + str(first + (page_idx - start))
            result[label] = page_idx

    return result


# ── Import macro generation ────────────────────────────────────────────────────

def _write_import_macro(
    out_dir: Path,
    journals: list[_FJournal],
    foundry_dcb_url: str,
) -> Path:
    """Write import_dcb.js — a Foundry macro that imports all journal files."""
    slugs = [_slugify(j.title) for j in journals]
    file_list = "\n".join(f'  "{s}",' for s in slugs)
    script = (
        "// DCB Foundry Import Macro\n"
        f"// Files are served from: {foundry_dcb_url}/\n"
        "// Open Foundry, create a Script macro, paste this, and run it once.\n"
        "\n"
        "const files = [\n"
        f"{file_list}\n"
        "];\n"
        "\n"
        "// Create or reuse the 'DCB' folder\n"
        "let folder = game.folders.find(f => f.name === 'DCB' && f.type === 'JournalEntry');\n"
        "if (!folder) folder = await Folder.create({ name: 'DCB', type: 'JournalEntry' });\n"
        "\n"
        "let imported = 0, failed = [];\n"
        "for (const name of files) {\n"
        "  try {\n"
        f'    const res = await fetch(`{foundry_dcb_url}/${{name}}.json`);\n'
        "    if (!res.ok) { failed.push(`${name} (${res.status})`); continue; }\n"
        "    const data = await res.json();\n"
        "    data.folder = folder.id;\n"
        "    await JournalEntry.create(data, { keepId: true });\n"
        "    console.log(`Imported: ${name}`);\n"
        "    imported++;\n"
        "  } catch (err) {\n"
        "    console.error(`Error importing ${name}:`, err);\n"
        "    failed.push(name);\n"
        "  }\n"
        "}\n"
        "if (failed.length)\n"
        "  ui.notifications.warn(`DCB import: ${imported} succeeded, failed: ${failed.join(', ')}`);\n"
        "else\n"
        "  ui.notifications.info(`DCB import complete — ${imported} journals imported into folder 'DCB'.`);\n"
    )
    macro_path = out_dir / "import_dcb.js"
    macro_path.write_text(script, encoding="utf-8")
    return macro_path


# ── Main export entry point ────────────────────────────────────────────────────

#: Link rules for the DCB — page references and hex references.
_DCB_LINK_RULES: list[LinkRule] = [
    LinkRule(r"\bp\.?\s*(\d+)", "pdf_page", group=1),
    LinkRule(r"(?i)hex\s+(\d{4})", "semantic_key", group=1, key_type="hex_number"),
]


def export_dcb_foundry(
    handler,                # core.pdf_handler.PDFHandler
    dolmenwood_handler,     # DolmenwoodHandler
    pages: list[int],
    output_parent: str,
    foundry_data_root: str,
    normalize_headers: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[Path]:
    """Export the DCB as multiple Foundry VTT journal JSON files.

    *output_parent* — directory inside which dcb/ will be created; should be
        '{foundry_data_root}/assets' so output lands at assets/dcb/ and is
        served by Foundry at /assets/dcb/.
    *foundry_data_root* — the Foundry Data folder (e.g.
        'C:/Store/Application Support/FoundryVTT/Data'). Foundry serves this
        folder at the root URL, so Data/assets/dcb/ → /assets/dcb/.

    Writes to {output_parent}/dcb/:
      <slug>.json   — one per Part-level TOC section
      images/       — extracted page images
      import_dcb.js — macro to import all journals at once

    Returns the list of JSON files created.
    """
    doc = handler.document
    pages_set = set(pages)

    # Hex section info from the Dolmenwood handler
    filename_map = dolmenwood_handler.build_filename_map(doc, pages)
    hex_pages: set[int] = set(filename_map.keys())

    # Output directories
    out_dir = Path(output_parent) / "dcb"
    images_dir = out_dir / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(exist_ok=True)

    # Compute the Foundry static URL for the dcb directory.
    # Foundry serves Data/ at the root, so Data/assets/dcb → /assets/dcb.
    try:
        rel = out_dir.relative_to(Path(foundry_data_root))
        foundry_dcb_url = "/" + str(rel).replace("\\", "/")
    except ValueError:
        foundry_dcb_url = "/assets/dcb"   # fallback if paths are unrelated

    # Step 1: Parse TOC into journal/page structure with pre-assigned IDs
    journals = _parse_journals(doc, pages_set, hex_pages, filename_map, dolmenwood_handler)

    # Step 2: Build cross-journal lookup maps
    # page_id_map is keyed by printed page label (e.g. "26") so that link-rule
    # matches on "p. 26" resolve correctly regardless of PDF front-matter offset.
    label_map = _build_label_map(doc)                    # printed label → pdf index
    pdf_to_label: dict[int, str] = {v: k for k, v in label_map.items()}

    page_id_map: dict[str, tuple[str, str]] = {}
    semantic_index: dict[str, dict[str, tuple[str, str]]] = {}

    for journal in journals:
        for fp in journal.pages:
            for pdf_pg in fp.pdf_pages:
                label = pdf_to_label.get(pdf_pg)
                if label:
                    page_id_map[label] = (journal.journal_id, fp.page_id)
            for key_type, key_value in fp.semantic_keys.items():
                semantic_index.setdefault(key_type, {})[key_value] = (
                    journal.journal_id, fp.page_id
                )

    # Step 3: Extract, transform, and write each journal
    flags = (
        pymupdf.TEXT_PRESERVE_LIGATURES
        | pymupdf.TEXT_PRESERVE_WHITESPACE
        | pymupdf.TEXT_PRESERVE_IMAGES
    )
    xhtml_header = pymupdf.ConversionHeader("xhtml", filename=handler.filename).lstrip("\n")
    xhtml_trailer = pymupdf.ConversionTrailer("xhtml")

    total = sum(len(j.pages) for j in journals)
    completed = 0
    output_paths: list[Path] = []

    for journal in journals:
        fvtt_pages: list[dict] = []

        for fp in journal.pages:
            parts: list[str] = []
            for pdf_pg in fp.pdf_pages:
                raw = _sanitize_xml(doc[pdf_pg].get_text("xhtml", flags=flags))
                full_xhtml = "\n".join([xhtml_header, raw, xhtml_trailer])
                if normalize_headers:
                    full_xhtml = _normalize_xhtml_headers(full_xhtml)
                if fp.is_hex:
                    full_xhtml = restructure_hex_page(full_xhtml)
                parts.append(_extract_page_div_content(full_xhtml))

            content = "".join(parts)
            content = _strip_soft_hyphens(content)
            content = _remove_running_headers(content)
            content = _remove_artifact_page_numbers(content)
            content = _merge_split_headings(content)
            content = _convert_italic_headings(content)
            content = _fix_section_opener_headings(content)
            content = _absorb_drop_caps(content)
            content = _fix_settlement_headings(content)
            content = _deduplicate_headings(content)
            content = _split_table_paragraphs(content)
            content = _sort_interleaved_table_rows(content)

            # Inject neighbour links paragraph after the hex map image
            if fp.is_hex:
                hex_num = fp.semantic_keys.get("hex_number")
                if hex_num:
                    neighbor_p = _hex_neighbor_links(hex_num, semantic_index)
                    if neighbor_p:
                        content = _insert_after_hex_map(content, neighbor_p)

            # Externalize images (base64 → disk files)
            page_label = f"p{fp.pdf_pages[0]:04d}" if fp.pdf_pages else "pX"
            content = _externalize_images(content, images_dir, foundry_dcb_url, page_label)

            # Resolve cross-journal @UUID links
            content = _resolve_links(content, _DCB_LINK_RULES, page_id_map, semantic_index)

            fvtt_pages.append({
                "_id": fp.page_id,
                "name": fp.title,
                "type": "text",
                "sort": (len(fvtt_pages) + 1) * 100000,
                "title": {"show": True, "level": 1},
                "text": {"content": content, "format": 1},
                "image": {},
                "video": {"controls": True, "volume": 0.5},
                "src": None,
                "system": {},
                "ownership": {"default": -1},
                "flags": {},
            })

            completed += 1
            if progress_callback:
                progress_callback(completed, total)

        journal_data = {
            "_id": journal.journal_id,
            "name": journal.title,
            "ownership": {"default": 0},
            "flags": {},
            "folder": None,
            "sort": 0,
            "pages": fvtt_pages,
        }

        slug = _slugify(journal.title)
        json_path = out_dir / f"{slug}.json"
        json_path.write_text(
            json.dumps(journal_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        output_paths.append(json_path)

    _write_import_macro(out_dir, journals, foundry_dcb_url)
    return output_paths
