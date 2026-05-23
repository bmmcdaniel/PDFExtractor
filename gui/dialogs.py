"""Dialog helpers for error and completion messages."""

import logging
import os
import subprocess
import sys

import customtkinter

log = logging.getLogger(__name__)


def _open_path(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def ask_hex_handling(parent, message: str) -> bool:
    """Ask whether to apply book-specific per-page naming. Returns True for Yes.

    *message* is provided by the BookHandler and should be two lines:
    the first identifying the book, the second asking the question.
    """
    result = [False]

    dialog = customtkinter.CTkToplevel(parent)
    dialog.title("Book Detected")
    dialog.geometry("440x160")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    dialog.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - 440) // 2
    y = parent.winfo_y() + (parent.winfo_height() - 160) // 2
    dialog.geometry(f"+{x}+{y}")

    customtkinter.CTkLabel(
        dialog,
        text=message,
        wraplength=400,
        justify="center",
    ).pack(padx=20, pady=(25, 10), fill="both", expand=True)

    btn_frame = customtkinter.CTkFrame(dialog, fg_color="transparent")
    btn_frame.pack(pady=(0, 20))

    def on_yes():
        result[0] = True
        dialog.destroy()

    customtkinter.CTkButton(btn_frame, text="Yes", command=on_yes, width=80).pack(side="left", padx=10)
    customtkinter.CTkButton(btn_frame, text="No", command=dialog.destroy, width=80).pack(side="left", padx=10)

    dialog.after(100, dialog.focus_force)
    dialog.wait_window()
    return result[0]


def show_error(parent, message: str) -> None:
    """Show a themed modal error dialog."""
    dialog = customtkinter.CTkToplevel(parent)
    dialog.title("Error")
    dialog.geometry("400x180")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    # Center on parent
    dialog.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - 400) // 2
    y = parent.winfo_y() + (parent.winfo_height() - 180) // 2
    dialog.geometry(f"+{x}+{y}")

    label = customtkinter.CTkLabel(
        dialog, text=message, wraplength=360, justify="left"
    )
    label.pack(padx=20, pady=(20, 10), fill="both", expand=True)

    ok_btn = customtkinter.CTkButton(dialog, text="OK", command=dialog.destroy, width=80)
    ok_btn.pack(pady=(0, 20))

    dialog.after(100, dialog.focus_force)


def show_completion(
    parent,
    message: str,
    file_path: str | None = None,
    folder_path: str | None = None,
) -> None:
    """Show a themed completion dialog with Open File / Open Folder / OK buttons."""
    dialog = customtkinter.CTkToplevel(parent)
    dialog.title("Complete")
    dialog.geometry("420x180")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    dialog.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - 420) // 2
    y = parent.winfo_y() + (parent.winfo_height() - 180) // 2
    dialog.geometry(f"+{x}+{y}")

    label = customtkinter.CTkLabel(
        dialog, text=message, wraplength=380, justify="left"
    )
    label.pack(padx=20, pady=(20, 10), fill="both", expand=True)

    btn_frame = customtkinter.CTkFrame(dialog, fg_color="transparent")
    btn_frame.pack(pady=(0, 20))

    if file_path:
        def open_file():
            _open_path(file_path)
            dialog.destroy()

        customtkinter.CTkButton(
            btn_frame, text="Open File", command=open_file, width=100
        ).pack(side="left", padx=5)

    if folder_path:
        def open_folder():
            _open_path(folder_path)
            dialog.destroy()

        customtkinter.CTkButton(
            btn_frame, text="Open Folder", command=open_folder, width=100
        ).pack(side="left", padx=5)

    customtkinter.CTkButton(
        btn_frame, text="OK", command=dialog.destroy, width=80
    ).pack(side="left", padx=5)

    dialog.after(100, dialog.focus_force)
