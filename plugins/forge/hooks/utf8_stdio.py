"""The standard streams of a hook, in UTF-8.

Claude Code writes the hook event in UTF-8 and reads the hook's answer as UTF-8. Under Windows, a
Python started by `uv` takes the ANSI code page (`cp1252` on a French host) for its standard
streams, unless `PYTHONUTF8=1` is set: `É` then arrives as `Ã‰`, and a message written by the hook
leaves with bytes Claude Code cannot read. Each hook calls `use_utf8()` first, before it reads its
event.
"""

from __future__ import annotations

import io
import sys


def use_utf8() -> None:
    """Reconfigure stdin, stdout and stderr to UTF-8, keeping each stream's error handler.

    A stream that is not a text wrapper (a test's `StringIO`, a closed stream) is left as it is.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors=stream.errors)
