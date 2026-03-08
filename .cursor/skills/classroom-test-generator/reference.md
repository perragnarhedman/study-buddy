# Reference

## Scope

This skill supports the markdown-first milestone of the Classroom test generator.

It does:
- collect screenshot paths and notes
- create structured draft JSON
- generate reviewable markdown files

It does not yet:
- complete Google OAuth
- publish to Google Classroom
- upload attachments to Drive

## Draft JSON Shape

Batch file structure:

```json
{
  "batch_id": "2026-03-08-sample",
  "created_at": "2026-03-08T22:00:00Z",
  "notes": "Short operator notes.",
  "source_images": ["serverlogs/2026-03-08-1/IMG_8891.PNG"],
  "items": [
    {
      "item_id": "img-8891",
      "item_type": "unknown",
      "course_name": null,
      "course_id": null,
      "title": "Needs review: IMG_8891",
      "description": "Generated from screenshot and notes.",
      "due_date": null,
      "attachments": [],
      "confidence": 0.1,
      "source_images": ["serverlogs/2026-03-08-1/IMG_8891.PNG"],
      "review_notes": [
        "Generated as a scaffold only.",
        "Review title, type, due date, and attachment details."
      ],
      "classroom_payload_preview": {}
    }
  ]
}
```

## Item Type Guidance

Use these values:

- `assignment`
- `material`
- `announcement`
- `unknown`

Use `unknown` when the screenshot is not clear enough.

## Markdown Output Format

Generate:

- one batch summary markdown file
- optionally one per-item markdown file when there are multiple extracted items

Recommended sections:

```markdown
# Batch Summary

## Source Screenshots
- ...

## Operator Notes
...

## Extracted Items
### Item 1
- Item type:
- Course:
- Title:
- Due date:
- Confidence:

## Open Questions
- ...
```

Per-item markdown should include:

- source screenshots
- inferred course
- inferred item type
- title
- description
- due date
- attachments
- confidence
- review notes
- suggested Classroom payload preview

## Review Rules

- Never present uncertain details as facts.
- Prefer `Unknown` over guessing.
- Call out missing due dates and attachments explicitly.
- Make markdown easy to scan for a product or ops user.
