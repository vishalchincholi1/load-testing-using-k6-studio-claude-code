import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";
import { SharedArray } from "k6/data";
import { catalogs } from "./catalogs.js";
import { templateBody } from "./requests-retail.js";

export const CATALOG = __ENV.CATALOG || "sample";
export const SLOW_MS = Number(__ENV.SLOW_MS || 3000);

export function metricName(r) {
  return "req_" + r.name.replace(/[^A-Za-z0-9]+/g, "_").slice(0, 60);
}

// Loads one catalog (all steps) and its date-range CSV. Call at init level.
export function loadCatalog() {
  const all = catalogs[CATALOG];
  if (!all) {
    throw new Error(`Unknown CATALOG "${CATALOG}". Known: ${Object.keys(catalogs).join(", ")}`);
  }
  const step = Number(__ENV.STEP || 0);
  const requests = all.filter((r) => r.step === step);
  if (requests.length === 0) throw new Error(`Catalog "${CATALOG}" has no requests for STEP=${step}`);

  const rows = new SharedArray("dates-" + CATALOG, () => parseCsv(open(`../../shared/inputs/${CATALOG}.csv`)));
  const trends = {};
  for (const r of requests) trends[r.name] = new Trend(metricName(r), true);
  return { requests, rows, trends };
}

function parseCsv(text) {
  const lines = text.replace(/\r/g, "").split("\n").filter((l) => l.trim() !== "");
  const head = lines[0].split(",");
  return lines.slice(1).map((l) => {
    const cells = l.split(",");
    const row = {};
    head.forEach((h, i) => (row[h.trim()] = (cells[i] || "").trim()));
    return row;
  });
}

// Picks the CSV row: row 0 normally, rotating through all rows when COLD=true.
export function pickRow(rows, iteration) {
  return __ENV.COLD === "true" ? rows[iteration % rows.length] : rows[0];
}

// Returns [method, url, body, params] for http.batch / http.request.
export function build(r, row, token) {
  const headers = Object.assign({}, r.headers || {});
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const body = r.body === null || r.body === undefined ? null : templateBody(r.body, row);
  if (body !== null && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  return [r.method, `${__ENV.BASE_URL}${templateBody(r.path, row)}`, body, { headers, tags: { name: r.name } }];
}

export function verify(r, res, trends) {
  trends[r.name].add(res.timings.duration);
  return check(res, {
    "status is 2xx": (x) => x.status >= 200 && x.status < 300,
    "body is not empty": (x) => r.method === "OPTIONS" || (x.body && x.body.length > 0),
    [`duration < ${SLOW_MS}ms`]: (x) => x.timings.duration < SLOW_MS,
  });
}

export function sendOne(r, row, token, trends) {
  const res = http.request(...build(r, row, token));
  verify(r, res, trends);
  return res;
}
