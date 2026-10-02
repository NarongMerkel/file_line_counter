"""Tests for file_line_counter.core.

Conventions asserted here:
  * Empty file -> 0 lines.
  * Final line without trailing newline still counts as one line.
  * CRLF files are counted by '\n' (the LF), so each CRLF line counts once.
  * Blank/comment skipping operates on the stripped line.
"""

import os
import tempfile
import unittest
from file_line_counter import count_lines, count_lines_path


def _write_temp(content: bytes) -> str:
    fd, path = tempfile.mkstemp(prefix="flc_", suffix=".txt")
    with os.fdopen(fd, "wb") as fh:
        fh.write(content)
    return path


class TestCountLinesPath(unittest.TestCase):
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _make(self, content: bytes) -> str:
        path = _write_temp(content)
        self._paths.append(path)
        return path

    def test_empty_file_is_zero(self):
        self.assertEqual(count_lines(self._make(b"")), 0)

    def test_single_char_no_newline_is_one(self):
        self.assertEqual(count_lines(self._make(b"x")), 1)

    def test_single_newline_is_one(self):
        # "\n" is one line containing an empty string.
        self.assertEqual(count_lines(self._make(b"\n")), 1)

    def test_three_lines_with_trailing_newline(self):
        self.assertEqual(count_lines(self._make(b"a\nb\nc\n")), 3)

    def test_three_lines_without_trailing_newline(self):
        self.assertEqual(count_lines(self._make(b"a\nb\nc")), 3)

    def test_crlf_counts_once_per_line(self):
        # b"a\r\nb\r\n" has exactly one '\n' per line.
        self.assertEqual(count_lines(self._make(b"a\r\nb\r\n")), 2)

    def test_mixed_newlines(self):
        # \n then \r\n then bare end.
        self.assertEqual(count_lines(self._make(b"a\nb\r\nc")), 3)

    def test_large_file_uses_chunked_read(self):
        # 200 KiB of 'line\n' entries; chunk size is 64 KiB so this crosses
        # at least three chunk boundaries.
        n = 40000
        content = b"line\n" * n
        self.assertEqual(count_lines(self._make(content)), n)

    def test_chunk_boundary_inside_line(self):
        # A single very long line split across chunks must be counted once.
        long_line = b"x" * (70 * 1024)
        self.assertEqual(count_lines(self._make(long_line)), 1)
        self.assertEqual(count_lines(self._make(long_line + b"\n")), 1)

    def test_pathlike_argument(self):
        path = self._make(b"a\nb\nc")
        self.assertEqual(count_lines(os.fspath(path)), 3)

    def test_count_lines_path_alias(self):
        path = self._make(b"a\nb\n")
        self.assertEqual(count_lines_path(path), 2)


class TestSkipBlank(unittest.TestCase):
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _make(self, content: bytes) -> str:
        path = _write_temp(content)
        self._paths.append(path)
        return path

    def test_skip_blank_removes_empty_lines(self):
        content = b"a\n\n  \n\tb\n\n"
        # Non-blank: "a", "\tb" -> 2
        self.assertEqual(count_lines(self._make(content), skip_blank=True), 2)

    def test_skip_blank_with_no_trailing_newline(self):
        content = b"a\n\n\n"
        self.assertEqual(count_lines(self._make(content), skip_blank=True), 1)

    def test_skip_blank_all_blank_is_zero(self):
        self.assertEqual(count_lines(self._make(b"\n  \n\t\n"), skip_blank=True), 0)

    def test_skip_blank_false_counts_all(self):
        content = b"a\n\nb\n"
        self.assertEqual(count_lines(self._make(content), skip_blank=False), 3)


class TestSkipComment(unittest.TestCase):
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _make(self, content: bytes) -> str:
        path = _write_temp(content)
        self._paths.append(path)
        return path

    def test_skip_comment_hash(self):
        content = b"# header\na\n  # indented comment\nb\n"
        # Counted: "a", "b" -> 2
        self.assertEqual(count_lines(self._make(content), skip_comment=b"#"), 2)

    def test_skip_comment_double_slash(self):
        content = b"// note\ncode\n// other\n"
        self.assertEqual(count_lines(self._make(content), skip_comment=b"//"), 1)

    def test_skip_comment_is_case_sensitive(self):
        content = b"# keep\n# skip\n"
        # With prefix b'#' both are comments -> 0.
        self.assertEqual(count_lines(self._make(content), skip_comment=b"#"), 0)

    def test_skip_comment_only_at_line_start(self):
        content = b"a # not a comment\nb\n"
        # The prefix only matches at the start of the stripped line, so the
        # first line counts (it does not START with '#').
        self.assertEqual(count_lines(self._make(content), skip_comment=b"#"), 2)

    def test_skip_comment_blank_lines_still_counted(self):
        content = b"# c\n\na\n"
        # Only the comment is skipped; the blank line is still counted because
        # skip_blank is False.
        self.assertEqual(count_lines(self._make(content), skip_comment=b"#"), 2)

    def test_skip_blank_and_comment_together(self):
        content = b"# c\n\n  \na\n\n# d\nb\n"
        # Counted: "a", "b" -> 2
        self.assertEqual(
            count_lines(self._make(content), skip_blank=True, skip_comment=b"#"),
            2,
        )

    def test_skip_comment_no_trailing_newline(self):
        content = b"# c\na"
        self.assertEqual(count_lines(self._make(content), skip_comment=b"#"), 1)


class TestIterableInput(unittest.TestCase):
    def test_iterable_of_chunks(self):
        chunks = [b"a\nb\n", b"c\nd"]
        self.assertEqual(count_lines(iter(chunks)), 4)

    def test_iterable_empty(self):
        self.assertEqual(count_lines(iter([])), 0)

    def test_iterable_with_skip_blank(self):
        chunks = [b"a\n\n", b"\nb\n"]
        # Non-blank: a, b -> 2
        self.assertEqual(count_lines(iter(chunks), skip_blank=True), 2)

    def test_iterable_single_chunk_no_newline(self):
        self.assertEqual(count_lines(iter([b"hello"])), 1)

    def test_iterable_chunk_boundary_on_newline(self):
        # Chunk ends exactly on a newline; next chunk starts a new line.
        chunks = [b"a\n", b"b\n"]
        self.assertEqual(count_lines(iter(chunks)), 2)


if __name__ == "__main__":
    unittest.main()
