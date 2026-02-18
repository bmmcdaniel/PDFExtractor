"""Main application window with drag-and-drop, thumbnails, and extraction."""

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog

import customtkinter
from PIL import Image
from tkinterdnd2 import TkinterDnD, DND_FILES

from core.image_extractor import ImageExtractor
from core.pdf_handler import PDFHandler
from core.settings import load_settings, save_settings
from core.text_extractor import TextExtractor
from gui.dialogs import show_completion, show_error
from gui.extraction_panel import ImagePanel, TextPanel
from gui.thumbnail_grid import ThumbnailGrid

log = logging.getLogger(__name__)


class App(customtkinter.CTk, TkinterDnD.DnDWrapper):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)

        self.title("PDF Text & Image Extractor")
        self.geometry("920x750")
        self.minsize(800, 600)

        self._pdf_handler: PDFHandler | None = None
        self._working = False
        self._settings = load_settings()
        self._zoom_status_after_id: str | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        """Create all UI widgets."""
        # --- Top: Filename label + Open button ---
        top_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        self._file_label = customtkinter.CTkLabel(
            top_frame,
            text="No PDF loaded",
            anchor="w",
        )
        self._file_label.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self._open_btn = customtkinter.CTkButton(
            top_frame, text="Open", width=80, command=self._browse_pdf
        )
        self._open_btn.pack(side="right")

        # --- Middle: Thumbnail grid ---
        self._thumb_grid = ThumbnailGrid(
            self,
            height=300,
            on_selection_changed=self._on_selection_changed,
            preview_callback=self._get_preview_image,
            on_zoom_changed=self._on_zoom_changed,
        )
        self._thumb_grid.pack(fill="both", expand=True, padx=10, pady=5)

        # Register drag-and-drop on the main window so drops work anywhere
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self._on_file_drop)

        # --- Selection buttons ---
        sel_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        sel_frame.pack(fill="x", padx=10, pady=5)

        customtkinter.CTkButton(
            sel_frame, text="Select All", width=110,
            command=self._thumb_grid.select_all,
        ).pack(side="left", padx=(0, 5))

        customtkinter.CTkButton(
            sel_frame, text="Select None", width=110,
            command=self._thumb_grid.select_none,
        ).pack(side="left", padx=5)

        customtkinter.CTkButton(
            sel_frame, text="Invert Selection", width=130,
            command=self._thumb_grid.invert_selection,
        ).pack(side="left", padx=5)

        # --- Extraction panels ---
        panels_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        panels_frame.pack(fill="x", padx=10, pady=5)

        self._text_panel = TextPanel(
            panels_frame, extract_command=self._extract_text
        )
        self._text_panel.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self._image_panel = ImagePanel(
            panels_frame, extract_command=self._extract_images
        )
        self._image_panel.pack(side="left", fill="both", expand=True, padx=(5, 0))

        # --- Status bar ---
        status_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        status_frame.pack(fill="x", padx=10, pady=(5, 10))

        self._status_label = customtkinter.CTkLabel(
            status_frame, text="Ready", anchor="w"
        )
        self._status_label.pack(side="left", fill="x", expand=True)

        self._progress_bar = customtkinter.CTkProgressBar(status_frame, width=200)
        self._progress_bar.pack(side="right")
        self._progress_bar.set(0)
        self._progress_bar.pack_forget()  # Hidden until needed

        # --- Keyboard shortcuts ---
        self.bind_all("<Control-o>", lambda e: self._browse_pdf() if not self._working else None)
        self.bind_all("<Control-a>", lambda e: self._thumb_grid.select_all() if not self._working else None)
        self.bind_all("<Control-Shift-A>", lambda e: self._thumb_grid.select_none() if not self._working else None)
        self.bind_all("<Control-i>", lambda e: self._thumb_grid.invert_selection() if not self._working else None)

    # --- Preview callback ---

    def _get_preview_image(self, page_index: int) -> Image.Image | None:
        """Return a large preview image for the given page, or None."""
        if not self._pdf_handler or self._working:
            return None
        return self._pdf_handler.get_thumbnail(page_index, width=720, height=960, hidpi=True)

    # --- Zoom indicator ---

    def _on_zoom_changed(self, zoom_level: int) -> None:
        """Briefly show zoom percentage in the status bar."""
        if self._zoom_status_after_id is not None:
            self.after_cancel(self._zoom_status_after_id)
        pct = int(zoom_level / ThumbnailGrid.ZOOM_DEFAULT * 100)
        self._set_status(f"Zoom: {pct}%")
        self._zoom_status_after_id = self.after(1500, self._restore_status_after_zoom)

    def _restore_status_after_zoom(self) -> None:
        """Restore the selection-based status after zoom indicator fades."""
        self._zoom_status_after_id = None
        self._on_selection_changed()

    # --- Selection feedback ---

    def _on_selection_changed(self) -> None:
        """Update status bar when page selection changes."""
        selected = self._thumb_grid.get_selection_count()
        total = self._thumb_grid.get_total_count()
        if selected == total:
            self._set_status(f"All {total} pages selected")
        elif selected == 0:
            self._set_status("No pages selected")
        else:
            self._set_status(f"{selected} of {total} pages selected")

    # --- File loading ---

    def _browse_pdf(self) -> None:
        """Open file dialog to select a PDF."""
        if self._working:
            return
        filepath = filedialog.askopenfilename(
            title="Open PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialdir=self._settings.get("last_open_dir"),
        )
        if filepath:
            self._settings["last_open_dir"] = str(Path(filepath).parent)
            save_settings(self._settings)
            self._load_pdf(filepath)

    def _on_file_drop(self, event) -> None:
        """Handle a file dropped on the thumbnail grid."""
        if self._working:
            return
        filepath = event.data
        # Windows may wrap path in braces if it contains spaces
        if filepath.startswith("{") and filepath.endswith("}"):
            filepath = filepath[1:-1]
        if filepath.lower().endswith(".pdf"):
            self._load_pdf(filepath)
        else:
            show_error(self, "Please drop a PDF file.")

    def _load_pdf(self, filepath: str) -> None:
        """Load a PDF and generate thumbnails."""
        # Close previous
        if self._pdf_handler:
            self._pdf_handler.close()
            self._pdf_handler = None

        self._thumb_grid.clear()
        self._text_panel.set_enabled(False)
        self._image_panel.set_enabled(False)

        try:
            handler = PDFHandler(filepath)
        except ValueError as exc:
            show_error(self, str(exc))
            self._file_label.configure(text="No PDF loaded")
            return

        self._pdf_handler = handler

        # Large PDF warning
        if handler.page_count > 500:
            from tkinter import messagebox
            proceed = messagebox.askyesno(
                "Large PDF",
                f"This PDF has {handler.page_count} pages. "
                "Generating thumbnails may take a moment. Continue?",
            )
            if not proceed:
                handler.close()
                self._pdf_handler = None
                self._file_label.configure(text="No PDF loaded")
                return

        self._file_label.configure(
            text=f"{handler.filename} ({handler.page_count} pages)"
        )
        self._set_status(f"Loading {handler.filename}...")
        self._show_progress()
        self._set_ui_locked(True)

        def generate():
            total = handler.page_count
            batch = []
            batch_size = 10
            workers = min(4, os.cpu_count() or 1)

            # PyMuPDF releases the GIL during get_pixmap(), so multiple
            # threads can render different pages truly in parallel.
            with ThreadPoolExecutor(max_workers=workers) as pool:
                thumbs = pool.map(handler.get_thumbnail, range(total))
                for i, thumb in enumerate(thumbs):
                    batch.append((i, thumb))
                    if len(batch) >= batch_size or i == total - 1:
                        self.after(0, self._add_thumbnail_batch, list(batch))
                        self.after(0, self._update_progress, i + 1, total)
                        batch.clear()
            return total

        self._run_in_thread(
            target=generate,
            on_complete=self._on_thumbnails_loaded,
            on_error=self._on_load_error,
        )

    def _add_thumbnail_batch(self, batch: list) -> None:
        """Add a batch of thumbnails to the grid (called on main thread)."""
        for index, pil_img in batch:
            self._thumb_grid.add_thumbnail(index, pil_img)

    def _on_thumbnails_loaded(self, total) -> None:
        """Handle successful thumbnail generation."""
        self._thumb_grid.finish_loading()
        self._text_panel.set_enabled(True)
        self._image_panel.set_enabled(True)
        self._set_status(f"All {total} pages selected")
        self._hide_progress()
        self._set_ui_locked(False)

    def _on_load_error(self, exc: Exception) -> None:
        """Handle thumbnail generation failure."""
        log.exception("Error loading PDF")
        show_error(self, f"Error loading PDF: {exc}")
        self._set_status("Ready")
        self._hide_progress()
        self._set_ui_locked(False)

    # --- Text extraction ---

    def _extract_text(self) -> None:
        """Start text extraction for selected pages."""
        if self._working or not self._pdf_handler:
            return

        pages = self._thumb_grid.get_selected_pages()
        if not pages:
            show_error(self, "Please select at least one page.")
            return

        fmt = self._text_panel.get_format()

        ext_map = {
            "md": ("Markdown files", "*.md", ".md"),
            "txt": ("Text files", "*.txt", ".txt"),
            "xhtml": ("XHTML files", "*.xhtml", ".xhtml"),
            "docx": ("Word documents", "*.docx", ".docx"),
        }
        desc, pattern, ext = ext_map[fmt]

        default_dir = self._settings.get(
            "last_save_dir", str(Path(self._pdf_handler.filepath).parent)
        )
        default_name = f"{self._pdf_handler.stem}{ext}"

        output_path = filedialog.asksaveasfilename(
            title="Save Extracted Text",
            initialdir=default_dir,
            initialfile=default_name,
            filetypes=[(desc, pattern), ("All files", "*.*")],
            defaultextension=ext,
        )
        if not output_path:
            return

        self._settings["last_save_dir"] = str(Path(output_path).parent)
        save_settings(self._settings)

        self._set_status(f"Extracting text from {len(pages)} pages...")
        self._show_progress()
        self._set_ui_locked(True)

        extractor = TextExtractor(self._pdf_handler)
        extract_fn = {
            "md": extractor.extract_markdown,
            "txt": extractor.extract_plain_text,
            "xhtml": extractor.extract_xhtml,
            "docx": extractor.extract_docx,
        }[fmt]

        def do_extract():
            extract_fn(
                pages=pages,
                output_path=output_path,
                progress_callback=lambda c, t: self.after(0, self._update_progress, c, t),
            )
            return output_path

        self._run_in_thread(
            target=do_extract,
            on_complete=self._on_text_extracted,
            on_error=self._on_extract_error,
        )

    def _on_text_extracted(self, output_path: str) -> None:
        """Handle successful text extraction."""
        self._set_status("Text extracted successfully")
        self._hide_progress()
        self._set_ui_locked(False)
        show_completion(
            self,
            "Text extracted successfully.",
            file_path=output_path,
            folder_path=str(Path(output_path).parent),
        )

    # --- Image extraction ---

    def _extract_images(self) -> None:
        """Start image extraction for selected pages."""
        if self._working or not self._pdf_handler:
            return

        pages = self._thumb_grid.get_selected_pages()
        if not pages:
            show_error(self, "Please select at least one page.")
            return

        fmt = self._image_panel.get_format()
        default_dir = self._settings.get(
            "last_image_dir", str(Path(self._pdf_handler.filepath).parent)
        )

        output_dir = filedialog.askdirectory(
            title="Select Output Folder for Images",
            initialdir=default_dir,
        )
        if not output_dir:
            return

        self._settings["last_image_dir"] = str(output_dir)
        save_settings(self._settings)

        self._set_status("Extracting images...")
        self._show_progress()
        self._set_ui_locked(True)

        extractor = ImageExtractor(self._pdf_handler)

        def do_extract():
            count = extractor.extract(
                pages=pages,
                output_dir=output_dir,
                format=fmt,
                progress_callback=lambda c, t: self.after(0, self._update_progress, c, t),
            )
            return count, output_dir

        self._run_in_thread(
            target=do_extract,
            on_complete=self._on_images_extracted,
            on_error=self._on_extract_error,
        )

    def _on_images_extracted(self, result: tuple) -> None:
        """Handle successful image extraction."""
        count, output_dir = result
        if count == 0:
            self._set_status("No images found on the selected pages.")
            self._hide_progress()
            self._set_ui_locked(False)
            show_error(self, "No images found on the selected pages.")
            return

        self._set_status(f"Extracted {count} images")
        self._hide_progress()
        self._set_ui_locked(False)
        show_completion(
            self,
            f"Extracted {count} unique images.",
            folder_path=output_dir,
        )

    def _on_extract_error(self, exc: Exception) -> None:
        """Handle extraction failure."""
        log.exception("Extraction error")
        self._set_status("Extraction failed")
        self._hide_progress()
        self._set_ui_locked(False)

        msg = str(exc)
        if isinstance(exc, PermissionError):
            msg = "Cannot write to the selected location. Please choose a different folder."
        elif isinstance(exc, OSError) and "No space" in str(exc):
            msg = "Not enough disk space to complete the extraction."

        show_error(self, msg)

    # --- Threading helper ---

    def _run_in_thread(self, target, on_complete, on_error) -> None:
        """Run target function in a background thread."""
        def wrapper():
            try:
                result = target()
                self.after(0, on_complete, result)
            except Exception as e:
                self.after(0, on_error, e)

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()

    # --- UI helpers ---

    def _set_status(self, text: str) -> None:
        """Update status bar text."""
        self._status_label.configure(text=text)

    def _show_progress(self) -> None:
        """Show and reset the progress bar."""
        self._progress_bar.set(0)
        self._progress_bar.pack(side="right")

    def _hide_progress(self) -> None:
        """Hide the progress bar."""
        self._progress_bar.pack_forget()

    def _update_progress(self, current: int, total: int) -> None:
        """Update progress bar value."""
        if total > 0:
            self._progress_bar.set(current / total)

    def _set_ui_locked(self, locked: bool) -> None:
        """Lock or unlock UI during operations."""
        self._working = locked
        state = "disabled" if locked else "normal"
        self._open_btn.configure(state=state)
        if not locked and self._pdf_handler:
            self._text_panel.set_enabled(True)
            self._image_panel.set_enabled(True)
        else:
            self._text_panel.set_enabled(not locked and self._pdf_handler is not None)
            self._image_panel.set_enabled(not locked and self._pdf_handler is not None)
