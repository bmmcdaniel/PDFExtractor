# This module has been superseded by core.book_handlers.
# It is kept only so that any external scripts that imported from here
# continue to work.  New code should use core.book_handlers directly.
from core.book_handlers import get_handler
from core.book_handlers.dolmenwood import DolmenwoodHandler

_handler = DolmenwoodHandler()
is_dolmenwood    = _handler.detect
build_filename_map = _handler.build_filename_map
