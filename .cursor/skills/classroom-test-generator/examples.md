# Examples

## Example 1: Create Drafts From Screenshots

User request:

`Use the classroom test generator on these screenshots and create markdown drafts.`

Suggested flow:

1. Read the screenshots.
2. Run:

```bash
python3 "test generator/scripts/extract_drafts.py" \
  --output "test generator/drafts/sample-batch.json" \
  --notes "Virtual school sample import." \
  "serverlogs/2026-03-08-1/IMG_8891.PNG" \
  "serverlogs/2026-03-08-1/IMG_8892.PNG"
```

3. Run:

```bash
python3 "test generator/scripts/write_markdown.py" \
  --input "test generator/drafts/sample-batch.json" \
  --output-dir "test generator/drafts/sample-batch"
```

4. Review the generated markdown with the user.

## Example 2: Improve A Draft

If the screenshots clearly show better details than the scaffold:

1. Update the batch JSON fields for:
- `item_type`
- `course_name`
- `title`
- `description`
- `due_date`
- `attachments`

2. Re-run `write_markdown.py`.

## Example 3: Defer Publishing

If the user asks to publish before OAuth is stable:

- explain that markdown generation is available now
- keep the draft JSON and markdown as the review artifact
- do not attempt live Google writes until the separate auth flow is working
