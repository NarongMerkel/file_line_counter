"""Core line-counting logic.

Design choices
---------------

* Iteration is over bytes, not str. Opening in text mode under Python 3
  triggers universal-newline translation, which means the interpreter has to
  decode the whole buffer and split on \r, \r\n, and \n. For line *counting*
  we do not care about the visual representation of each line, so decoding
  is pure overhead and a potential UnicodeDecodeError on files that are not
  valid UTF-8. Reading raw bytes and splitting on b'\n' is faster and never
  crashes on bad encodings. The cost is that blank/comment detection works
  on byte literals.

* Comment-prefix matching is a simple startswith on the stripped line. We do
  not support multi-character comment markers that contain leading whitespace
  (such as `  #  comment` where the user wants to treat only `#` as a marker).
  That is a deliberate simplification: stripping then startswith covers the
  overwhelmingly common cases (#, //, ;, --) without a regex engine.

* A line is "blank" iff, after stripping ASCII whitespace (b' \t\r\n\v\f'),
  it is empty. We use bytes.strip() with no arguments, which strips the same
  set of ASCII whitespace the test suite checks. Non-ASCII whitespace is not
  considered blank; documenting this keeps the behaviour predictable.

* The final line of the file is counted even if it has no trailing newline.
  This matches `wc -l`'s behaviour for files that *do* end in a newline (it
  counts the newlines) and the intuitive count for files that do not. We
  implement this by counting newlines and then adding one if the last chunk
  we read was non-empty and did not end in a newline.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional, Union

# 64 KiB matches the default pipe buffer / io block size on most platforms.
# Bigger blocks trade memory for fewer read() syscalls; this is a reasonable
# middle ground and also what the stdlib's csv reader uses internally.
_CHUNK_SIZE = 64 * 1024

# bytes.strip() with no argument removes this set of ASCII whitespace.
# We pin it to a named constant so the test suite can document the same
# definition without magic literals.
_ASCII_WHITESPACE = b" \t\r\n\x0b\x0c"


def _iter_file_chunks(path: Union[str, "os.PathLike[str]"], chunk_size: int) -> Iterable[bytes]:
    """Yield successive byte chunks from *path*.

    The file is opened in binary mode and closed when the generator is
    exhausted or garbage-collected. Using a generator (rather than reading
    the whole file) is what keeps peak memory bounded by *chunk_size*.
    """
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                return
            yield chunk


def count_lines(
    source: Union[str, "os.PathLike[str]", Iterable[bytes]],
    *,
    skip_blank: bool = False,
    skip_comment: Optional[bytes] = None,
    chunk_size: int = _CHUNK_SIZE,
) -> int:
    """Count lines in *source* without loading it fully into memory.

    *source* may be a filesystem path (str or os.PathLike) or an iterable
    of ``bytes`` chunks. Passing an iterable lets callers feed sockets,
    pipes, or in-memory byte streams without a temporary file.

    Parameters
    ----------
    skip_blank
        If true, lines that are empty after stripping ASCII whitespace are
        not counted.
    skip_comment
        If set to a byte prefix such as ``b'#'`` or ``b'//'``, lines whose
        first non-whitespace bytes begin with this prefix are not counted.
        Comparison is case-sensitive.
    chunk_size
        Read size in bytes when *source* is a path. Ignored for iterables.

    Returns
    -------
    int
        The number of lines, respecting the skip flags.

    Notes
    -----
    A file that is completely empty yields 0. A file containing a single
    byte with no newline yields 1. This is the same convention used by
    ``wc -l`` on a file without a trailing newline.
    """
    if isinstance(source, (str, os.PathLike)):
        chunks = _iter_file_chunks(source, chunk_size)
    else:
        chunks = source

    total = 0
    # When skip_blank or skip_comment is active we need to examine individual
    # lines, which means splitting on b'\n' across chunk boundaries. We keep
    # the trailing partial line in `carry` and prepend it to the next chunk.
    #
    # When neither skip flag is active we avoid the per-line split entirely
    # and just count b'\n' bytes, which is dramatically faster on large
    # files. This fast path also sidesteps the need to track `carry`.
    if not skip_blank and skip_comment is None:
        ended_in_newline = True
        for chunk in chunks:
            total += chunk.count(b"\n")
            ended_in_newline = chunk.endswith(b"\n")
        # If the last chunk did not end in a newline, there is one more line
        # (the unterminated final line). For an empty file `ended_in_newline`
        # stays True and we correctly return 0.
        if not ended_in_newline:
            total += 1
        return total

    carry = b""
    saw_any = False
    for chunk in chunks:
        saw_any = True
        data = carry + chunk
        # rsplit keeps the last segment (which may be a partial line) as the
        # final element; everything before it is a complete line including its
        # trailing newline. Using rsplit instead of split avoids a special case
        # when data ends exactly on a newline boundary.
        *complete, carry = data.rsplit(b"\n")
        for line in complete:
            # `line` excludes the newline that terminated it, but may contain
            # a trailing \r (CRLF files). Strip handles both in one call.
            if _should_count(line, skip_blank, skip_comment):
                total += 1

    if saw_any:
        # `carry` holds whatever came after the final newline, or the whole
        # file if there were no newlines. If it is non-empty it is the last
        # line (which had no terminating newline). If it is empty, the file
        # ended exactly on a newline and there is no extra line to count.
        if carry:
            if _should_count(carry, skip_blank, skip_comment):
                total += 1
    # If the iterable produced nothing at all, we return 0 — consistent with
    # an empty file.
    return total


def _should_count(line: bytes, skip_blank: bool, skip_comment: Optional[bytes]) -> bool:
    """Return True if *line* should be counted under the skip flags.

    *line* is a bytes object that does not include the terminating newline
    but may include a trailing carriage return (CRLF). Stripping handles it.
    """
    if skip_blank:
        if line.strip(_ASCII_WHITESPACE) == b"":
            return False
    if skip_comment is not None:
        if line.lstrip(_ASCII_WHITESPACE).startswith(skip_comment):
            return False
    return True


def count_lines_path(
    path: Union[str, "os.PathLike[str]"],
    *,
    skip_blank: bool = False,
    skip_comment: Optional[bytes] = None,
    chunk_size: int = _CHUNK_SIZE,
) -> int:
    """Convenience wrapper that takes a filesystem path.

    Equivalent to ``count_lines(path, skip_blank=..., skip_comment=...,
    chunk_size=...)``. It exists because the README documents both entry
    points and some callers prefer the explicit name.
    """
    return count_lines(
        path,
        skip_blank=skip_blank,
        skip_comment=skip_comment,
        chunk_size=chunk_size,
    )
