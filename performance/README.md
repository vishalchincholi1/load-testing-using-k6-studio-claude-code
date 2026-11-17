# performance/

Run reference for the load-test template. The full guide is the [root README](../README.md).

```text
performance/
  k6/
    run.sh                  bash performance/k6/run.sh <script> <env-profile>
    scripts/                test types: page-load-retail, load-baseline, load-capacity
    lib/
      login.js              login (skipped if LOGIN_PATH is empty)
      send.js               builds requests, checks, picks the date row
      report.js             writes the .html / .json / -slowest.md reports
      requests-retail.js    fills {{START_DATE}} / {{END_DATE}} placeholders
      catalogs.js           registry of catalogs (do not remove the marker comments)
      pages/                one requests-<name>.js per recorded page (generated)
    k6-studio-raw-scripts/  put k6 Studio recordings (.har) here; git-ignored
    reports/                run output; git-ignored
  shared/
    env/.env.example        copy to .env.<profile>; git-ignored once copied
    inputs/<name>.csv       date ranges per catalog
```

## Try it in 1 minute

```bash
cp performance/shared/env/.env.example performance/shared/env/.env.dev
CATALOG=sample VUS=1 BURSTS=1 bash performance/k6/run.sh page-load-retail dev
```

This hits the public Grafana QuickPizza demo API using the `sample` catalog. Open the `.html` in `performance/k6/reports/`.

## Settings

| Setting | Used by | Default |
| --- | --- | --- |
| `CATALOG` | all | `sample` |
| `VUS` | page-load, baseline | 1 (baseline: unset = ramp) |
| `BURSTS` | page-load | unset (repeat for `DURATION`) |
| `DURATION` | all | 1m (baseline 2m) |
| `PEAK_VUS`, `STAGE_DURATION` | baseline ramp | 300, 2m |
| `SLEEP` | baseline | 1 (seconds between requests) |
| `STEP` | all | 0 |
| `COLD` | all | false (`true` rotates CSV date ranges) |
| `RATE`, `PRE_VUS`, `MAX_VUS` | capacity | 500, 100, 1000 |
| `SLOW_MS` | all | 3000 |
| `REPORTS_DIR` | all | `../reports` |
