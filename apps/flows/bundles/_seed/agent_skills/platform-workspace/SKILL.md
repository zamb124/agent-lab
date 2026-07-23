---
name: platform-workspace
description: Shared platform capabilities — documents, diagrams, browser research, WorkItems, schedules, Google Sheets, and execution planning. Load for cross-service deliverables and research.
depends_on: document-workspace diagrams-viz web-research work-tracking agent-planning google-sheets team-directory
---

# Platform workspace

## Goal

Unlock cross-cutting platform capabilities that are not CRM- or Flows-specific.

## Procedure

1. Files / Office — load `document-workspace` (then `docx-templates` if needed).
2. Charts / Mermaid / ECharts `.viz` — load `diagrams-viz`.
3. Web/index search, batch discovery and bounded page snapshots — load `web-research`.
4. WorkItems and one-time/cron/interval schedules — load `work-tracking`.
5. Company roster / resolve person by name — load `team-directory`.
6. Multi-step execution checklist — load `agent-planning` (`agent_plan_write` / `agent_plan_get`).
7. Google Sheets (spreadsheet_id + A1) — load `google-sheets`.

## Notes

These children also appear under other domains when relevant; loading here is the direct path from any Lara entry.
