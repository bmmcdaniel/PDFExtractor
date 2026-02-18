"""Scrollable thumbnail grid widget for PDF page selection."""

from collections.abc import Callable
import tkinter

import customtkinter
from PIL import Image, ImageTk

# Border color for selected state
_SELECTED_BORDER = "#CC3333"

# Preview window settings
_PREVIEW_WIDTH = 720
_PREVIEW_HEIGHT = 960
_PREVIEW_OFFSET = 20
_HOVER_DELAY_MS = 390


class ThumbnailGrid(customtkinter.CTkScrollableFrame):
    """Scrollable grid of PDF page thumbnails with red-border selection."""

    THUMB_WIDTH = 120
    THUMB_HEIGHT = 160
    CELL_PAD = 8
    BORDER_WIDTH = 3

    ZOOM_MIN = 40
    ZOOM_MAX = 240
    ZOOM_STEP = 10
    ZOOM_DEFAULT = 90

    def __init__(
        self,
        master,
        on_selection_changed: Callable[[], None] | None = None,
        preview_callback: Callable[[int], Image.Image | None] | None = None,
        on_zoom_changed: Callable[[int], None] | None = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._cells: list[dict] = []
        self._columns = 1
        self._measured_cell_width: int | None = None
        self._first_cell_frame = None
        self._resize_after_id = None
        self._zoom_level: int = self.ZOOM_DEFAULT
        self._on_selection_changed = on_selection_changed
        self._preview_callback = preview_callback
        self._on_zoom_changed = on_zoom_changed
        self._preview_win: tkinter.Toplevel | None = None
        self._preview_after_id: str | None = None
        self._preview_page_index: int | None = None
        self.bind_all("<Configure>", self._on_configure)
        self.bind_all("<Control-MouseWheel>", self._on_ctrl_scroll)
        self.bind_all("<Control-Double-Button-1>", self._on_ctrl_double_click)
        self.bind("<Leave>", self._on_grid_leave)

    def add_thumbnail(self, index: int, pil_img: Image.Image) -> None:
        """Add a single thumbnail cell to the grid."""
        zoom_w = self._zoom_level
        zoom_h = int(self._zoom_level * (4 / 3))
        ctk_img = customtkinter.CTkImage(
            light_image=pil_img,
            dark_image=pil_img,
            size=(zoom_w, zoom_h),
        )

        cell_frame = customtkinter.CTkFrame(
            self,
            border_width=self.BORDER_WIDTH,
            border_color=_SELECTED_BORDER,
        )

        img_label = customtkinter.CTkLabel(cell_frame, image=ctk_img, text="")
        img_label.pack(padx=2, pady=2)

        selected = customtkinter.BooleanVar(value=True)

        cell = {
            "frame": cell_frame,
            "image_label": img_label,
            "selected": selected,
            "ctk_image": ctk_img,
            "page_index": index,
        }
        self._cells.append(cell)

        # Grid cells progressively so thumbnails appear as they load.
        # Event bindings are deferred to finish_loading() to keep
        # per-thumbnail overhead minimal.
        if index == 0:
            cell_frame.grid(row=0, column=0,
                            padx=self.CELL_PAD, pady=self.CELL_PAD, sticky="n")
            self._first_cell_frame = cell_frame
            self._columns = 1
        elif index == 1 and self._measured_cell_width is None:
            cell_frame.grid(row=0, column=1,
                            padx=self.CELL_PAD, pady=self.CELL_PAD, sticky="n")
            self.update_idletasks()

            x0 = self._first_cell_frame.winfo_x()
            x1 = cell_frame.winfo_x()
            self._measured_cell_width = x1 - x0

            if self._measured_cell_width <= 0:
                req_w = self._first_cell_frame.winfo_reqwidth()
                self._measured_cell_width = req_w + self.CELL_PAD * 2

            self._first_cell_frame = None
            self._columns = self._calc_columns()
            self._layout_grid()
        else:
            row = index // self._columns
            col = index % self._columns
            cell_frame.grid(row=row, column=col,
                            padx=self.CELL_PAD, pady=self.CELL_PAD, sticky="n")

    def finish_loading(self) -> None:
        """Bind events, calculate layout, and grid all cells."""
        for cell in self._cells:
            cf = cell["frame"]
            lbl = cell["image_label"]
            # Bind directly to the frame and its label rather than walking
            # the full CTk widget tree recursively.
            for widget in (cf, lbl):
                widget.bind("<Button-1>",
                            lambda e, c=cell: self._toggle_cell(c))
                widget.bind("<Button-3>",
                            lambda e, c=cell: self._on_cell_right_click(c, e))
                widget.bind("<Enter>",
                            lambda e, c=cell: self._on_cell_enter(c))
                widget.bind("<Leave>",
                            lambda e, c=cell: self._on_cell_leave(c))
                widget.bind("<Motion>",
                            lambda e: self._on_cell_motion(e))

        if self._cells and self._measured_cell_width:
            self.update_idletasks()
            self._columns = self._calc_columns()
            self._layout_grid()

    def _calc_columns(self) -> int:
        """Calculate how many columns fit in the available width."""
        if not self._measured_cell_width:
            return 1

        widths = []
        try:
            widths.append(self._parent_canvas.winfo_width())
        except Exception:
            pass
        try:
            widths.append(self._parent_frame.winfo_width())
        except Exception:
            pass

        if not widths or max(widths) <= 1:
            available = self.master.winfo_width() - 50
        else:
            available = min(widths)

        return max(1, available // self._measured_cell_width)

    @staticmethod
    def _bind_recursive(widget, event: str, handler) -> None:
        """Bind an event handler to a widget and all its descendants."""
        widget.bind(event, handler)
        for child in widget.winfo_children():
            ThumbnailGrid._bind_recursive(child, event, handler)

    def _toggle_cell(self, cell: dict) -> None:
        """Toggle a cell's selection and update its border."""
        new_val = not cell["selected"].get()
        cell["selected"].set(new_val)
        self._update_cell_border(cell)
        self._notify_selection_changed()

    def _update_cell_border(self, cell: dict) -> None:
        """Set cell border color based on selection state."""
        if cell["selected"].get():
            cell["frame"].configure(border_color=_SELECTED_BORDER)
        else:
            fg = cell["frame"].cget("fg_color")
            cell["frame"].configure(border_color=fg)

    def _notify_selection_changed(self) -> None:
        """Call the selection-changed callback if set."""
        if self._on_selection_changed:
            self._on_selection_changed()

    def _on_configure(self, event) -> None:
        """Debounced resize handler to recalculate columns."""
        if event.widget is not self and event.widget is not self._parent_frame:
            return
        if not self._cells or not self._measured_cell_width:
            return
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(150, self._recalc_columns)

    def _recalc_columns(self) -> None:
        """Recalculate column count based on current width."""
        self._resize_after_id = None
        new_cols = self._calc_columns()
        if new_cols != self._columns:
            self._columns = new_cols
            self._layout_grid()

    def _on_ctrl_scroll(self, event) -> None:
        """Zoom thumbnails on Ctrl+scroll."""
        if not self._cells:
            return
        if event.delta > 0:
            new_zoom = min(self._zoom_level + self.ZOOM_STEP, self.ZOOM_MAX)
        else:
            new_zoom = max(self._zoom_level - self.ZOOM_STEP, self.ZOOM_MIN)
        if new_zoom == self._zoom_level:
            return
        self._zoom_level = new_zoom
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        """Resize all thumbnails to the current zoom level and relayout."""
        zoom_w = self._zoom_level
        zoom_h = int(self._zoom_level * (4 / 3))
        for cell in self._cells:
            cell["ctk_image"].configure(size=(zoom_w, zoom_h))

        # Re-measure cell width empirically (same approach as initial load)
        # to capture actual DPI-scaled pixel distances.
        if len(self._cells) >= 2:
            self._cells[0]["frame"].grid(row=0, column=0,
                                         padx=self.CELL_PAD, pady=self.CELL_PAD, sticky="n")
            self._cells[1]["frame"].grid(row=0, column=1,
                                         padx=self.CELL_PAD, pady=self.CELL_PAD, sticky="n")
            self.update_idletasks()
            x0 = self._cells[0]["frame"].winfo_x()
            x1 = self._cells[1]["frame"].winfo_x()
            if x1 - x0 > 0:
                self._measured_cell_width = x1 - x0
        elif self._cells:
            self.update_idletasks()
            req_w = self._cells[0]["frame"].winfo_reqwidth()
            self._measured_cell_width = req_w + self.CELL_PAD * 2

        self._columns = self._calc_columns()
        self._layout_grid()
        if self._on_zoom_changed:
            self._on_zoom_changed(self._zoom_level)

    def _on_ctrl_double_click(self, event) -> None:
        """Reset zoom to default on Ctrl+double-click."""
        if not self._cells:
            return
        if self._zoom_level != self.ZOOM_DEFAULT:
            self._zoom_level = self.ZOOM_DEFAULT
            self._apply_zoom()

    def _layout_grid(self) -> None:
        """Re-place all cells in a grid layout."""
        for cell in self._cells:
            cell["frame"].grid_forget()

        for i, cell in enumerate(self._cells):
            row = i // self._columns
            col = i % self._columns
            cell["frame"].grid(
                row=row, column=col,
                padx=self.CELL_PAD, pady=self.CELL_PAD,
                sticky="n",
            )

    def select_all(self) -> None:
        """Select all pages."""
        for cell in self._cells:
            cell["selected"].set(True)
            self._update_cell_border(cell)
        self._notify_selection_changed()

    def select_none(self) -> None:
        """Deselect all pages."""
        for cell in self._cells:
            cell["selected"].set(False)
            self._update_cell_border(cell)
        self._notify_selection_changed()

    def invert_selection(self) -> None:
        """Toggle each page's selection."""
        for cell in self._cells:
            cell["selected"].set(not cell["selected"].get())
            self._update_cell_border(cell)
        self._notify_selection_changed()

    def get_selected_pages(self) -> list[int]:
        """Return list of 0-based page indices that are selected."""
        return [i for i, cell in enumerate(self._cells) if cell["selected"].get()]

    def get_selection_count(self) -> int:
        """Return number of currently selected pages."""
        return sum(1 for cell in self._cells if cell["selected"].get())

    def get_total_count(self) -> int:
        """Return total number of pages."""
        return len(self._cells)

    # --- Right-click context menu ---

    def _on_cell_right_click(self, cell: dict, event) -> None:
        """Show context menu on right-click."""
        idx = self._cells.index(cell)

        # Match CTk theme colors and font size
        mode = customtkinter.get_appearance_mode()
        if mode == "Dark":
            bg, fg, abg, afg = "#2b2b2b", "#dce4ee", "#3b8ed0", "#ffffff"
        else:
            bg, fg, abg, afg = "#f0f0f0", "#1a1a1a", "#3b8ed0", "#ffffff"

        scaling = self._get_widget_scaling()
        font = ("Segoe UI", int(10 * scaling))

        menu = tkinter.Menu(self, tearoff=0, bg=bg, fg=fg,
                            activebackground=abg, activeforeground=afg,
                            font=font, borderwidth=1, relief="flat")
        menu.add_command(label="Select All", command=self.select_all)
        menu.add_command(label="Select None", command=self.select_none)
        menu.add_command(label="Invert Selection", command=self.invert_selection)
        menu.add_separator()
        menu.add_command(label="Select This and All After",
                         command=lambda: self._select_from(idx))
        menu.add_command(label="Select Only This",
                         command=lambda: self._select_only(idx))
        menu.add_command(label="Deselect Only This",
                         command=lambda: self._deselect_only(idx))
        menu.post(event.x_root, event.y_root)

    def _select_from(self, index: int) -> None:
        """Select the cell at index and all cells after it."""
        for i, cell in enumerate(self._cells):
            cell["selected"].set(i >= index)
            self._update_cell_border(cell)
        self._notify_selection_changed()

    def _select_only(self, index: int) -> None:
        """Deselect all cells except the one at index."""
        for i, cell in enumerate(self._cells):
            cell["selected"].set(i == index)
            self._update_cell_border(cell)
        self._notify_selection_changed()

    def _deselect_only(self, index: int) -> None:
        """Deselect only the cell at index, leaving others unchanged."""
        cell = self._cells[index]
        cell["selected"].set(False)
        self._update_cell_border(cell)
        self._notify_selection_changed()

    # --- Hover preview ---

    def _on_cell_enter(self, cell: dict) -> None:
        """Start hover timer when mouse enters a cell."""
        if not self._preview_callback:
            return
        page_index = cell["page_index"]
        # If already showing preview for this page, do nothing
        if self._preview_win and self._preview_page_index == page_index:
            return
        self._cancel_preview()
        self._preview_after_id = self.after(
            _HOVER_DELAY_MS, lambda: self._show_preview(page_index)
        )

    def _on_cell_leave(self, cell: dict) -> None:
        """Cancel pending timer and destroy preview on mouse leave."""
        # Only dismiss if the mouse actually left the cell boundary,
        # not just crossed between child widgets within the same cell.
        frame = cell["frame"]
        try:
            rx, ry = frame.winfo_rootx(), frame.winfo_rooty()
            mx, my = frame.winfo_pointerxy()
            if (rx <= mx < rx + frame.winfo_width()
                    and ry <= my < ry + frame.winfo_height()):
                return
        except tkinter.TclError:
            pass
        self._cancel_preview()
        self._destroy_preview()

    def _on_grid_leave(self, event) -> None:
        """Dismiss preview when the mouse leaves the grid entirely."""
        self._cancel_preview()
        self._destroy_preview()

    def _on_cell_motion(self, event) -> None:
        """Reposition preview window to follow the cursor."""
        if not self._preview_win:
            return
        # Get absolute cursor position
        x = event.widget.winfo_rootx() + event.x
        y = event.widget.winfo_rooty() + event.y
        self._position_preview(x, y)

    def _show_preview(self, page_index: int) -> None:
        """Render and display the large preview window."""
        self._preview_after_id = None
        if not self._preview_callback:
            return
        pil_img = self._preview_callback(page_index)
        if pil_img is None:
            return

        self._destroy_preview()
        self._preview_page_index = page_index

        win = tkinter.Toplevel(self)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        # Make the window non-interactive so mouse events pass through
        try:
            win.attributes("-transparentcolor", "")
        except tkinter.TclError:
            pass

        # Resize the HiDPI source image to display size
        display_img = pil_img.resize(
            (_PREVIEW_WIDTH, _PREVIEW_HEIGHT), Image.LANCZOS
        )
        photo = ImageTk.PhotoImage(display_img)
        label = tkinter.Label(win, image=photo, borderwidth=0, highlightthickness=0)
        label._photo = photo  # prevent GC
        label.pack()

        # Position near the current cursor
        x, y = win.winfo_pointerxy()
        self._preview_win = win
        self._position_preview(x, y)

    def _position_preview(self, cursor_x: int, cursor_y: int) -> None:
        """Position preview window near cursor, clamping to screen bounds."""
        win = self._preview_win
        if not win:
            return
        win.update_idletasks()
        pw = win.winfo_reqwidth()
        ph = win.winfo_reqheight()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()

        x = cursor_x + _PREVIEW_OFFSET
        y = cursor_y + _PREVIEW_OFFSET

        # Flip to left of cursor if it would go off the right edge
        if x + pw > sw:
            x = cursor_x - _PREVIEW_OFFSET - pw
        # Flip above cursor if it would go off the bottom edge
        if y + ph > sh:
            y = cursor_y - _PREVIEW_OFFSET - ph

        # Clamp to screen
        x = max(0, x)
        y = max(0, y)

        win.geometry(f"+{x}+{y}")

    def _cancel_preview(self) -> None:
        """Cancel any pending hover timer."""
        if self._preview_after_id is not None:
            self.after_cancel(self._preview_after_id)
            self._preview_after_id = None

    def _destroy_preview(self) -> None:
        """Destroy the preview window if it exists."""
        if self._preview_win is not None:
            self._preview_win.destroy()
            self._preview_win = None
            self._preview_page_index = None

    def clear(self) -> None:
        """Remove all thumbnail cells."""
        self._cancel_preview()
        self._destroy_preview()
        for cell in self._cells:
            cell["frame"].destroy()
        self._cells.clear()
        self._measured_cell_width = None
        self._first_cell_frame = None
        self._columns = 1
        self._zoom_level = self.ZOOM_DEFAULT
