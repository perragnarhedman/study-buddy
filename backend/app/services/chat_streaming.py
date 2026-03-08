from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import uuid4


_SHORT_OPENER_RE = re.compile(r"^\s*([^\n]{1,60}?[.!?])(?:\s+)(?=\S)")
_PARAGRAPH_BREAK_RE = re.compile(r"\n[ \t]*\n+")
_WEAK_FRAGMENT_RE = re.compile(r'^[\s\)\]\}"\'»”’.,:;!?…-]{1,6}$')
_SUBJECT_BULLET_BOUNDARY_RE = re.compile(
    r"\n(?=[•*-]\s*(?:Math|History|English|Matte|Historia|Engelska)\s*:)",
    re.IGNORECASE,
)


@dataclass
class AssistantTextJSONStreamParser:
    """
    Extract decoded characters for the `assistant_text` JSON string while the
    full JSON object is still streaming in as plain text.
    """

    _key_token: str = field(default='"assistant_text"', init=False)
    _match_index: int = 0
    _state: str = "search_key"
    _escaped: bool = False
    _unicode_digits: str = ""

    def feed(self, chunk: str) -> str:
        out: list[str] = []
        for ch in chunk:
            if self._state == "search_key":
                expected = self._key_token[self._match_index]
                if ch == expected:
                    self._match_index += 1
                    if self._match_index == len(self._key_token):
                        self._match_index = 0
                        self._state = "after_key"
                else:
                    self._match_index = 1 if ch == self._key_token[0] else 0
                continue

            if self._state == "after_key":
                if ch.isspace():
                    continue
                if ch == ":":
                    self._state = "before_value"
                else:
                    self._state = "search_key"
                    self._match_index = 1 if ch == self._key_token[0] else 0
                continue

            if self._state == "before_value":
                if ch.isspace():
                    continue
                if ch == '"':
                    self._state = "in_string"
                else:
                    self._state = "done"
                continue

            if self._state == "in_unicode":
                self._unicode_digits += ch
                if len(self._unicode_digits) == 4:
                    try:
                        out.append(chr(int(self._unicode_digits, 16)))
                    except ValueError:
                        pass
                    self._unicode_digits = ""
                    self._state = "in_string"
                    self._escaped = False
                continue

            if self._state == "in_string":
                if self._escaped:
                    self._escaped = False
                    if ch == "n":
                        out.append("\n")
                    elif ch == "r":
                        out.append("\r")
                    elif ch == "t":
                        out.append("\t")
                    elif ch == "b":
                        out.append("\b")
                    elif ch == "f":
                        out.append("\f")
                    elif ch == "u":
                        self._state = "in_unicode"
                        self._unicode_digits = ""
                    else:
                        out.append(ch)
                    continue

                if ch == "\\":
                    self._escaped = True
                    continue
                if ch == '"':
                    self._state = "done"
                    continue
                out.append(ch)
                continue

            if self._state == "done":
                continue

        return "".join(out)


@dataclass
class BubbleStreamFormatter:
    """
    Convert streamed assistant text into chat bubble events.

    We keep the first bubble buffered briefly so short openers like "Hi!" can
    become their own bubble before the main answer starts.
    """

    pending_text: str = ""
    waiting_for_first_boundary: bool = True

    def feed(self, text: str) -> list[dict]:
        self.pending_text += text.replace("\r\n", "\n").replace("\r", "\n")
        return self._drain(final=False)

    def finish(self) -> list[dict]:
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[dict]:
        events: list[dict] = []

        while True:
            if self.waiting_for_first_boundary:
                opener_split = self._consume_short_opener()
                if opener_split is not None:
                    opener, rest = opener_split
                    self._emit_message(opener, events)
                    self.pending_text = rest
                    self.waiting_for_first_boundary = False
                    continue

                segment_split = self._consume_message_boundary()
                if segment_split is not None:
                    segment, rest = segment_split
                    if not segment:
                        self.pending_text = rest
                        continue
                    self._emit_message(segment, events)
                    self.pending_text = rest
                    self.waiting_for_first_boundary = False
                    continue

                if final:
                    final_text = self.pending_text.strip()
                    if final_text:
                        self._emit_message(final_text, events)
                    self.pending_text = ""
                    self.waiting_for_first_boundary = False
                    break

                if self.pending_text.endswith("\n"):
                    break

                if len(self.pending_text.strip()) < 80:
                    break

                buffered = self.pending_text.strip()
                if buffered:
                    self._emit_message(buffered, events)
                self.pending_text = ""
                self.waiting_for_first_boundary = False
                break

            segment_split = self._consume_message_boundary()
            if segment_split is not None:
                segment, rest = segment_split
                if not segment:
                    self.pending_text = rest
                    continue
                self._emit_message(segment, events)
                self.pending_text = rest
                continue

            if final:
                final_text = self.pending_text.strip()
                if final_text:
                    self._emit_message(final_text, events)
                self.pending_text = ""
            break

        return events

    def _consume_short_opener(self) -> tuple[str, str] | None:
        match = _SHORT_OPENER_RE.match(self.pending_text)
        if not match:
            return None
        opener = match.group(1).strip()
        rest = self.pending_text[match.end() :].lstrip()
        if not opener:
            return None
        leading_fragment, _remaining = self._split_leading_paragraph(rest)
        if self._is_weak_fragment(leading_fragment):
            return None
        return opener, rest

    def _consume_paragraph_boundary(self) -> tuple[str, str] | None:
        match = _PARAGRAPH_BREAK_RE.search(self.pending_text)
        if match is None:
            return None
        if match.end() >= len(self.pending_text):
            return None
        segment = self.pending_text[: match.start()].strip()
        rest = self.pending_text[match.end() :].lstrip("\n")
        segment, rest = self._merge_weak_leading_fragment(segment, rest)
        return segment, rest

    def _consume_subject_bullet_boundary(self) -> tuple[str, str] | None:
        match = _SUBJECT_BULLET_BOUNDARY_RE.search(self.pending_text, 1)
        if match is None:
            return None
        segment = self.pending_text[: match.start()].strip()
        rest = self.pending_text[match.start() + 1 :].lstrip("\n")
        return segment, rest

    def _consume_message_boundary(self) -> tuple[str, str] | None:
        paragraph_split = self._consume_paragraph_boundary()
        bullet_split = self._consume_subject_bullet_boundary()

        if paragraph_split is None:
            return bullet_split
        if bullet_split is None:
            return paragraph_split

        paragraph_len = len(paragraph_split[0])
        bullet_len = len(bullet_split[0])
        return paragraph_split if paragraph_len <= bullet_len else bullet_split

    def _merge_weak_leading_fragment(self, segment: str, rest: str) -> tuple[str, str]:
        fragment, remaining = self._split_leading_paragraph(rest)
        if not self._is_weak_fragment(fragment):
            return segment, rest
        merged = f"{segment}{fragment}".strip() if segment else fragment
        return merged, remaining

    def _split_leading_paragraph(self, text: str) -> tuple[str, str]:
        trimmed = text.lstrip("\n")
        if not trimmed:
            return "", ""
        match = _PARAGRAPH_BREAK_RE.search(trimmed)
        if match is None:
            return trimmed.strip(), ""
        fragment = trimmed[: match.start()].strip()
        remaining = trimmed[match.end() :].lstrip("\n")
        return fragment, remaining

    def _is_weak_fragment(self, text: str) -> bool:
        trimmed = text.strip()
        if not trimmed:
            return False
        return _WEAK_FRAGMENT_RE.fullmatch(trimmed) is not None

    def _emit_message(self, text: str, events: list[dict]) -> None:
        if not text:
            return
        message_id = str(uuid4())
        events.append({"type": "message_started", "message_id": message_id})
        events.append({"type": "message_delta", "message_id": message_id, "delta": text})
        events.append({"type": "message_completed", "message_id": message_id})
