import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend } from "k6/metrics";
import exec from "k6/execution";
import { htmlSummary, markdownSummary } from "../lib/report.js";

const submitMs = new Trend("stress_a2a_submit_ms", true);
const pollMs = new Trend("stress_a2a_poll_ms", true);
const taskTotalMs = new Trend("stress_a2a_task_total_ms", true);
const submitFailed = new Counter("stress_a2a_submit_failed");
const taskFailed = new Counter("stress_a2a_task_failed");
const pollTimeout = new Counter("stress_a2a_poll_timeout");

const BASE_URL = (__ENV.STRESS_URL || "http://localhost:8001").replace(/\/+$/, "");
const TOKEN = __ENV.TOKEN || __ENV.STRESS_TOKEN || "";
const USE_MOCK = (__ENV.STRESS_USE_MOCK || "true").toLowerCase() !== "false";
const MAX_POLLS = Number.parseInt(__ENV.STRESS_MAX_POLLS || "120", 10);
const POLL_SLEEP_S = Number.parseFloat(__ENV.STRESS_POLL_SLEEP || "0.5");
const PROFILE = __ENV.STRESS_PROFILE || "local";
const RATE = Number.parseInt(__ENV.STRESS_RATE || "5", 10);
const DURATION = __ENV.STRESS_DURATION || "2m";
const PRE_ALLOCATED_VUS = Number.parseInt(__ENV.STRESS_PRE_ALLOCATED_VUS || "20", 10);
const MAX_VUS = Number.parseInt(__ENV.STRESS_MAX_VUS || "100", 10);

export const options = {
  scenarios: {
    a2a_async: {
      executor: "constant-arrival-rate",
      rate: RATE,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: PRE_ALLOCATED_VUS,
      maxVUs: MAX_VUS,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    stress_a2a_submit_failed: ["count==0"],
    stress_a2a_task_failed: ["count==0"],
    stress_a2a_poll_timeout: ["count==0"],
    stress_a2a_submit_ms: ["p(95)<1000"],
    stress_a2a_poll_ms: ["p(95)<1000"],
    stress_a2a_task_total_ms: ["p(95)<30000"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
  tags: {
    service: "flows",
    profile: PROFILE,
  },
};

// Mock задаётся per-node (по node_id графа), потому что в одном run могут
// исполняться разные llm-ноды и каждой нужны свои ответы. Значение для любой
// сущности — список (FIFO), даже если ответ один. Code-ноды (classifier,
// formatter, greeting_node) не мокаются — исполняются реально, они дёшевы.
const CASES = [
  {
    flowId: "example_graph",
    branch: "default",
    text: "привет, проверь графовый маршрут",
    mock: {},
    expectedStates: ["completed"],
  },
  {
    flowId: "example_graph",
    branch: "fast_track",
    text: "заказ 1042: нужен статус",
    mock: {
      nodes: {
        order_processor: [{ type: "text", content: "Заказ 1042 принят в обработку" }],
      },
    },
    expectedStates: ["completed"],
  },
  {
    flowId: "example_graph",
    branch: "orders_only",
    text: "жалоба на доставку",
    mock: {
      nodes: {
        complaint_processor: [{ type: "text", content: "Жалоба зарегистрирована" }],
      },
    },
    expectedStates: ["completed"],
  },
  {
    flowId: "example_react",
    branch: "default",
    text: "Привет! Ответь коротко для нагрузочного теста.",
    mock: {
      nodes: {
        main: [{ type: "text", content: "Привет! Stress response ready." }],
      },
    },
    expectedStates: ["completed"],
  },
  {
    flowId: "example_react",
    branch: "direct_mode",
    text: "Собери короткую справку через subflow.",
    mock: {
      nodes: {
        direct_subflow: [{ type: "text", content: "Subflow stress response ready." }],
      },
    },
    expectedStates: ["completed"],
  },
];

function headers() {
  const result = {
    "Content-Type": "application/json",
    Accept: "application/json",
    "X-Company-Id": __ENV.STRESS_COMPANY_ID || "system",
  };
  if (TOKEN) result.Authorization = `Bearer ${TOKEN}`;
  return result;
}

function uuid(prefix) {
  return `${prefix}-${Date.now()}-${exec.vu.idInTest}-${exec.scenario.iterationInTest}`;
}

function caseForIteration() {
  return CASES[exec.scenario.iterationInTest % CASES.length];
}

function metadata(testCase) {
  const data = {
    execution_mode: "async",
    branch: testCase.branch,
    variables: {
      company_name: "Stress Lab",
      support_contacts: "stress@local",
      max_response_length: "320",
    },
  };
  if (USE_MOCK) {
    const caseMock = testCase.mock || {};
    data.__mock__ = {
      enabled: true,
      permission_groups: ["admin", "developers"],
      tools: caseMock.tools || {},
      nodes: caseMock.nodes || {},
      flows: caseMock.flows || {},
      llm: caseMock.llm || [],
    };
  }
  return data;
}

function rpc(flowId, method, params, tags) {
  return http.post(
    `${BASE_URL}/flows/api/v1/${flowId}`,
    JSON.stringify({
      jsonrpc: "2.0",
      id: uuid("rpc"),
      method,
      params,
    }),
    { headers: headers(), tags },
  );
}

function submitTask(testCase, taskId, contextId) {
  const res = rpc(
    testCase.flowId,
    "message/send",
    {
      message: {
        messageId: uuid("msg"),
        taskId,
        contextId,
        role: "user",
        parts: [{ kind: "text", text: testCase.text }],
      },
      metadata: metadata(testCase),
    },
    {
      endpoint: "a2a.message_send",
      flow_id: testCase.flowId,
      branch: testCase.branch,
    },
  );
  submitMs.add(res.timings.duration, { flow_id: testCase.flowId, branch: testCase.branch });
  const ok = check(res, {
    "message/send HTTP 200": (r) => r.status === 200,
    "message/send JSON-RPC result": (r) => Boolean(r.json("result.id")),
    "message/send async state": (r) => ["submitted", "working"].includes(r.json("result.status.state")),
  });
  if (!ok) submitFailed.add(1, { flow_id: testCase.flowId, branch: testCase.branch });
  return res;
}

function getTask(testCase, taskId, started) {
  for (let i = 0; i < MAX_POLLS; i += 1) {
    const res = rpc(
      testCase.flowId,
      "tasks/get",
      { id: taskId },
      {
        endpoint: "a2a.tasks_get",
        flow_id: testCase.flowId,
        branch: testCase.branch,
      },
    );
    pollMs.add(res.timings.duration, { flow_id: testCase.flowId, branch: testCase.branch });
    if (res.status === 200 && res.json("result.status.state")) {
      const state = res.json("result.status.state");
      if (["completed", "input-required", "failed", "canceled", "rejected"].includes(state)) {
        taskTotalMs.add(Date.now() - started, { flow_id: testCase.flowId, branch: testCase.branch, final_state: state });
        return { state, res };
      }
    }
    sleep(POLL_SLEEP_S);
  }
  pollTimeout.add(1, { flow_id: testCase.flowId, branch: testCase.branch });
  return { state: "timeout", res: null };
}

export default function runFlowsStress() {
  const testCase = caseForIteration();
  const taskId = uuid("task");
  const contextId = uuid("ctx");
  const started = Date.now();
  const submitted = submitTask(testCase, taskId, contextId);
  if (submitted.status !== 200 || !submitted.json("result.id")) return;

  const result = getTask(testCase, taskId, started);
  const ok = testCase.expectedStates.includes(result.state);
  check(result, {
    "task reached expected terminal state": () => ok,
  });
  if (!ok) taskFailed.add(1, { flow_id: testCase.flowId, branch: testCase.branch, final_state: result.state });
}

export function handleSummary(data) {
  const dir = __ENV.STRESS_RESULTS_DIR || "stress/results";
  return {
    stdout: markdownSummary(data),
    [`${dir}/summary.json`]: JSON.stringify(data, null, 2),
    [`${dir}/report.md`]: markdownSummary(data),
    [`${dir}/report.html`]: htmlSummary(data),
  };
}
