---
name: diagrams-viz
description: Create and update platform visualizations (.viz) — ECharts charts/timelines and Mermaid flowcharts/sequences/gantt. Use when the user wants a diagram, chart, or process map in chat.
allowed-tools: create_viz update_viz export_viz viz_open_file
---

# Diagrams and visualizations

## Goal

Create `.viz` files that preview inline in chat and open in Documents viewer.

## Procedure

1. Choose `kind`:
   - Mermaid: `flowchart`, `sequence`, `gantt` → pass `source` (Mermaid DSL) or `engine=mermaid`
   - ECharts: `chart`, `timeline` → pass `option` (ECharts option object) or `engine=echarts`
2. Call `create_viz` with `title`, `kind`, and `source`/`option`.
3. To change an existing viz — `update_viz` with `file_id` and patched fields.
4. To export — `export_viz` (`svg` or `json`).
5. To re-open in Documents — `viz_open_file`.

## Notes

- Prefer clear titles; default filename is derived from title.
- Keep Mermaid source valid; keep ECharts `option` a JSON object.
- Read reference `diagrams-viz-reference.md` for examples.
