# Test Generator Config

This folder holds local configuration for the separate Google Classroom test generator.

## Files

- `.env.example`: tracked template
- `.env.local`: local secrets for your machine only
- `.gitignore`: keeps secrets and generated artifacts out of git

## What to fill in

Update `test generator/.env.local` with:

- `TEST_GENERATOR_GOOGLE_CLIENT_ID`
- `TEST_GENERATOR_GOOGLE_CLIENT_SECRET`
- `TEST_GENERATOR_TARGET_COURSE_ID`

## Notes

- This is intentionally separate from the StudyBuddy app config.
- `TEST_GENERATOR_DEFAULT_PUBLISH_STATE=DRAFT` is the safest starting mode for initial tests.
- Token, draft, run, and upload paths are local to this folder so the generator can stay isolated from app state.
