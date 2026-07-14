# diagrams-viz — call examples

## Mermaid flowchart

```json
{
  "title": "Onboarding",
  "kind": "flowchart",
  "source": "flowchart TD\n  A[Start] --> B[Form]\n  B --> C[Done]"
}
```

## ECharts bar chart

```json
{
  "title": "Sales",
  "kind": "chart",
  "option": {
    "xAxis": { "type": "category", "data": ["Mon", "Tue", "Wed"] },
    "yAxis": { "type": "value" },
    "series": [{ "type": "bar", "data": [12, 20, 15] }]
  }
}
```
