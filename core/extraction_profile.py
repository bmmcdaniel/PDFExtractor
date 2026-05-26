"""Per-PDF extraction profile for Foundry VTT journal output.

A profile describes how the pages of one PDF map to Foundry journal entry
pages.  It consists of ordered *sections*, each covering a page range with a
grouping strategy, plus optional *link rules* for turning page-number or
semantic references into @UUID links.

Profiles are stored as <pdf-stem>.profile.json alongside the PDF.  On first
run the application generates a default profile (from the book handler if one
matches, otherwise from the user's chosen TOC level) and saves it.  On
subsequent runs the saved file is loaded so hand-edits persist.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _make_id() -> str:
    """Generate a Foundry-compatible 16-character hex document ID."""
    return secrets.token_hex(8)


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class SectionRule:
    """One page-range section and how to group its pages into journal pages."""

    name: str
    page_start: int    # 0-based PDF page index, inclusive
    page_end: int      # 0-based PDF page index, inclusive
    strategy: str      # "toc" | "page" | "skip"
    toc_level: int = 2
    transform: bool = False  # call page_xhtml_transform on each page

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "strategy": self.strategy,
            "toc_level": self.toc_level,
            "transform": self.transform,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SectionRule:
        return cls(
            name=d["name"],
            page_start=d["page_start"],
            page_end=d["page_end"],
            strategy=d["strategy"],
            toc_level=d.get("toc_level", 2),
            transform=d.get("transform", False),
        )


@dataclass
class LinkRule:
    """A text pattern to replace with a Foundry @UUID link.

    *pattern* is a regex; the capture group at index *group* yields the key.
    *resolve* controls how the key is looked up:
      "pdf_page"     — key is a 1-based human page number; resolved via the
                       page-ID map built during extraction.
      "semantic_key" — key is a book-specific identifier (e.g. hex number);
                       resolved via the semantic index built by the book handler.
    *key_type* is only used for "semantic_key" and must match a key_type
    populated by the handler's stem_to_semantic_keys() method.
    """

    pattern: str
    resolve: str       # "pdf_page" | "semantic_key"
    group: int = 1
    key_type: str = ""

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "resolve": self.resolve,
            "group": self.group,
            "key_type": self.key_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> LinkRule:
        return cls(
            pattern=d["pattern"],
            resolve=d["resolve"],
            group=d.get("group", 1),
            key_type=d.get("key_type", ""),
        )


@dataclass
class ExtractionProfile:
    """Full per-PDF configuration for Foundry VTT journal export."""

    journal_name: str
    sections: list[SectionRule]
    link_rules: list[LinkRule] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "journal_name": self.journal_name,
            "sections": [s.to_dict() for s in self.sections],
            "link_rules": [r.to_dict() for r in self.link_rules],
        }

    @classmethod
    def from_dict(cls, d: dict) -> ExtractionProfile:
        return cls(
            journal_name=d["journal_name"],
            sections=[SectionRule.from_dict(s) for s in d.get("sections", [])],
            link_rules=[LinkRule.from_dict(r) for r in d.get("link_rules", [])],
        )

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> ExtractionProfile:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass
class JournalGroup:
    """One Foundry journal page: a named, ordered set of PDF pages."""

    title: str
    pages: list[int]                      # 0-based PDF page indices, in order
    transform: bool                       # apply page_xhtml_transform to each page
    page_id: str = field(default_factory=_make_id)
    semantic_keys: dict[str, str] = field(default_factory=dict)
    # e.g. {"hex_number": "0508"} — used to build the semantic link index


# ── Profile construction helpers ───────────────────────────────────────────────

def profile_path_for(pdf_path: str | Path) -> Path:
    """Return the .profile.json path that sits alongside a given PDF."""
    p = Path(pdf_path)
    return p.parent / f"{p.stem}.profile.json"


def build_toc_profile(
    doc,              # pymupdf.Document
    journal_name: str,
    toc_level: int,
) -> ExtractionProfile:
    """Build a single-section flat profile using TOC grouping at *toc_level*.

    *toc_level* 0 means "one journal page per PDF page" (strategy "page").
    Any positive integer uses strategy "toc" at that level.
    A generic page-reference link rule is included automatically.
    """
    strategy = "toc" if toc_level > 0 else "page"
    section = SectionRule(
        name="Content",
        page_start=0,
        page_end=doc.page_count - 1,
        strategy=strategy,
        toc_level=toc_level,
        transform=False,
    )
    return ExtractionProfile(
        journal_name=journal_name,
        sections=[section],
        link_rules=[LinkRule(r"p\.\s*(\d+)", "pdf_page", group=1)],
    )


# ── Journal group builder ──────────────────────────────────────────────────────

def build_journal_groups(
    profile: ExtractionProfile,
    doc,              # pymupdf.Document
    pages: list[int],
    filename_map: dict[int, str] | None = None,
    stem_to_title=None,          # Callable[[str], str] | None
    stem_to_semantic_keys=None,  # Callable[[str], dict[str, str]] | None
) -> list[JournalGroup]:
    """Expand a profile into an ordered list of JournalGroups.

    Only PDF pages present in *pages* and falling within a section's range
    are included.  Groups with no pages are omitted silently.

    *filename_map*          maps page index → partial filename stem (from the
                            book handler); used for "page" strategy sections.
    *stem_to_title*         converts a stem to a human-readable title.
    *stem_to_semantic_keys* extracts semantic link keys from a stem.
    """
    # PyMuPDF TOC: [[level, title, page_1based], ...]
    toc = doc.get_toc()
    result: list[JournalGroup] = []

    for section in profile.sections:
        if section.strategy == "skip":
            continue

        section_pages = [p for p in pages
                         if section.page_start <= p <= section.page_end]
        if not section_pages:
            continue

        if section.strategy == "page":
            for pg in section_pages:
                stem = (filename_map or {}).get(pg)
                if stem:
                    title = stem_to_title(stem) if stem_to_title else stem.replace("_", " ")
                    sem_keys = stem_to_semantic_keys(stem) if stem_to_semantic_keys else {}
                else:
                    title = f"Page {pg + 1}"
                    sem_keys = {}
                result.append(JournalGroup(
                    title=title,
                    pages=[pg],
                    transform=section.transform,
                    semantic_keys=sem_keys,
                ))

        elif section.strategy == "toc":
            level = section.toc_level
            toc_entries: list[tuple[str, int]] = [
                (title, pg_1 - 1)
                for lvl, title, pg_1 in toc
                if lvl == level
                and section.page_start <= (pg_1 - 1) <= section.page_end
            ]

            if not toc_entries:
                # No TOC entries at this level — treat whole section as one group
                result.append(JournalGroup(
                    title=section.name,
                    pages=section_pages,
                    transform=section.transform,
                ))
                continue

            # Pages before the first TOC entry → intro group under section name
            first_toc_pg = toc_entries[0][1]
            pre = [p for p in section_pages if p < first_toc_pg]
            if pre:
                result.append(JournalGroup(
                    title=section.name,
                    pages=pre,
                    transform=section.transform,
                ))

            for i, (title, toc_pg) in enumerate(toc_entries):
                next_pg = (toc_entries[i + 1][1]
                           if i + 1 < len(toc_entries)
                           else section.page_end + 1)
                group_pages = [p for p in section_pages if toc_pg <= p < next_pg]
                if group_pages:
                    result.append(JournalGroup(
                        title=title,
                        pages=group_pages,
                        transform=section.transform,
                    ))

    return result


# ── Link resolution ────────────────────────────────────────────────────────────

def resolve_links(
    html: str,
    link_rules: list[LinkRule],
    journal_id: str,
    page_id_map: dict[int, str],
    semantic_index: dict[str, dict[str, str]],
) -> str:
    """Replace matched link patterns in *html* with Foundry @UUID links.

    *page_id_map*      maps 0-based PDF page index → journal page _id.
    *semantic_index*   maps key_type → {key_value → journal page _id}.

    Patterns that cannot be resolved (target page not extracted or not in map)
    are left unchanged.
    """
    for rule in link_rules:
        regex = re.compile(rule.pattern)

        def _replace(m: re.Match, _rule: LinkRule = rule) -> str:
            original = m.group(0)
            key = m.group(_rule.group)
            if _rule.resolve == "pdf_page":
                try:
                    pg_0 = int(key) - 1   # human 1-based → 0-based index
                except ValueError:
                    return original
                page_id = page_id_map.get(pg_0)
            elif _rule.resolve == "semantic_key":
                page_id = semantic_index.get(_rule.key_type, {}).get(key)
            else:
                return original

            if page_id is None:
                return original
            return (
                f"@UUID[JournalEntry.{journal_id}"
                f".JournalEntryPage.{page_id}]{{{original}}}"
            )

        html = regex.sub(_replace, html)

    return html
