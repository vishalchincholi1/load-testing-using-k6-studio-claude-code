---
name: k6-recording-to-lib
description: Convert a trimmed k6 Studio recording (generated .js script) into a reusable k6 request catalog plus a date-range CSV, register it, and verify it. Use when the user wants to turn a recorded page journey into a load test.
---

# k6-recording-to-lib

Turns a k6 Studio script into files the k6 scripts can replay. Never edit generated files by hand; fix `scripts/convert.py` (tests first) and re-run.

## Steps

1. **Find recordings.** List `performance/k6/k6-studio-raw-scripts/*.js`, ignoring `*-original.js` (those are untouched backups, never converted). If the user has only an `-original.js`, offer to make the trimmed final copy first (README, Step 1b): copy it, remove whole call blocks the user names (`params`, `http.url`, `http.request`, `check` together), keep the original unchanged, and list what was removed. Ask which recording to use and what to name the test (lowercase letters, digits and dashes, one per page, e.g. `checkout-page`). Reject names with spaces or `&`.
2. **Dry run.** From the repo root:
   ```bash
   python -I -B .claude/skills/k6-recording-to-lib/scripts/convert.py --recording <file> --name <name> --api-prefix <prefix> --dry-run
   ```
   Ask the user for the API prefix (default `/api/v1`) if unsure. Show the report: recorded to kept counts, one line per step, date ranges found, and any `UNRESOLVED` or `WARNING` line. Explain every such line before going on. A new step starts after a pause of 2 seconds or more between calls (`--step-gap`).
3. **Ask about extra date ranges.** Offer `none`, or ranges like `2026-07-01:2026-07-31,2026-06-01:2026-06-30`. They must be dates the system has data for.
4. **Write.** Re-run without `--dry-run`, adding `--extra-ranges "<answer>"`. This writes `performance/k6/lib/pages/requests-<name>.js` and `performance/shared/inputs/<name>.csv`, and adds one line each to `performance/k6/lib/catalogs.js`. If the catalog already exists the converter stops; use `--force` only when the user wants to regenerate it.
5. **Verify.**
   - Check the catalog loads: `CATALOG=<name> BASE_URL=http://localhost k6 inspect performance/k6/scripts/page-load-retail.js` (from the repo root; it must print options without an error).
   - Confirm the generated file contains no tokens, passwords or literal dates (the converter also checks this and exits 3 if it fails).
   - Offer a 1-user smoke test: `CATALOG=<name> VUS=1 BURSTS=1 bash performance/k6/run.sh page-load-retail dev`.

## Exit codes

- `0` ok.
- `2` the recording has a shape the converter does not know (for example a half-deleted call block or a non-JSON body), or the catalog exists. Say so. If it is a new shape, add a failing test in `scripts/test_convert.py`, fix `convert.py`, re-run. Do not patch the generated file.
- `3` verification found a leaked secret or date. Stop and tell the user.

## Rules

- Never print, copy or commit the raw recording; it holds a password and a live token.
- Run the tests after any converter change: `python -I -B .claude/skills/k6-recording-to-lib/scripts/test_convert.py`.
- `.har` files also work with `--recording`.
