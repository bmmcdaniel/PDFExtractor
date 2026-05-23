"""Text and Image extraction panels with format radio buttons."""

import customtkinter


class TextPanel(customtkinter.CTkFrame):
    """Panel with text format controls and Extract button."""

    FORMATS = {
        0: ("Markdown (.md)", "md"),
        1: ("Plain Text (.txt)", "txt"),
        2: ("XHTML (.xhtml)", "xhtml"),
        3: ("Word (.docx)", "docx"),
    }

    def __init__(self, master, extract_command=None, **kwargs):
        super().__init__(master, **kwargs)

        header = customtkinter.CTkLabel(self, text="Extract Text", font=("", 14, "bold"))
        header.pack(padx=10, pady=(10, 5), anchor="w")

        customtkinter.CTkLabel(self, text="Format:").pack(padx=10, anchor="w")

        self._format_var = customtkinter.IntVar(value=0)

        for value, (label, _) in self.FORMATS.items():
            rb = customtkinter.CTkRadioButton(
                self, text=label, variable=self._format_var, value=value,
                command=self._on_format_changed,
            )
            rb.pack(padx=20, pady=2, anchor="w")

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

        self._extract_btn = customtkinter.CTkButton(
            self, text="Extract Text", command=extract_command, state="disabled"
        )
        self._extract_btn.pack(padx=10, pady=(10, 10))

    def _on_format_changed(self) -> None:
        fmt = self.get_format()
        self._include_images_cb.configure(state="normal" if fmt == "xhtml" else "disabled")
        self._per_page_cb.configure(state="disabled" if fmt == "docx" else "normal")
        self._normalize_cb.configure(state="disabled" if fmt == "txt" else "normal")

    def get_format(self) -> str:
        """Return the selected format key (e.g., 'md', 'txt', 'xhtml', 'docx')."""
        return self.FORMATS[self._format_var.get()][1]

    def get_options(self) -> dict:
        """Return current option values, masking options disabled for the active format."""
        fmt = self.get_format()
        return {
            "include_images": self._include_images_var.get() if fmt == "xhtml" else False,
            "per_page": self._per_page_var.get() if fmt != "docx" else False,
            "normalize_headers": self._normalize_headers_var.get() if fmt != "txt" else False,
        }

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the Extract button."""
        self._extract_btn.configure(state="normal" if enabled else "disabled")


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
