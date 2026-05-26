"""Text and Image extraction panels with format radio buttons."""

import customtkinter


class TextPanel(customtkinter.CTkFrame):
    """Panel with text format controls and Extract button."""

    FORMATS = {
        0: ("Markdown (.md)", "md"),
        1: ("Plain Text (.txt)", "txt"),
        2: ("XHTML (.xhtml)", "xhtml"),
        3: ("Word (.docx)", "docx"),
        4: ("Foundry VTT Journal (.json)", "fvtt"),
    }

    _TOC_LEVEL_OPTIONS = ["1", "2", "3", "4", "None (1 per page)"]

    def __init__(self, master, extract_command=None, **kwargs):
        super().__init__(master, **kwargs)

        header = customtkinter.CTkLabel(self, text="Extract Text", font=("", 14, "bold"))
        header.pack(padx=10, pady=(10, 5), anchor="w")

        customtkinter.CTkLabel(self, text="Format:").pack(padx=10, anchor="w")

        self._format_var = customtkinter.IntVar(value=0)
        self._radio_buttons: dict[str, customtkinter.CTkRadioButton] = {}

        for value, (label, fmt_key) in self.FORMATS.items():
            rb = customtkinter.CTkRadioButton(
                self, text=label, variable=self._format_var, value=value,
                command=self._on_format_changed,
            )
            rb.pack(padx=20, pady=2, anchor="w")
            self._radio_buttons[fmt_key] = rb

        # Output options — always visible
        customtkinter.CTkLabel(self, text="Output Options:").pack(padx=10, pady=(5, 0), anchor="w")

        self._include_images_var = customtkinter.BooleanVar(value=False)
        self._include_images_cb = customtkinter.CTkCheckBox(
            self, text="Include images",
            variable=self._include_images_var,
            state="disabled",
        )
        self._include_images_cb.pack(padx=20, pady=2, anchor="w")

        self._per_page_var = customtkinter.BooleanVar(value=False)
        self._per_page_cb = customtkinter.CTkCheckBox(
            self, text="One file per page",
            variable=self._per_page_var,
        )
        self._per_page_cb.pack(padx=20, pady=2, anchor="w")

        self._normalize_headers_var = customtkinter.BooleanVar(value=False)
        self._normalize_cb = customtkinter.CTkCheckBox(
            self, text="Normalize header capitalization",
            variable=self._normalize_headers_var,
        )
        self._normalize_cb.pack(padx=20, pady=2, anchor="w")

        # FVTT-only: TOC grouping level
        self._toc_level_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self._toc_level_frame.pack(padx=20, pady=2, anchor="w", fill="x")
        customtkinter.CTkLabel(
            self._toc_level_frame, text="TOC grouping level:"
        ).pack(side="left")
        self._toc_level_var = customtkinter.StringVar(value="2")
        self._toc_level_menu = customtkinter.CTkOptionMenu(
            self._toc_level_frame,
            variable=self._toc_level_var,
            values=self._TOC_LEVEL_OPTIONS,
            width=140,
        )
        self._toc_level_menu.pack(side="left", padx=(6, 0))
        self._toc_level_frame.pack_forget()  # hidden until fvtt selected

        self._extract_btn = customtkinter.CTkButton(
            self, text="Extract Text", command=extract_command, state="disabled"
        )
        self._extract_btn.pack(padx=10, pady=(10, 10))

    def _on_format_changed(self) -> None:
        fmt = self.get_format()
        is_fvtt = fmt == "fvtt"
        self._include_images_cb.configure(
            state="normal" if fmt in ("xhtml", "fvtt") else "disabled"
        )
        self._per_page_cb.configure(
            state="disabled" if fmt in ("docx", "fvtt") else "normal"
        )
        self._normalize_cb.configure(
            state="disabled" if fmt == "txt" else "normal"
        )
        self._toc_level_frame.pack_forget()

    def get_format(self) -> str:
        """Return the selected format key (e.g., 'md', 'txt', 'xhtml', 'docx', 'fvtt')."""
        return self.FORMATS[self._format_var.get()][1]

    def get_options(self) -> dict:
        """Return current option values, masking options disabled for the active format."""
        fmt = self.get_format()
        toc_str = self._toc_level_var.get()
        try:
            toc_level = int(toc_str)
        except ValueError:
            toc_level = 0   # "None (1 per page)" → strategy "page"
        return {
            "include_images": self._include_images_var.get() if fmt in ("xhtml", "fvtt") else False,
            "per_page": self._per_page_var.get() if fmt not in ("docx", "fvtt") else False,
            "normalize_headers": self._normalize_headers_var.get() if fmt != "txt" else False,
            "toc_level": toc_level,
        }

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the Extract button."""
        self._extract_btn.configure(state="normal" if enabled else "disabled")

    def set_fvtt_available(self, available: bool) -> None:
        """Show or hide the Foundry VTT format option."""
        rb = self._radio_buttons.get("fvtt")
        if rb is None:
            return
        rb.configure(state="normal" if available else "disabled")
        if not available and self.get_format() == "fvtt":
            self._format_var.set(0)
            self._on_format_changed()


class ImagePanel(customtkinter.CTkFrame):
    """Panel with image format radio buttons and Extract button."""

    FORMATS = {
        0: ("Native (original format)", "native"),
        1: ("Convert to PNG", "png"),
        2: ("Convert to JPEG", "jpeg"),
        3: ("Convert to WebP", "webp"),
    }

    def __init__(self, master, extract_command=None, **kwargs):
        super().__init__(master, **kwargs)

        header = customtkinter.CTkLabel(self, text="Extract Images", font=("", 14, "bold"))
        header.pack(padx=10, pady=(10, 5), anchor="w")

        format_label = customtkinter.CTkLabel(self, text="Format:")
        format_label.pack(padx=10, anchor="w")

        self._format_var = customtkinter.IntVar(value=0)

        for value, (label, _) in self.FORMATS.items():
            rb = customtkinter.CTkRadioButton(
                self, text=label, variable=self._format_var, value=value
            )
            rb.pack(padx=20, pady=2, anchor="w")

        self._extract_btn = customtkinter.CTkButton(
            self, text="Extract Images", command=extract_command, state="disabled"
        )
        self._extract_btn.pack(padx=10, pady=(10, 10))

    def get_format(self) -> str:
        """Return the selected format key (e.g., 'native', 'png', 'jpeg', 'webp')."""
        return self.FORMATS[self._format_var.get()][1]

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the Extract button."""
        self._extract_btn.configure(state="normal" if enabled else "disabled")
