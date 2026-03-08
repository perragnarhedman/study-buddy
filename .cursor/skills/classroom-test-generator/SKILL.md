---
name: classroom-test-generator
description: Generates reviewable markdown drafts for Google Classroom test content from screenshots and short notes. Use when the user wants to recreate assignments, materials, or announcements from screenshots, produce `.md` output files, or prepare test Classroom content before live publishing is enabled.
---

# Classroom Test Generator

## Quick Start

Use this skill when the user wants screenshot-driven test content generation without touching the main app.

Default workflow:

1. Read the provided screenshots and any short notes.
2. Create or update a draft batch JSON file under `test generator/drafts/`.
3. Generate reviewable markdown files from that draft batch.
4. Ask the user to review the markdown output before any auth or publishing work.

## Rules

- Keep all runtime state under `test generator/`.
- Do not reuse the app's existing Google auth flow for writes.
- Default to markdown output first; live Google writes come later.
- Treat screenshots as imperfect inputs and mark uncertainty clearly.
- Prefer one batch JSON file plus one summary markdown file per run.

## Draft Workflow

Use this sequence:

1. Create a batch scaffold with `python3 "test generator/scripts/extract_drafts.py" ...`
2. If needed, enrich the JSON draft after reviewing screenshots.
3. Render markdown with `python3 "test generator/scripts/write_markdown.py" ...`
4. Show the generated markdown paths to the user.

## Output Expectations

The markdown output should make it easy for a non-engineer to review:

- what screenshots were used
- what the agent inferred
- what is still uncertain
- what would later be sent to Google Classroom

## Additional Resources

- Draft schema and markdown format: [reference.md](reference.md)
- Example usage: [examples.md](examples.md)
