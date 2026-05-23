function valueAt(metric, path, fallback = 0) {
  let cur = metric;
  for (const key of path) {
    if (cur == null || cur[key] == null) return fallback;
    cur = cur[key];
  }
  return cur;
}

function fmtMs(value) {
  if (!Number.isFinite(value)) return "n/a";
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  return `${value.toFixed(1)}ms`;
}

function fmtRate(value) {
  if (!Number.isFinite(value)) return "n/a";
  return `${(value * 100).toFixed(2)}%`;
}

function metricRow(data, name, label) {
  const metric = data.metrics[name];
  if (!metric) return "";
  const avg = valueAt(metric, ["values", "avg"], NaN);
  const p90 = valueAt(metric, ["values", "p(90)"], NaN);
  const p95 = valueAt(metric, ["values", "p(95)"], NaN);
  const p99 = valueAt(metric, ["values", "p(99)"], NaN);
  const max = valueAt(metric, ["values", "max"], NaN);
  return `| ${label} | ${fmtMs(avg)} | ${fmtMs(p90)} | ${fmtMs(p95)} | ${fmtMs(p99)} | ${fmtMs(max)} |`;
}

function counterValue(data, name) {
  return valueAt(data.metrics[name], ["values", "count"], 0);
}

function rateValue(data, name) {
  return valueAt(data.metrics[name], ["values", "rate"], 0);
}

export function markdownSummary(data) {
  const started = new Date().toISOString();
  const lines = [
    `# Stress Report`,
    ``,
    `Generated: ${started}`,
    ``,
    `## Run`,
    ``,
    `- Service: ${__ENV.STRESS_SERVICE || "flows"}`,
    `- URL: ${__ENV.STRESS_URL || "http://localhost:8001"}`,
    `- Profile: ${__ENV.STRESS_PROFILE || "local"}`,
    `- Scenario: ${__ENV.STRESS_SCENARIO || "a2a_async"}`,
    `- Mock LLM: ${__ENV.STRESS_USE_MOCK || "true"}`,
    ``,
    `## Health`,
    ``,
    `- Iterations: ${counterValue(data, "iterations")}`,
    `- HTTP requests: ${counterValue(data, "http_reqs")}`,
    `- HTTP failure rate: ${fmtRate(rateValue(data, "http_req_failed"))}`,
    `- A2A submit failures: ${counterValue(data, "stress_a2a_submit_failed")}`,
    `- A2A task failures: ${counterValue(data, "stress_a2a_task_failed")}`,
    `- A2A polling timeouts: ${counterValue(data, "stress_a2a_poll_timeout")}`,
    ``,
    `## Latency`,
    ``,
    `| Metric | avg | p90 | p95 | p99 | max |`,
    `| --- | ---: | ---: | ---: | ---: | ---: |`,
    metricRow(data, "http_req_duration", "HTTP request"),
    metricRow(data, "stress_a2a_submit_ms", "message/send submit"),
    metricRow(data, "stress_a2a_poll_ms", "tasks/get poll"),
    metricRow(data, "stress_a2a_task_total_ms", "submit -> terminal task"),
    ``,
  ];
  return `${lines.filter((line) => line !== "").join("\n")}\n`;
}

export function htmlSummary(data) {
  const markdown = markdownSummary(data)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Stress Report</title>
  <style>
    body { font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #172026; }
    pre { white-space: pre-wrap; background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 8px; padding: 20px; }
  </style>
</head>
<body><pre>${markdown}</pre></body>
</html>
`;
}
