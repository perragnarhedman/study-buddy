from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from models import DraftItem, batch_from_dict


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return normalized.strip("-") or "draft"


def item_markdown(item: DraftItem) -> str:
    attachment_lines = []
    for attachment in item.attachments:
        target = attachment.url or attachment.file_path or "Unknown target"
        attachment_lines.append(f"- `{attachment.title}` -> {target}")
    if not attachment_lines:
        attachment_lines.append("- None captured yet")

    review_lines = [f"- {note}" for note in item.review_notes] or ["- None"]
    source_lines = [f"- `{path}`" for path in item.source_images] or ["- None"]

    payload_preview = json.dumps(item.classroom_payload_preview, indent=2) or "{}"

    return "\n".join(
        [
            f"# {item.title or item.item_id}",
            "",
            "## Source Screenshots",
            *source_lines,
            "",
            "## Inferred Details",
            f"- Item type: `{item.item_type or 'unknown'}`",
            f"- Course: `{item.course_name or item.course_id or 'Unknown'}`",
            f"- Due date: `{item.due_date or 'Unknown'}`",
            f"- Confidence: `{item.confidence}`",
            "",
            "## Description",
            item.description or "No description captured yet.",
            "",
            "## Attachments",
            *attachment_lines,
            "",
            "## Review Notes",
            *review_lines,
            "",
            "## Suggested Classroom Payload Preview",
            "```json",
            payload_preview,
            "```",
            "",
        ]
    )


def summary_markdown(batch_name: str, notes: str, source_images: list[str], items: list[DraftItem]) -> str:
    source_lines = [f"- `{path}`" for path in source_images] or ["- None"]
    item_lines = []
    for item in items:
        item_lines.extend(
            [
                f"### {item.title or item.item_id}",
                f"- Item type: `{item.item_type or 'unknown'}`",
                f"- Course: `{item.course_name or item.course_id or 'Unknown'}`",
                f"- Due date: `{item.due_date or 'Unknown'}`",
                f"- Confidence: `{item.confidence}`",
                "",
            ]
        )

    return "\n".join(
        [
            f"# Batch Summary: {batch_name}",
            "",
            "## Source Screenshots",
            *source_lines,
            "",
            "## Operator Notes",
            notes or "No notes supplied.",
            "",
            "## Extracted Items",
            *(item_lines or ["No items were generated."]),
            "## Open Questions",
            "- Review item type, course mapping, due dates, and attachments before publish.",
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render markdown review files from a draft batch JSON file."
    )
    parser.add_argument("--input", required=True, help="Input batch JSON path.")
    parser.add_argument("--output-dir", required=True, help="Output directory for markdown.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    batch = batch_from_dict(json.loads(input_path.read_text(encoding="utf-8")))

    summary_path = output_dir / "README.md"
    summary_path.write_text(
        summary_markdown(batch.batch_id, batch.notes, batch.source_images, batch.items),
        encoding="utf-8",
    )

    for item in batch.items:
        item_path = output_dir / f"{slugify(item.title or item.item_id)}.md"
        item_path.write_text(item_markdown(item), encoding="utf-8")

    print(f"Wrote markdown review files to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
