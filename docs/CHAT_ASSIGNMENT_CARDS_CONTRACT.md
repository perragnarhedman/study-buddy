## Chat assignment cards — API contract (be-27q)

**Status: DEPRECATED.** Assignment cards were removed in the chat-only refactor (iOS no longer renders cards, and the backend no longer returns `assignment_cards` from `POST /chat/send`). This document is kept for historical context.

When the student asked for an overview (for example “what assignments do I have this week?”), the backend used to return **assignment cards** along with the normal assistant text. The iOS app used to render these cards inline in the chat conversation.

### Where it appears

- Endpoint: `POST /chat/send`
- Field: `assignment_cards` (optional, removed)

### JSON shape

`assignment_cards` is an array of objects:

- `id` (string): stable id for UI list rendering (usually `sourceAssignmentId`)
- `title` (string): display title (typically the plan item title)
- `courseName` (string|null): subject/course label
- `dueDate` (string|null): ISO8601 date or datetime (display-only in iOS)
- `estimatedMinutes` (int|null)
- `status` ("todo" | "doing" | "done")
- `sourceAssignmentId` (string|null): the source assignment id used for persistence
- `url` (string|null): optional primary link
- `attachments` (array|null): optional list of `{ "title": string, "url": string }`

### Status updates

To persist a status change triggered by tapping a card (removed):

- Endpoint: `POST /assignment/status` (removed)
- Body:
  - `sourceAssignmentId` (string)
  - `status` ("todo" | "doing" | "done")


