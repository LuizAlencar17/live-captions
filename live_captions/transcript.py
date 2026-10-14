from __future__ import annotations

from dataclasses import dataclass, field

SOURCE_LABELS = {"computer": "Computer", "microphone": "Mic"}


@dataclass(slots=True)
class Segment:
    source: str
    text: str


@dataclass(slots=True)
class Turn:
    """Consecutive text coming from the same source."""

    source: str
    final: str = ""
    interim: str = ""


@dataclass(slots=True)
class TranscriptBuffer:
    """Store final segments (tagged by source) and one interim hypothesis per source."""

    segments: list[Segment] = field(default_factory=list)
    interim_by_source: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.split())

    def apply(self, text: str, is_final: bool, source: str = "computer") -> None:
        normalized = self._normalize(text)
        if not normalized:
            if is_final:
                self.interim_by_source.pop(source, None)
            return

        if is_final:
            self.segments.append(Segment(source, normalized))
            self.interim_by_source.pop(source, None)
        else:
            self.interim_by_source[source] = normalized

    def turns(self) -> list[Turn]:
        """Group consecutive same-source segments; pending interim text goes last."""
        turns: list[Turn] = []
        for seg in self.segments:
            if turns and turns[-1].source == seg.source:
                turns[-1].final = f"{turns[-1].final} {seg.text}"
            else:
                turns.append(Turn(seg.source, seg.text))
        for source, text in self.interim_by_source.items():
            if not text:
                continue
            if turns and turns[-1].source == source:
                turns[-1].interim = text
            else:
                turns.append(Turn(source, "", text))
        return turns

    @property
    def final_text(self) -> str:
        return " ".join(seg.text for seg in self.segments)

    @property
    def text(self) -> str:
        """Plain text for copying, one labelled line per turn."""
        lines = []
        for turn in self.turns():
            body = " ".join(part for part in (turn.final, turn.interim) if part)
            label = SOURCE_LABELS.get(turn.source, turn.source)
            lines.append(f"[{label}] {body}")
        return "\n".join(lines)

    def clear(self) -> None:
        self.segments.clear()
        self.interim_by_source.clear()
