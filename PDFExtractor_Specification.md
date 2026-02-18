# PDF Text and Image Extractor - Technical Specification

**Version:** 3.0
**Date:** February 18, 2026
**Target Platform:** Windows (Python cross-platform compatible)
**Language:** Python 3.10+
**Primary Library:** PyMuPDF (pymupdf)
**GUI Framework:** CustomTkinter

---

## 1. PROJECT OVERVIEW

### 1.1 Purpose
Create a standalone GUI application that allows users to extract text and images from PDF files with a visual page-thumbnail interface for selecting which pages to process.

### 1.2 Key Features
- Modern themed GUI with system-following dark/light mode
- Visual PDF page thumbnails with per-page selection
- Drag-and-drop PDF loading from Explorer
- Multiple text extraction formats (Markdown, Plain Text, XHTML, DOCX)
- Multiple image extraction formats (Native, PNG, JPEG, WebP)
- Image deduplication (each unique image extracted once)
- Threaded extraction with progress feedback
- Keyboard shortcuts (Ctrl+O, Ctrl+A, Ctrl+Shift+A, Ctrl+I)
- Ctrl+scroll zoom with zoom level indicator and Ctrl+double-click reset
- Hover preview showing large page preview on mouse-over
- Right-click context menu on thumbnails for selection operations
- Persistent settings (last-used directories remembered across sessions)
- Parallel thumbnail rendering using ThreadPoolExecutor

---

## 2. USER INTERFACE DESIGN

### 2.1 Main Window Layout

```
┌──────────────────────────────────────────────────────────────┐
│ PDF Text & Image Extractor                          [_][□][X]│
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────┐  [Open]  │
│  │  Drop PDF Here or Click to Browse...           │          │
│  └────────────────────────────────────────────────┘          │
├──────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────────┐ │
│ │                                                          │ │
│ │  PDF Page Thumbnails (Scrollable Grid)                   │ │
│ │  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐               │ │
│ │  │       │ │       │ │       │ │       │  ...            │ │
│ │  │   1   │ │   2   │ │   3   │ │   4   │               │ │
│ │  │       │ │       │ │       │ │       │               │ │
│ │  └───────┘ └───────┘ └───────┘ └───────┘               │ │
│ │    [✓]       [✓]       [ ]       [✓]                     │ │
│ │                                                          │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│  [Select All]  [Select None]  [Invert Selection]             │
│                                                              │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  │
│  │ Extract Text        │  │ Extract Images               │  │
│  ├─────────────────────┤  ├──────────────────────────────┤  │
│  │ Format:             │  │ Format:                      │  │
│  │ ● Markdown (.md)    │  │ ● Native (original format)   │  │
│  │ ○ Plain Text (.txt) │  │ ○ Convert to PNG             │  │
│  │ ○ XHTML (.xhtml)    │  │ ○ Convert to JPEG            │  │
│  │ ○ Word (.docx)      │  │ ○ Convert to WebP            │  │
│  │                     │  │                              │  │
│  │ [Extract Text]      │  │ [Extract Images]             │  │
│  └─────────────────────┘  └──────────────────────────────┘  │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ Status: Ready                          [████████░░] 80%      │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 UI Components Breakdown

#### 2.2.1 File Selection Area
- **Drop Zone**: A `CTkLabel` styled as a drop target, accepting PDF drag-and-drop via tkinterdnd2
- **Browse Button**: `CTkButton` opening a file dialog filtered to `*.pdf`
- **File Path Display**: Shows the currently loaded PDF filename inside the drop zone label
- **Behavior on new file**: If a PDF is already loaded, loading a new one replaces it (clears thumbnails and selection)

#### 2.2.2 Thumbnail Grid View
- **Container**: `CTkScrollableFrame` with vertical scrolling
- **Layout**: Grid of thumbnail cells using `.grid()` geometry manager
- **Default Thumbnail Size**: 90×120 logical pixels (ZOOM_DEFAULT=90), zoomable from 40 to 240
- **Thumbnail Rendering**: PIL source images rendered at 120×160 (1x) for fast loading
- **Columns**: Dynamically recalculated on window resize via debounced `<Configure>` event binding
- **Per-Thumbnail Cell** (a `CTkFrame` containing):
  - `CTkLabel` with `CTkImage` showing the page preview
  - Red border indicates selected state; border matches background when deselected
- **Click behavior**: Clicking the thumbnail toggles its selection state
- **Zoom**: Ctrl+scroll to zoom thumbnails in/out; Ctrl+double-click to reset to default zoom
- **Hover Preview**: Hovering over a thumbnail for 390ms shows a large 720×960 preview window that follows the cursor
- **Right-click menu**: Context menu with Select All, Select None, Invert Selection, Select This and All After, Select Only This, Deselect Only This

#### 2.2.3 Selection Controls
- **Select All** (`CTkButton`): Selects all pages (also Ctrl+A)
- **Select None** (`CTkButton`): Deselects all pages (also Ctrl+Shift+A)
- **Invert Selection** (`CTkButton`): Toggles each page's selection (also Ctrl+I)

#### 2.2.4 Text Extraction Panel
- **Container**: `CTkFrame` with a label header
- **Radio Buttons** (`CTkRadioButton` sharing an `IntVar`):
  - Markdown (.md) — **DEFAULT**
  - Plain Text (.txt)
  - XHTML (.xhtml) — clean, semantic markup
  - Word (.docx) — editable document
- **Extract Text** (`CTkButton`): Disabled until a PDF is loaded and at least one page is selected

#### 2.2.5 Image Extraction Panel
- **Container**: `CTkFrame` with a label header
- **Radio Buttons** (`CTkRadioButton` sharing an `IntVar`):
  - Native (preserves original format) — **DEFAULT**
  - Convert to PNG
  - Convert to JPEG
  - Convert to WebP
- **Extract Images** (`CTkButton`): Disabled until a PDF is loaded and at least one page is selected

#### 2.2.6 Status Bar
- **Status Label** (`CTkLabel`): Text messages — "Ready", "Loading PDF...", "Extracting text from 5 pages...", etc.
- **Zoom Indicator**: Temporarily shows "Zoom: 150%" for 1.5 seconds when zoom level changes, then reverts to selection status
- **Progress Bar** (`CTkProgressBar`): Determinate mode during extraction, hidden when idle

### 2.3 Appearance
- **Theme**: System-following (`customtkinter.set_appearance_mode("system")`)
- **Color theme**: `"blue"` (default)
- **Minimum window size**: 800x600
- **Default window size**: 920x750
- **DPI**: Automatic HiDPI handling via CustomTkinter's built-in DPI awareness

---

## 3. TECHNICAL IMPLEMENTATION

### 3.1 Technology Stack

#### 3.1.1 Core Libraries
```
# requirements.txt
pymupdf>=1.24.0          # PDF handling and extraction
pymupdf4llm>=0.3.0       # Markdown text extraction
customtkinter>=5.2.0     # Modern themed GUI framework
pillow>=10.0.0           # Image format conversions, CTkImage support
tkinterdnd2>=0.4.0       # Drag-and-drop file support
python-docx>=1.1.0       # Word document generation
```

#### 3.1.2 GUI Framework Choice
**Selected: CustomTkinter**
- **Rationale**:
  - Modern, themed appearance out of the box
  - Built-in dark/light mode following system preference
  - Automatic Windows HiDPI scaling
  - `CTkScrollableFrame` for the thumbnail grid
  - `CTkProgressBar` for extraction progress
  - Drop-in replacement for tkinter with better visuals
  - MIT licensed

**Drag-and-drop**: Requires `tkinterdnd2` for accepting files dragged from Explorer. The main `App` class inherits from both `customtkinter.CTk` and `TkinterDnD.DnDWrapper`.

### 3.2 File Structure

```
PDFExtractor/
├── main.py                    # Application entry point
├── gui/
│   ├── __init__.py
│   ├── app.py                 # Main App window class (CTk + DnD)
│   ├── thumbnail_grid.py      # ThumbnailGrid widget (CTkScrollableFrame)
│   ├── extraction_panel.py    # TextPanel and ImagePanel widgets
│   └── dialogs.py             # Completion and error dialog helpers
├── core/
│   ├── __init__.py
│   ├── pdf_handler.py         # PDF loading, thumbnails, page access
│   ├── text_extractor.py      # Text extraction (all formats)
│   ├── image_extractor.py     # Image extraction (all formats)
│   └── settings.py            # Persistent JSON settings (~/.pdfextractor/)
├── assets/
│   └── icon.ico               # Application icon
├── requirements.txt
└── README.md
```

### 3.3 Threading Model

All extraction runs in background threads to keep the UI responsive. Communication back to the UI uses tkinter's `after()` method.

**Thumbnail rendering** uses a `ThreadPoolExecutor` (up to 4 workers) for parallel page rendering. PyMuPDF releases the GIL during `get_pixmap()`, enabling true parallelism across CPU cores. Results are batched (10 per callback) and marshalled to the main thread via `after(0)`.

```python
from concurrent.futures import ThreadPoolExecutor

def generate():
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
        thumbs = pool.map(handler.get_thumbnail, range(total))
        for i, thumb in enumerate(thumbs):
            # batch and marshal to main thread
```

**Extraction** uses a simple single-thread wrapper:
```python
def _run_in_thread(self, target, on_complete, on_error):
    def wrapper():
        try:
            result = target()
            self.after(0, on_complete, result)
        except Exception as e:
            self.after(0, on_error, e)
    thread = threading.Thread(target=wrapper, daemon=True)
    thread.start()
```

**Progress callbacks**: Extraction methods accept an optional `progress_callback(current: int, total: int)` parameter. The GUI wraps this to call `self.after(0, update_progress_bar, current, total)` to safely update the `CTkProgressBar` from the main thread.

**UI locking during extraction**: While an extraction or thumbnail load is running, the Extract buttons are disabled and the Open/Browse controls are disabled. Keyboard shortcuts also check the `_working` flag before acting.

### 3.4 Core Classes

#### 3.4.1 PDFHandler
```python
class PDFHandler:
    """Manages PDF document loading and page access."""

    def __init__(self, filepath: str):
        """Open PDF document. Raises ValueError for invalid/encrypted PDFs."""

    @property
    def filepath(self) -> str:
        """Return the original file path."""

    @property
    def filename(self) -> str:
        """Return the filename without path (e.g., 'document.pdf')."""

    @property
    def stem(self) -> str:
        """Return the filename without extension (e.g., 'document')."""

    def get_page_count(self) -> int:
        """Return total number of pages."""

    def get_thumbnail(self, page_num: int, width: int = 120, height: int = 160,
                       hidpi: bool = False) -> PIL.Image.Image:
        """Generate thumbnail PIL Image for the given 0-based page index.

        The returned image is sized to fit within width x height while
        preserving aspect ratio. Set hidpi=True for 2x preview quality.
        Renders with alpha=False and annots=False for speed.
        """

    def get_page(self, page_num: int) -> pymupdf.Page:
        """Get page object for the given 0-based page index."""

    @property
    def document(self) -> pymupdf.Document:
        """Return the underlying pymupdf.Document for direct access."""

    def close(self):
        """Close PDF document and release resources."""
```

#### 3.4.2 TextExtractor
```python
class TextExtractor:
    """Handles text extraction in multiple formats."""

    def __init__(self, pdf_handler: PDFHandler):
        """Initialize with an open PDFHandler."""

    def extract_markdown(
        self,
        pages: list[int],
        output_path: str,
        progress_callback: Callable[[int, int], None] | None = None
    ) -> None:
        """Extract text as Markdown using pymupdf4llm."""

    def extract_plain_text(
        self,
        pages: list[int],
        output_path: str,
        progress_callback: Callable[[int, int], None] | None = None
    ) -> None:
        """Extract text as plain text with form-feed page separators."""

    def extract_xhtml(
        self,
        pages: list[int],
        output_path: str,
        progress_callback: Callable[[int, int], None] | None = None
    ) -> None:
        """Extract text as clean, semantic XHTML."""

    def extract_docx(
        self,
        pages: list[int],
        output_path: str,
        progress_callback: Callable[[int, int], None] | None = None
    ) -> None:
        """Extract text as a Word document using python-docx."""
```

#### 3.4.3 ImageExtractor
```python
class ImageExtractor:
    """Handles image extraction with deduplication and format conversion."""

    def __init__(self, pdf_handler: PDFHandler):
        """Initialize with an open PDFHandler."""

    def extract(
        self,
        pages: list[int],
        output_dir: str,
        format: str = "native",  # "native", "png", "jpeg", "webp"
        progress_callback: Callable[[int, int], None] | None = None
    ) -> int:
        """Extract images from selected pages.

        Images are deduplicated by xref — if the same image appears on
        multiple selected pages, it is extracted only once.

        Args:
            pages: List of 0-based page indices
            output_dir: Directory to save extracted images
            format: Output format — "native", "png", "jpeg", or "webp"
            progress_callback: Optional callback(current, total)

        Returns:
            Number of unique images extracted
        """
```

---

## 4. EXTRACTION SPECIFICATIONS

### 4.1 Text Extraction Details

#### 4.1.1 Markdown Format (.md)
**Library**: `pymupdf4llm.to_markdown()`

**Implementation**:
```python
import pymupdf4llm

md_text = pymupdf4llm.to_markdown(
    doc,                          # pymupdf.Document or file path
    pages=selected_pages,         # List of 0-based page indices
    page_chunks=False,            # Single combined string output
    show_progress=False,          # We handle progress via page count
    table_strategy="lines_strict" # Precise table detection
)

with open(output_path, "w", encoding="utf-8") as f:
    f.write(md_text)
```

**Output**: Single `.md` file, UTF-8 encoded

**Features**:
- Preserves headers (detected via font size analysis)
- Maintains tables (using `lines_strict` strategy)
- Includes bold/italic formatting
- GitHub-compatible Markdown syntax

#### 4.1.2 Plain Text Format (.txt)
**Library**: `page.get_text("text")`

**Implementation**:
```python
text_parts = []
for i, page_num in enumerate(selected_pages):
    page = doc[page_num]
    text_parts.append(page.get_text("text"))
    if progress_callback:
        progress_callback(i + 1, len(selected_pages))

combined_text = "\f".join(text_parts)  # Form feed page separator

with open(output_path, "w", encoding="utf-8") as f:
    f.write(combined_text)
```

**Output**: Single `.txt` file, UTF-8 encoded, pages separated by form feed (`\f`)

#### 4.1.3 XHTML Format (.xhtml)
**Library**: `page.get_text("xhtml")` with `pymupdf.ConversionHeader/Trailer`

**Implementation**:
```python
import pymupdf

header = pymupdf.ConversionHeader("xhtml", filename=filename)
trailer = pymupdf.ConversionTrailer("xhtml")

xhtml_parts = [header]
for i, page_num in enumerate(selected_pages):
    page = doc[page_num]
    xhtml_parts.append(page.get_text("xhtml"))
    if progress_callback:
        progress_callback(i + 1, len(selected_pages))
xhtml_parts.append(trailer)

with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(xhtml_parts))
```

**Note**: Unlike `get_text("html")` which produces heavily styled fragments with absolute positioning and inline font declarations, `get_text("xhtml")` produces clean, semantic markup using standard HTML elements (`<p>`, `<span>`, `<b>`, `<i>`) without positional styling. This is easier to re-style and re-use but does not preserve the original page layout.

**Output**: Single `.xhtml` file with semantic markup, wrapped with `ConversionHeader/Trailer`

#### 4.1.4 Word Document Format (.docx)
**Library**: `python-docx`

**Implementation**:
```python
from docx import Document as DocxDocument
from docx.shared import Pt
import pymupdf4llm
import re

# Extract structured content using pymupdf4llm with page_chunks
chunks = pymupdf4llm.to_markdown(
    doc,
    pages=selected_pages,
    page_chunks=True,
    table_strategy="lines_strict"
)

docx_doc = DocxDocument()

for i, chunk in enumerate(chunks):
    md_text = chunk["text"]

    for line in md_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Map Markdown headings to Word heading styles
        if stripped.startswith("# "):
            docx_doc.add_heading(stripped[2:], level=1)
        elif stripped.startswith("## "):
            docx_doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith("### "):
            docx_doc.add_heading(stripped[4:], level=3)
        else:
            para = docx_doc.add_paragraph()
            # Parse bold (**text**) and italic (*text*) runs
            _add_formatted_runs(para, stripped)

    # Page break between pages (except after last)
    if i < len(chunks) - 1:
        docx_doc.add_page_break()

    if progress_callback:
        progress_callback(i + 1, len(chunks))

docx_doc.save(output_path)
```

**Formatting support**: The `_add_formatted_runs()` helper parses Markdown inline formatting (`**bold**`, `*italic*`, `***bold italic***`) into python-docx `Run` objects with the appropriate `bold` and `italic` properties.

**Limitations**:
- Tables are inserted as plain text (python-docx can create tables, but faithfully mapping pymupdf4llm's Markdown tables adds significant complexity — reserved for a future enhancement)
- Images are not embedded
- Complex layouts (multi-column, sidebars) are flattened to linear flow

**Output**: Single `.docx` file with headings, paragraphs, and basic bold/italic formatting

### 4.2 Image Extraction Details

#### 4.2.1 Image Deduplication

Images are deduplicated by their PDF cross-reference number (xref). The same image embedded on multiple pages shares a single xref and is extracted only once.

```python
seen_xrefs: set[int] = set()

for page_num in selected_pages:
    page = doc[page_num]
    for img in page.get_images():
        xref = img[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        # Extract this image...
```

**Naming Convention**: `img_{xref}.{ext}` (e.g., `img_42.png`)

This avoids ambiguous per-page numbering and makes deduplication transparent in the output filenames.

#### 4.2.2 Native Format (Original)
**Method**: `doc.extract_image(xref)`

```python
base_image = doc.extract_image(xref)
image_ext = base_image["ext"]     # "jpeg", "png", "tiff", etc.
image_bytes = base_image["image"]

output_path = os.path.join(output_dir, f"img_{xref}.{image_ext}")
with open(output_path, "wb") as f:
    f.write(image_bytes)
```

**Output**: Original format and quality preserved exactly as stored in the PDF.

#### 4.2.3 Convert to PNG
**Method**: `pymupdf.Pixmap` conversion

```python
pix = pymupdf.Pixmap(doc, xref)

# Convert CMYK to RGB if needed
if pix.n - pix.alpha > 3:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

output_path = os.path.join(output_dir, f"img_{xref}.png")
pix.save(output_path)
```

**Output**: PNG (RGB or RGBA depending on source)

#### 4.2.4 Convert to JPEG
**Method**: `pymupdf.Pixmap` with explicit alpha removal

```python
pix = pymupdf.Pixmap(doc, xref)

# Convert CMYK to RGB if needed
if pix.n - pix.alpha > 3:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

# JPEG does not support alpha — strip it
if pix.alpha:
    pix = pymupdf.Pixmap(pix, 0)  # 0 = drop alpha channel

output_path = os.path.join(output_dir, f"img_{xref}.jpg")
pix.save(output_path, output="jpeg", jpg_quality=95)
```

**Important**: The correct way to strip alpha is `pymupdf.Pixmap(pix, 0)`. Do NOT use `pymupdf.Pixmap(pymupdf.csRGB, pix)` for alpha removal — that only converts the colorspace and may retain the alpha channel.

**Output**: JPEG, RGB only, quality 95

#### 4.2.5 Convert to WebP
**Method**: Pillow for WebP encoding

```python
from PIL import Image

pix = pymupdf.Pixmap(doc, xref)

# Convert CMYK to RGB if needed
if pix.n - pix.alpha > 3:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

# Determine PIL mode from pixmap properties
if pix.alpha:
    mode = "RGBA"
else:
    mode = "RGB"

img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)

output_path = os.path.join(output_dir, f"img_{xref}.webp")
img.save(output_path, "WEBP", quality=90)
```

**Output**: WebP, quality 90

### 4.3 Output Organization

#### 4.3.1 Save Dialog Behavior

Both text and image extraction always show a save dialog before writing:

- **Text extraction**: File save dialog
  - Default filename: `{pdf_stem}.{ext}` (e.g., `document.md`)
  - Default directory: Last-used save directory (persisted), or same directory as source PDF
  - File type filter matches the selected format

- **Image extraction**: Folder selection dialog
  - Default directory: Last-used image directory (persisted), or same directory as source PDF

- **PDF open dialog**: Remembers last-used open directory across sessions

All last-used directories are persisted to `~/.pdfextractor/settings.json` via `core/settings.py`.

This ensures the user always confirms the output location and avoids failures when the source PDF is in a read-only location.

#### 4.3.2 Image Output Structure
```
chosen_output_folder/
├── img_42.png
├── img_57.png
├── img_89.png
└── img_124.png
```

Images are named by xref number, making deduplication visible and filenames stable across repeated extractions.

---

## 5. USER WORKFLOWS

### 5.1 Extract Text Workflow

1. **User opens application**
2. **User loads PDF** via one of:
   - Drag-and-drop a `.pdf` file from Explorer onto the drop zone
   - Click "Open" and select a PDF from the file dialog
3. **Application generates thumbnails** in a background thread; progress bar shows loading status
4. **All pages are selected by default**
5. **User optionally adjusts selection**:
   - Uncheck individual pages
   - Use "Select None" then check specific pages
   - Use "Invert Selection"
6. **User selects text format** via radio buttons (Markdown is default)
7. **User clicks "Extract Text"**
8. **Save dialog appears** with default filename and location pre-filled
9. **Extraction runs in background thread**:
   - Extract buttons and Open button are disabled
   - Status bar shows: "Extracting text from X pages..."
   - Progress bar updates
10. **Completion**: Status bar shows "Text extracted successfully", a dialog offers "Open File", "Open Folder", or "OK"

### 5.2 Extract Images Workflow

1. **Steps 1-5** same as text workflow
2. **User selects image format** via radio buttons (Native is default)
3. **User clicks "Extract Images"**
4. **Folder selection dialog appears** with default folder name pre-filled
5. **Extraction runs in background thread**:
   - Status bar shows: "Extracting images... (X of Y unique images)"
   - Progress bar updates
6. **Completion**: Status bar shows "Extracted X images", a dialog offers "Open Folder" or "OK"

### 5.3 Loading a New PDF

When a PDF is already loaded and the user loads a new one:
1. Previous document is closed
2. Thumbnail cache is cleared
3. All selection state is reset
4. New thumbnails are generated

---

## 6. DRAG-AND-DROP IMPLEMENTATION

### 6.1 Hybrid App Class

CustomTkinter does not natively support drag-and-drop. The `tkinterdnd2` library provides this by wrapping the underlying Tk DnD extension.

```python
from tkinterdnd2 import TkinterDnD, DND_FILES
import customtkinter

class App(customtkinter.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        TkinterDnD._require(self)

        # Register the drop zone widget
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self._on_file_drop)

    def _on_file_drop(self, event):
        filepath = event.data
        # Windows may wrap the path in braces if it contains spaces
        if filepath.startswith("{") and filepath.endswith("}"):
            filepath = filepath[1:-1]
        if filepath.lower().endswith(".pdf"):
            self._load_pdf(filepath)
        else:
            self._show_error("Please drop a PDF file.")
```

### 6.2 Drop Zone Visual Feedback

The drop zone label should update visually during drag-over:
- **Default state**: "Drop PDF Here or Click to Browse..."
- **Drag hover**: Border highlight changes color, text changes to "Release to open PDF"
- **File loaded**: Shows the filename (e.g., "document.pdf (42 pages)")

---

## 7. ERROR HANDLING

### 7.1 Error Scenarios

#### 7.1.1 File Loading Errors
| Condition | Message |
|-----------|---------|
| Not a PDF | "Selected file is not a valid PDF." |
| Corrupted | "PDF file is corrupted or cannot be read." |
| Locked by another process | "Cannot open PDF — file may be in use by another application." |
| Password-protected | "PDF is password-protected. Password-protected PDFs are not supported in this version." |

#### 7.1.2 Extraction Errors
| Condition | Message |
|-----------|---------|
| No pages selected | "Please select at least one page." (Extract button should be disabled, but guard against it.) |
| No images found | "No images found on the selected pages." |
| Write permission denied | "Cannot write to the selected location. Please choose a different folder." |
| Disk full | "Not enough disk space to complete the extraction." |

#### 7.1.3 Error Display
- Errors shown via `CTkToplevel` modal dialog (not tkinter messagebox, to maintain theme consistency)
- All errors are also logged to stderr via `logging` module
- After any error, the application returns to the ready state

---

## 8. PERFORMANCE CONSIDERATIONS

### 8.1 Thumbnail Generation
- **Parallel rendering**: Thumbnails are rendered using `ThreadPoolExecutor` with up to 4 workers; PyMuPDF releases the GIL during `get_pixmap()` enabling true parallelism
- **Optimized pixmap**: `get_pixmap(alpha=False, annots=False)` skips alpha channel computation and annotation rendering for faster thumbnails
- **1x resolution**: Thumbnails rendered at display resolution (120×160) not 2x, since hover preview provides high-quality detail on demand
- **Batched marshaling**: Thumbnails are batched (10 per callback) to reduce event loop overhead
- **Deferred event binding**: Cell event bindings are applied once in `finish_loading()` rather than per-cell during loading
- **Cache**: Store `CTkImage` objects in a list; clear on new PDF load

### 8.2 Large PDF Handling
- **Page limit warning**: If PDF has more than 500 pages, show a confirmation dialog: "This PDF has X pages. Generating thumbnails may take a moment. Continue?"
- **Memory management**: Clear thumbnail cache before generating new set
- **Extraction batching**: Not needed for v1.0 — PyMuPDF handles sequential page access efficiently

### 8.3 Thread Safety
- PyMuPDF `Document` objects support concurrent read access in PyMuPDF 1.24+. Thumbnail rendering uses multiple threads safely via `ThreadPoolExecutor`.
- The GUI thread must not access the `Document` directly during extraction.
- Progress updates from the worker thread are marshalled to the GUI thread via `self.after(0, callback)`.

---

## 9. INSTALLATION & PACKAGING

### 9.1 Development Installation
```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 9.2 Requirements File
```
# requirements.txt
pymupdf>=1.24.0
pymupdf4llm>=0.3.0
customtkinter>=5.2.0
pillow>=10.0.0
tkinterdnd2>=0.4.0
python-docx>=1.1.0
```

### 9.3 Standalone Executable (Future)
- **Tool**: PyInstaller
- **Note**: `tkinterdnd2` requires special handling in PyInstaller (the DnD shared libraries must be included via `--add-data` or a hook file)
- **Command**:
  ```bash
  pyinstaller --onefile --windowed --icon=assets/icon.ico ^
      --hidden-import=tkinterdnd2 ^
      main.py
  ```
- **Output**: Single `.exe` file for Windows

---

## 10. FUTURE ENHANCEMENTS

### 10.1 Potential Features
- Batch processing multiple PDFs
- OCR for scanned PDFs (pymupdf4llm already supports `use_ocr=True`)
- Custom image quality/size settings
- Text search and highlight before extraction
- Preview extracted text before saving
- Bookmarks/TOC extraction
- Password-protected PDF support (password entry dialog)
- Command-line interface mode
- Light/dark mode manual toggle

### 10.2 UI Improvements
- Recent files list
- Page range text entry (e.g., "1-5, 8, 12-20")
- Standalone executable packaging via PyInstaller

---

## 11. TESTING REQUIREMENTS

### 11.1 Test PDFs
Create or collect a test suite with:
- Simple PDF (5 pages, text only)
- Image-heavy PDF (photos, diagrams, mixed formats)
- Complex PDF (tables, multi-column, formatted text)
- Large PDF (100+ pages)
- PDF with CMYK images
- PDF with transparent (alpha) images
- PDF with duplicate images across pages (e.g., logo on every page)

### 11.2 Test Cases

**File Loading**:
- Valid PDF loads and shows correct page count
- Non-PDF file shows error dialog
- Password-protected PDF shows unsupported message
- Large PDF (500+ pages) shows confirmation dialog
- Loading a new PDF replaces the previous one cleanly

**Drag-and-Drop**:
- Dropping a PDF file loads it
- Dropping a non-PDF file shows error
- Drop zone visual feedback works on hover

**Page Selection**:
- All pages selected by default on load
- Select All / Select None / Invert work correctly
- Clicking a thumbnail toggles its checkbox
- Extract buttons disabled when no pages selected

**Text Extraction**:
- Markdown output is valid Markdown with preserved tables
- Plain text has form-feed separators between pages
- XHTML is a well-formed document with semantic markup
- DOCX opens correctly in Word with headings and basic formatting
- Save dialog defaults to correct filename and location

**Image Extraction**:
- Native format preserves original bytes exactly
- PNG conversion produces valid PNG files
- JPEG conversion strips alpha channel correctly
- WebP conversion produces valid WebP files
- Duplicate images (same xref) are extracted only once
- CMYK images are converted to RGB in all converted formats
- Output filenames use xref-based naming

**UI/Threading**:
- UI remains responsive during thumbnail generation
- UI remains responsive during extraction
- Progress bar updates smoothly
- Extract and Open buttons are disabled during extraction
- Status bar messages are accurate

**Error Recovery**:
- After any error, application returns to ready state
- Can successfully extract after a previous extraction error

---

## 12. CODE STYLE GUIDELINES

### 12.1 Python Style
- **PEP 8** compliance
- **Type hints** for all function signatures (using Python 3.10+ syntax: `list[int]`, `str | None`)
- **Docstrings** for all public classes and methods
- **Maximum line length**: 100 characters

### 12.2 Import Conventions
```python
# Standard library
import os
import re
import threading
from pathlib import Path

# Third-party
import customtkinter
import pymupdf
import pymupdf4llm
from docx import Document as DocxDocument
from PIL import Image
from tkinterdnd2 import TkinterDnD, DND_FILES
```

### 12.3 Example Function Signature
```python
def extract(
    self,
    pages: list[int],
    output_dir: str,
    format: str = "native",
    progress_callback: Callable[[int, int], None] | None = None,
) -> int:
    """Extract images from specified pages with deduplication.

    Args:
        pages: 0-based page indices to extract from.
        output_dir: Directory path for saving extracted images.
        format: Output format — "native", "png", "jpeg", or "webp".
        progress_callback: Optional callback(current, total) for progress.

    Returns:
        Number of unique images successfully extracted.

    Raises:
        OSError: If output directory cannot be created or written to.
    """
```

---

## 13. LICENSING

### 13.1 Dependencies
| Library | License | Implication |
|---------|---------|-------------|
| PyMuPDF | AGPL-3.0 | Copyleft — application must be AGPL-compatible |
| pymupdf4llm | AGPL-3.0 | Same as PyMuPDF |
| CustomTkinter | MIT | Permissive |
| Pillow | HPND (permissive) | No restriction |
| tkinterdnd2 | MIT | Permissive |
| python-docx | MIT | Permissive |

**Implication**: Due to PyMuPDF's AGPL-3.0 license, the application must be released under AGPL-3.0 or a compatible license if distributed.

---

## 14. APPENDIX

### 14.1 PyMuPDF Text Extraction Format Reference

| Format | Method | Output Type | Use Case |
|--------|--------|-------------|----------|
| Markdown | `pymupdf4llm.to_markdown()` | String | LLM/RAG, documentation |
| Plain Text | `page.get_text("text")` | String | Simple text extraction |
| HTML | `page.get_text("html")` | String (fragment) | Web display, formatting |
| Dict/JSON | `page.get_text("dict")` | Dict | Programmatic access |
| XML | `page.get_text("xml")` | String | Advanced parsing |
| XHTML | `page.get_text("xhtml")` | String | Web standards |
| Words | `page.get_text("words")` | List | Word-level analysis |
| Blocks | `page.get_text("blocks")` | List | Block-level structure |

**Note**: Both `"html"` and `"xhtml"` return fragments, not complete documents. Use `pymupdf.ConversionHeader()` and `pymupdf.ConversionTrailer()` to wrap fragments into valid documents with proper structure and CSS.

### 14.2 Image Format Comparison

| Format | Pros | Cons | Best For |
|--------|------|------|----------|
| Native | Preserves original exactly, fastest | Mixed output formats | Archival, exact preservation |
| PNG | Lossless, supports transparency | Larger files | Graphics, diagrams, screenshots |
| JPEG | Small files, widely supported | Lossy, no transparency | Photographs |
| WebP | Excellent quality/size ratio | Less compatible with older software | Web use, modern workflows |

### 14.3 pymupdf4llm Key Parameters (v0.3.x)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `pages` | `None` (all) | List of 0-based page indices |
| `page_chunks` | `False` | If True, returns list of dicts instead of string |
| `table_strategy` | `"lines_strict"` | Table detection: `"lines_strict"`, `"lines"`, or `"text"` |
| `show_progress` | `False` | Print progress to stdout |
| `write_images` | `False` | Save images to disk during extraction |
| `embed_images` | `False` | Embed images as base64 in Markdown |
| `image_format` | `"png"` | Format for extracted/embedded images |
| `ignore_images` | `False` | Skip image extraction entirely |
| `use_ocr` | `True` | Run OCR on pages that need it |
| `force_ocr` | `False` | Force OCR even on pages with embedded text |
| `fontsize_limit` | `3` | Ignore text below this font size |

### 14.4 CustomTkinter Widget Reference

| CTk Widget | Tkinter Equivalent | Used For |
|------------|-------------------|----------|
| `CTk` | `Tk` | Main application window |
| `CTkFrame` | `Frame` | Container panels |
| `CTkScrollableFrame` | Frame + Canvas + Scrollbar | Thumbnail grid |
| `CTkButton` | `Button` | All buttons |
| `CTkLabel` | `Label` | Text labels, thumbnail display |
| `CTkCheckBox` | `Checkbutton` | Page selection checkboxes |
| `CTkRadioButton` | `Radiobutton` | Format selection |
| `CTkProgressBar` | `Progressbar` | Extraction progress |
| `CTkToplevel` | `Toplevel` | Dialogs |
| `CTkImage` | `PhotoImage` | HiDPI-aware image display |

---

## END OF SPECIFICATION
