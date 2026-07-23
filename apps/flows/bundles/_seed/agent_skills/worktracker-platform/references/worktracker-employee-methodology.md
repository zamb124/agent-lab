# Worktracker employee methodology

## Wake-up

When the flow runs because of `worktracker/work_item/assigned`, prefer:

1. `work_item_get` if `work_item_id` is already in run context.
2. Else `work_item_list_mine` → pick the item → `work_item_get`.
3. Do the work; optionally `work_item_add_comment`; then `work_item_complete` or `work_item_cancel` / reassign.

## Scenario matrix

| Intent | Chain |
|---|---|
| What is on me? | `work_item_list_mine` → optional `work_item_get` |
| Inbox counters | `work_item_mine_summary` |
| Create for self | `work_item_create(assignee_type=self)` |
| Assign to named person | `team_resolve_user` → (1 match) create/assign; else `ask_user` |
| Assign to queue | `work_queue_list` / `get_by_slug` → create/assign queue |
| Claim unclaimed | `work_item_mine_summary` → `work_item_list` with `queue_unclaimed_only` + `work_queue_ids` → `work_item_claim` |
| Move on board | `work_board_get` → `work_item_move` |
| Activity note | `work_item_add_comment` (not HITL) |
| Done / failed | `work_item_complete(terminal_state=done\|failed)` |
| Cancel | `work_item_cancel` |

## Two «members»

| Meaning | Tools |
|---|---|
| Company roster | `team_list_members` / `team_resolve_user` |
| Queue claim ACL | `work_queue_list_members` / add / remove |

## Boundaries

- HITL customer dialog is not an employee Worktracker tool.
- Never invent ids; Zero-Guess on ambiguous team resolve.
- Schedules live on shared `work-tracking`; AgentPlan checklist is `agent-planning`, not WorkItem.
