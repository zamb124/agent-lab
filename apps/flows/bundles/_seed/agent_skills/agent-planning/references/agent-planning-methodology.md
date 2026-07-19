# Agent planning methodology

## When to plan

Use `agent_plan_write` when the task needs **two or more** meaningful steps (search → read → answer, create → edit → verify, research → summarize).

Skip for:

- a single tool call with an immediate answer;
- a short clarification question to the user.

## Tool contract

| Tool | Args | Effect |
|---|---|---|
| `agent_plan_write` | `{ "steps": [{ "id", "title", "status" }, ...] }` | Full replace of `ExecutionState.agent_plan` |
| `agent_plan_get` | `{}` | Read current plan; errors if missing |

There is **no** patch/merge API. Every write replaces the whole checklist.

## Statuses

| Status | Meaning |
|---|---|
| `pending` | Not started |
| `in_progress` | Current focus (at most one) |
| `completed` | Done |
| `need_help` | Blocked on user/operator |
| `failed` | Tried and failed; say so in the reply |

## Good example

```json
{
  "steps": [
    { "id": "1", "title": "Find matching documents", "status": "completed" },
    { "id": "2", "title": "Read top results", "status": "in_progress" },
    { "id": "3", "title": "Summarize for the user", "status": "pending" }
  ]
}
```

## Bad examples

- Delta-only updates (`[{ "id": "2", "status": "completed" }]`) — invalid; send the full list.
- Three steps `in_progress` at once — invalid.
- Essay titles or dumping tool JSON into `title`.
- Creating a WorkItem for each micro-step — wrong domain.
- Putting the checklist only into `reason.plan` — user will not see the structured UI.

## Cadence

1. Write plan before the first heavy tool call.
2. Rewrite after each completed step (mark completed, advance `in_progress`).
3. Final rewrite with all `completed` before the closing answer.

## Help and HITL

If you need the user: set the current step to `need_help`, call `ask_user` (or HITL). After the answer, rewrite the plan and continue.
