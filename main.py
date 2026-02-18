"""PDF Text & Image Extractor - Application entry point."""

import logging
import sys

import customtkinter

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(name)s: %(message)s",
    stream=sys.stderr,
)

customtkinter.set_appearance_mode("system")
customtkinter.set_default_color_theme("blue")

from gui.app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
