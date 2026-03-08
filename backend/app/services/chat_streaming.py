from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import uuid4


_SHORT_OPENER_RE = re.compile(r"^\s*([^\n]{1,40}?[.!?])(?:\s+)(?=[A-ZÅÄÖ])")


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
    active_message_id: str | None = None
    waiting_for_first_boundary: bool = True

    def feed(self, text: str) -> list[dict]:
        self.pending_text += text
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
                    self._emit_text(opener, events)
                    self._complete_message(events)
                    self.pending_text = rest
                    self.waiting_for_first_boundary = False
                    continue

                paragraph_split = self._consume_paragraph_boundary()
                if paragraph_split is not None:
                    segment, rest = paragraph_split
                    self._emit_text(segment, events)
                    self._complete_message(events)
                    self.pending_text = rest
                    self.waiting_for_first_boundary = False
                    continue

                if final or len(self.pending_text) >= 60:
                    self.waiting_for_first_boundary = False
                    if self.pending_text:
                        self._emit_text(self.pending_text, events)
                        self.pending_text = ""
                    if final:
                        self._complete_message(events)
                    break

                break

            paragraph_split = self._consume_paragraph_boundary()
            if paragraph_split is not None:
                segment, rest = paragraph_split
                self._emit_text(segment, events)
                self._complete_message(events)
                self.pending_text = rest
                continue

            if self.pending_text:
                self._emit_text(self.pending_text, events)
                self.pending_text = ""

            if final:
                self._complete_message(events)
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
        return opener, rest

    def _consume_paragraph_boundary(self) -> tuple[str, str] | None:
        idx = self.pending_text.find("\n\n")
        if idx == -1:
            return None
        segment = self.pending_text[:idx].strip()
        rest = self.pending_text[idx + 2 :].lstrip("\n")
        return segment, rest

    def _emit_text(self, text: str, events: list[dict]) -> None:
        if not text:
            return
        if self.active_message_id is None:
            self.active_message_id = str(uuid4())
            events.append({"type": "message_started", "message_id": self.active_message_id})
        events.append(
            {
                "type": "message_delta",
                "message_id": self.active_message_id,
                "delta": text,
            }
        )

    def _complete_message(self, events: list[dict]) -> None:
        if self.active_message_id is None:
            return
        events.append({"type": "message_completed", "message_id": self.active_message_id})
        self.active_message_id = None
