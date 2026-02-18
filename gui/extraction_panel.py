"""Text and Image extraction panels with format radio buttons."""

import customtkinter


class TextPanel(customtkinter.CTkFrame):
    """Panel with text format radio buttons and Extract button."""

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

        format_label = customtkinter.CTkLabel(self, text="Format:")
        format_label.pack(padx=10, anchor="w")

        self._format_var = customtkinter.IntVar(value=0)

        for value, (label, _) in self.FORMATS.items():
            rb = customtkinter.CTkRadioButton(
                self, text=label, variable=self._format_var, value=value
            )
            rb.pack(padx=20, pady=2, anchor="w")

        self._extract_btn = customtkinter.CTkButton(
            self, text="Extract Text", command=extract_command, state="disabled"
        )
        self._extract_btn.pack(padx=10, pady=(10, 10))

    def get_format(self) -> str:
        """Return the selected format key (e.g., 'md', 'txt', 'xhtml', 'docx')."""
        return self.FORMATS[self._format_var.get()][1]

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
