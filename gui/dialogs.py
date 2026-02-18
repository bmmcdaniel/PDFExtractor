"""Dialog helpers for error and completion messages."""

import logging
import os

import customtkinter

log = logging.getLogger(__name__)


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
            os.startfile(file_path)
            dialog.destroy()

        customtkinter.CTkButton(
            btn_frame, text="Open File", command=open_file, width=100
        ).pack(side="left", padx=5)

    if folder_path:
        def open_folder():
            os.startfile(folder_path)
            dialog.destroy()

        customtkinter.CTkButton(
            btn_frame, text="Open Folder", command=open_folder, width=100
        ).pack(side="left", padx=5)

    customtkinter.CTkButton(
        btn_frame, text="OK", command=dialog.destroy, width=80
    ).pack(side="left", padx=5)

    dialog.after(100, dialog.focus_force)
