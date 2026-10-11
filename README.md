# file_line_counter

Count lines in a file without loading it fully into memory, optionally skipping blank or comment lines. Standard library only — zero dependencies.

## Usage

```python
from file_line_counter import count_lines, count_lines_path

# Count lines in an in-memory bytes stream:
total = count_lines(iter([b"a\n", b"b\n"]))

# Or feed any iterable of bytes chunks (pipe, socket, in-memory stream):
total = count_lines(iter([b"a\n", b"b\n"]))

code = count_lines(iter([b"# hi\n", b"a = 1\n"]), skip_blank=True, skip_comment=b"#")

# Same thing with the explicit path helper:
import tempfile, os
fd, path = tempfile.mkstemp(suffix=".py")
with os.fdopen(fd, "wb") as fh:
    fh.write(b"# hi\na = 1\n")
code = count_lines_path(path, skip_blank=True, skip_comment=b"#")
os.remove(path)
```

## Why this exists

`len(open(f).readlines())` loads the entire file into a list of `str` objects. For multi-gigabyte logs that is a lot of memory and a lot of UTF-8 decoding overhead, and it raises `UnicodeDecodeError` on files that are not valid UTF-8. This library reads raw bytes in fixed-size chunks and counts `b"\n"` occurrences, so peak memory is bounded by the chunk size (64 KiB by default) and decoding is never attempted.

The trade-off: because we never decode, blank and comment detection operate on byte literals. Pass `skip_comment=b"#"`, not `"#"`.

## Edge cases you will hit

- A file with no trailing newline still counts its final line. `b"a\nb\nc"` is 3 lines, matching `wc -l` on a file that lacks the final newline. An completely empty file is 0 lines.
- CRLF files are counted by the `\n` byte, so `b"a\r\nb\r\n"` is 2 lines, not 4.
- Comment matching is a case-sensitive `startswith` on the line after stripping leading ASCII whitespace. `b"#"` matches `# hi` and `   # hi`, but a line like `x = 1 # note` is **not** skipped — the `#` is not at the start.
- Blank detection strips ASCII whitespace (` \t\r\n\v\f`). Non-ASCII whitespace (e.g. U+00A0) is not treated as blank.
- `skip_comment` and `skip_blank` are independent. To drop both, pass both.

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

