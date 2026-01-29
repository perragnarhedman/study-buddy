# Raw Classroom Assignment Candidates (Chat) — Contract

Owner epic: `be-crg`  
Source-of-truth ticket: `be-crg.1`

## Decision (Option C: hybrid)

We will make **LLM candidates = raw Classroom assignments**, and the model will select an **assignment id**.

- **Model selection field**: `selected_assignment_id` (new)  
- **Backend response compatibility**: keep returning `best_next_action: PlanItem` by mapping the selected assignment to the best matching plan item (via `sourceAssignmentId`).
- **Why**: keeps the app experience stable (it still gets a `best_next_action`), while letting the model reason over unsplit assignments.

Notes:
- During rollout, backend may accept a legacy `selected_plan_item_id` and translate it to an assignment id via the current plan item’s `sourceAssignmentId` (best-effort), but prompts should migrate to `selected_assignment_id`.

## Candidate schema (raw assignments)

Each candidate is a single Classroom assignment (no splitting):

```json
{
  "id": "string",                // Classroom assignment id (Assignment.id)
  "title": "string",
  "courseName": "string",
  "dueDate": "string | null",    // ISO8601 or null
  "description": "string",       // truncated
  "url": "string | null",
  "estimatedMinutes": "int | null"
}
```

### Truncation / sizing rules

- `description`: include at most **1000 characters** (after trimming).
- Attachments: the Classroom fetcher currently appends an `Attachments:` block into `description`. That is acceptable; we are not introducing a separate attachments field in this epic.

## Threading / continuation (“ok/ja”)

When the student replies with a short acknowledgment (e.g., `"ok"`, `"ja"`), treat it as **continue the current thread**:

- Persist **last_selected_assignment_id** in user state.
- On ack, restrict candidates to that assignment (if still present); otherwise fall back to the normal candidate selection set.

## Overview vs selection behavior

- If the user asks for an overview (e.g., “what else do I have / what subjects?”):
  - Provide overview in `assistant_text`
  - Set `selected_assignment_id = null`
- If the user expresses a clear preference (e.g., “English today”):
  - Select the closest matching candidate assignment
  - Set `selected_assignment_id` to that assignment’s id

## Mapping selection → `best_next_action` (PlanItem)

Given `selected_assignment_id`, choose `best_next_action` by mapping through the current plan:

- Find the first plan item where:
  - `PlanItem.sourceAssignmentId == selected_assignment_id`, and
  - `PlanItem.status != "done"`
- If none exist, return `best_next_action = null` (assistant can still guide via text).

## Done marking

We keep done-state persistence tied to assignments:

- If the user says they finished something, the model may specify `mark_done_assignment_id`.
- Backend persists done via `assignment_status` keyed by `source_assignment_id` (which is assignment id).

## Worked examples (expected decision fields)

- Greeting: “Hej”
  - `selected_assignment_id = null`
- Overview: “Vad har jag kvar?”
  - `selected_assignment_id = null`
- Preference: “Jag vill göra engelska idag.”
  - `selected_assignment_id = <matching assignment id>`
- Ack continuation: “Ok”
  - `selected_assignment_id = last_selected_assignment_id` (if any)


