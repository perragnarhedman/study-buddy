from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from models import DraftBatch, DraftItem


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return normalized.strip("-") or "draft"


def build_item(image_path: str, notes: str, course_name: str | None, index: int) -> DraftItem:
    stem = Path(image_path).stem
    return DraftItem(
        item_id=f"{slugify(stem)}-{index}",
        item_type="unknown",
        course_name=course_name,
        title=f"Needs review: {stem}",
        description=notes or "Generated from screenshot and notes.",
        confidence=0.1,
        source_images=[image_path],
        review_notes=[
            "Generated as a scaffold only.",
            "Review title, type, due date, and attachment details.",
        ],
        classroom_payload_preview={
            "state": "DRAFT",
            "notes": "Preview only. Live publish not enabled in markdown-first mode.",
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a draft JSON scaffold from screenshot paths and notes."
    )
    parser.add_argument("images", nargs="+", help="Screenshot file paths.")
    parser.add_argument("--output", required=True, help="Output batch JSON path.")
    parser.add_argument("--notes", default="", help="Short operator notes.")
    parser.add_argument("--batch-id", default="", help="Optional explicit batch ID.")
    parser.add_argument("--course-name", default="", help="Optional course name hint.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    batch_id = args.batch_id or output_path.stem
    course_name = args.course_name or None
    items = [
        build_item(image_path=image, notes=args.notes, course_name=course_name, index=index)
        for index, image in enumerate(args.images, start=1)
    ]
    batch = DraftBatch(
        batch_id=batch_id,
        notes=args.notes,
        source_images=args.images,
        items=items,
    )

    output_path.write_text(json.dumps(batch.to_dict(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote draft batch: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
