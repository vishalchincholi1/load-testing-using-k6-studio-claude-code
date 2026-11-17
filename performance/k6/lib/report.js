import { htmlReport } from "https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.2/index.js";

// Builds the 3 report files (html, json, -slowest.md) plus the console summary.
export function makeSummary(data, testName) {
  const dir = __ENV.REPORTS_DIR || "../reports";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-"); // UTC
  const base = `${dir}/${testName}-${stamp}`;
  return {
    stdout: textSummary(data, { indent: " ", enableColors: false }),
    [`${base}.html`]: htmlReport(data),
    [`${base}.json`]: JSON.stringify(data, null, 2),
    [`${base}-slowest.md`]: slowest(data),
  };
}

function slowest(data) {
  const rows = Object.keys(data.metrics)
    .filter((k) => k.startsWith("req_"))
    .map((k) => ({ name: k.slice(4), v: data.metrics[k].values }))
    .sort((a, b) => b.v["p(95)"] - a.v["p(95)"]);
  const f = (n) => (n === undefined ? "-" : n.toFixed(0));
  let md = "# Slowest requests (by p95, ms)\n\n| Request | avg | p95 | max | count |\n| --- | --- | --- | --- | --- |\n";
  for (const r of rows) {
    md += `| ${r.name} | ${f(r.v.avg)} | ${f(r.v["p(95)"])} | ${f(r.v.max)} | ${r.v.count} |\n`;
  }
  return md;
}
