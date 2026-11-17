// Page load: each virtual user fires all of a page's requests at once (a burst), repeatedly.
import http from "k6/http";
import { Trend } from "k6/metrics";
import { login } from "../lib/login.js";
import { loadCatalog, pickRow, build, verify } from "../lib/send.js";
import { makeSummary } from "../lib/report.js";

const { requests, rows, trends } = loadCatalog();
const wall = new Trend("page_load_wall_duration_ms", true);

const vus = Number(__ENV.VUS || 1);
export const options = {
  scenarios: {
    page_load: __ENV.BURSTS
      ? { executor: "per-vu-iterations", vus, iterations: Number(__ENV.BURSTS), maxDuration: "30m" }
      : { executor: "constant-vus", vus, duration: __ENV.DURATION || "1m" },
  },
  // CHANGE FOR YOUR PROJECT: your pass/fail targets (SLOs).
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<3000"],
    checks: ["rate>0.99"],
  },
};

export function setup() {
  return { token: login() };
}

export default function (data) {
  const row = pickRow(rows, __ITER);
  const start = Date.now();
  const responses = http.batch(requests.map((r) => build(r, row, data.token)));
  wall.add(Date.now() - start);
  responses.forEach((res, i) => verify(requests[i], res, trends));
}

export function handleSummary(data) {
  return makeSummary(data, "page-load-retail");
}
