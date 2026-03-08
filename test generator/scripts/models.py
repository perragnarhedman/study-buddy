from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DraftAttachment:
    title: str
    url: str | None = None
    file_path: str | None = None
    attachment_type: str = "unknown"


@dataclass
class DraftItem:
    item_id: str
    item_type: str = "unknown"
    course_name: str | None = None
    course_id: str | None = None
    title: str = ""
    description: str | None = None
    due_date: str | None = None
    attachments: list[DraftAttachment] = field(default_factory=list)
    confidence: float = 0.0
    source_images: list[str] = field(default_factory=list)
    review_notes: list[str] = field(default_factory=list)
    classroom_payload_preview: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DraftBatch:
    batch_id: str
    created_at: str = field(default_factory=iso_now)
    notes: str = ""
    source_images: list[str] = field(default_factory=list)
    items: list[DraftItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "created_at": self.created_at,
            "notes": self.notes,
            "source_images": self.source_images,
            "items": [item.to_dict() for item in self.items],
        }


def batch_from_dict(data: dict[str, Any]) -> DraftBatch:
    items: list[DraftItem] = []
    for raw_item in data.get("items", []):
        attachments = [
            DraftAttachment(**raw_attachment)
            for raw_attachment in raw_item.get("attachments", [])
        ]
        item_data = dict(raw_item)
        item_data["attachments"] = attachments
        items.append(DraftItem(**item_data))

    return DraftBatch(
        batch_id=data["batch_id"],
        created_at=data.get("created_at", iso_now()),
        notes=data.get("notes", ""),
        source_images=list(data.get("source_images", [])),
        items=items,
    )
