# Test Generator

This folder holds the local runtime state for the separate Google Classroom test generator.

The current milestone is `markdown-first`:

- collect screenshots plus notes
- scaffold a draft JSON file
- generate reviewable markdown files
- review the output in Cursor

Live Google auth and Classroom writes stay separate and come later.

## Files

- `.env.example`: tracked template
- `.env.local`: local secrets for your machine only
- `.gitignore`: keeps secrets and generated artifacts out of git
- `scripts/`: local helper scripts for draft scaffolding, markdown output, and later auth/publish steps
- `tokens/`: generator-only OAuth tokens when auth is re-enabled
- `drafts/`: generated draft JSON and markdown review files
- `runs/`: later publish run history
- `uploads/`: later local upload staging

## What to fill in

Update `test generator/.env.local` with:

- `TEST_GENERATOR_GOOGLE_CLIENT_ID`
- `TEST_GENERATOR_GOOGLE_CLIENT_SECRET`
- `TEST_GENERATOR_TARGET_COURSE_ID`

## First local workflow

Create a draft scaffold from screenshots:

```bash
python3 "test generator/scripts/extract_drafts.py" \
  --output "test generator/drafts/sample-batch.json" \
  --notes "Virtual school sample import." \
  "serverlogs/2026-03-08-1/IMG_8891.PNG"
```

Render markdown review files:

```bash
python3 "test generator/scripts/write_markdown.py" \
  --input "test generator/drafts/sample-batch.json" \
  --output-dir "test generator/drafts/sample-batch"
```

## Notes

- This is intentionally separate from the StudyBuddy app config.
- `TEST_GENERATOR_DEFAULT_PUBLISH_STATE=DRAFT` is the safest starting mode for later live tests.
- Token, draft, run, and upload paths are local to this folder so the generator can stay isolated from app state.
- `auth_helper.py` and `publish_classroom.py` are placeholders until the separate OAuth path is stable.
