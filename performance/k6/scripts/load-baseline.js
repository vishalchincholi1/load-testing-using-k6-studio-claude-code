// Steady use: each user walks through all requests one by one, SLEEP seconds apart.
// VUS set    -> flat load for DURATION.
// VUS unset  -> ramp 1/3 -> peak -> 1/3 users over 5 stages (PEAK_VUS, STAGE_DURATION).
import { sleep } from "k6";
import { login } from "../lib/login.js";
import { loadCatalog, pickRow, sendOne } from "../lib/send.js";
import { makeSummary } from "../lib/report.js";

const { requests, rows, trends } = loadCatalog();

const peak = Number(__ENV.PEAK_VUS || 300);
const third = Math.max(1, Math.round(peak / 3));
const stageDuration = __ENV.STAGE_DURATION || "2m";

export const options = {
  scenarios: {
    baseline: __ENV.VUS
      ? { executor: "constant-vus", vus: Number(__ENV.VUS), duration: __ENV.DURATION || "2m" }
      : {
          executor: "ramping-vus",
          startVUs: third,
          gracefulRampDown: "30s",
          stages: [third, peak, peak, peak, third].map((target) => ({ duration: stageDuration, target })),
        },
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
  for (const r of requests) {
    sendOne(r, row, data.token, trends);
    sleep(Number(__ENV.SLEEP || 1));
  }
}

export function handleSummary(data) {
  return makeSummary(data, "load-baseline");
}
