"""Package init, re-exports the public API."""

from .core import count_lines, count_lines_path

__all__ = ["count_lines", "count_lines_path"]
