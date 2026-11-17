// Capacity: sends a fixed rate of requests per second regardless of how slow the server is.
import { login } from "../lib/login.js";
import { loadCatalog, pickRow, sendOne } from "../lib/send.js";
import { makeSummary } from "../lib/report.js";

const { requests, rows, trends } = loadCatalog();

export const options = {
  scenarios: {
    capacity: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.RATE || 500),
      timeUnit: "1s",
      duration: __ENV.DURATION || "1m",
      preAllocatedVUs: Number(__ENV.PRE_VUS || 100),
      maxVUs: Number(__ENV.MAX_VUS || 1000),
    },
  },
  // CHANGE FOR YOUR PROJECT: your pass/fail targets (SLOs).
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<3000"],
  },
};

export function setup() {
  return { token: login() };
}

export default function (data) {
  const r = requests[__ITER % requests.length];
  sendOne(r, pickRow(rows, __ITER), data.token, trends);
}

export function handleSummary(data) {
  return makeSummary(data, "load-capacity");
}
