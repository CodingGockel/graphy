"""Separates `<think>…</think>` reasoning from LLM output: incrementally for a stream
(`ThinkSplitter`) and over a complete text (`split_think`)."""
import re
from typing import Literal

Kind = Literal["thinking", "answer"]

OPEN = "<think>"
CLOSE = "</think>"


def _held_back(text: str, tag: str) -> int:
    """Length of the end of `text` that could be the beginning of `tag`."""
    for length in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:length]):
            return length
    return 0


class ThinkSplitter:
    """Routes the deltas of a stream to `thinking` or `answer`.

    Tracks whether it is inside a `<think>` block and holds back an incomplete tag at
    the end of a delta (`<thi` | `nk>`) until the next one decides what it is.

    Text before a lone `</think>` (a chat template that puts the opening tag into the
    prompt) is not handled: it has gone out as `answer` when the tag arrives and cannot
    be taken back. `split_think` fixes that up on the complete text.
    """

    def __init__(self) -> None:
        self._inside = False
        self._held = ""

    def feed(self, delta: str) -> list[tuple[Kind, str]]:
        text = self._held + delta
        self._held = ""
        parts: list[tuple[Kind, str]] = []
        while text:
            kind: Kind = "thinking" if self._inside else "answer"
            tag = CLOSE if self._inside else OPEN
            index = text.find(tag)
            if index == -1:
                held = _held_back(text, tag)
                if held < len(text):
                    parts.append((kind, text[: len(text) - held]))
                self._held = text[len(text) - held:] if held else ""
                break
            if index:
                parts.append((kind, text[:index]))
            text = text[index + len(tag):]
            self._inside = not self._inside
        return parts

    def flush(self) -> list[tuple[Kind, str]]:
        """Release text that was held back as a possible tag; call at the end of the stream."""
        held, self._held = self._held, ""
        if not held:
            return []
        return [("thinking" if self._inside else "answer", held)]


def split_think(text: str) -> tuple[str | None, str]:
    """`(thinking, answer)` of a complete LLM output; thinking is None if there is none.

    Same rules as the frontend's `lib/thinking.ts`: several blocks, an unclosed block
    (truncated output) and text before a lone `</think>` all count as reasoning.
    """
    parts: list[str] = []
    rest = text

    close = rest.find(CLOSE)
    open_ = rest.find(OPEN)
    if close != -1 and (open_ == -1 or open_ > close):
        parts.append(rest[:close])
        rest = rest[close + len(CLOSE):]

    def take(match: re.Match[str]) -> str:
        parts.append(match.group(1))
        return ""

    rest = re.sub(r"<think>(.*?)(?:</think>|\Z)", take, rest, flags=re.DOTALL)

    thinking = "\n\n".join(part.strip() for part in parts if part.strip())
    return thinking or None, rest.strip()
