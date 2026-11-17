#!/usr/bin/env python3
"""Convert a k6 Studio recording (generated .js script, or .har) into a k6 request catalog + date CSV.

Writes (unless --dry-run):
  performance/k6/lib/pages/requests-<name>.js
  performance/shared/inputs/<name>.csv
and registers <name> in performance/k6/lib/catalogs.js.

Exit codes: 0 ok, 2 recording has a shape this converter does not handle,
3 verification failed (a date, token or password leaked into generated files).

CHANGE FOR YOUR PROJECT (see README, "Adopting this template"):
  --api-prefix, --auth-prefix, DATE_PATHS, DROP_BODY_KEYS.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
RANGE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})$")
SECRET_RE = re.compile(r"bearer\s|password|passwd|access_token|refresh_token|authorization", re.I)

# Body paths holding the date range: (parent key, start key, end key).
DATE_PATHS = [("date_range", "start_date", "end_date")]
# Keys that change on every call and must not be replayed.
DROP_BODY_KEYS = {"query_id", "occurred_at"}


class ConvertError(Exception):
    """Recording has a shape the converter does not know (exit 2)."""


def parse_time(text):
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def clean_body(node, ranges):
    """Drop volatile keys and replace date-range values with placeholders."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in DROP_BODY_KEYS:
                continue
            out[key] = clean_body(value, ranges)
        for parent, start, end in DATE_PATHS:
            block = out.get(parent)
            if isinstance(block, dict) and start in block and end in block:
                if DATE_RE.fullmatch(str(block[start])[:10]) and DATE_RE.fullmatch(str(block[end])[:10]):
                    ranges.append((str(block[start])[:10], str(block[end])[:10]))
                    block[start] = "{{START_DATE}}"
                    block[end] = "{{END_DATE}}"
        return out
    if isinstance(node, list):
        return [clean_body(v, ranges) for v in node]
    return node


def entries_from_har(har):
    """Normalise a .har file into [{method, url, body, gap}] (gap = seconds since previous request)."""
    raw = har.get("log", {}).get("entries") if isinstance(har, dict) else None
    if not isinstance(raw, list) or not raw:
        raise ConvertError("No entries found in the .har file.")
    out, last = [], None
    for e in raw:
        req = e.get("request", {})
        t = parse_time(e.get("startedDateTime"))
        gap = (t - last).total_seconds() if (t and last) else 0.0
        last = t or last
        out.append({"method": req.get("method", "GET"), "url": req.get("url", ""),
                    "body": (req.get("postData") or {}).get("text"), "gap": gap})
    return out


# One regex walks a k6 Studio generated script in order: sleep(), http.url`...`, http.request(...).
_STR = r"""`(?:[^`\\]|\\.)*`|'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\""""
K6_TOKEN = re.compile(
    r"(?P<sleep>\bsleep\(\s*(?P<secs>[\d.]+)\s*\))"
    r"|(?P<url>\bhttp\.url\s*`(?P<u>[^`]*)`)"
    r"|(?P<req>\bhttp\.request\(\s*['\"](?P<m>[A-Za-z]+)['\"]\s*,\s*(?P<target>[^,]+?)\s*,\s*(?P<body>null|undefined|" + _STR + r")\s*,)"
)


def _unquote(lit):
    return re.sub(r"\\(.)", r"\1", lit[1:-1])


def entries_from_k6_script(text):
    """Normalise a k6 Studio generated script (.js). Each call is: params, http.url, http.request, check.
    A sleep() before a call becomes that call's gap."""
    out, url, gap = [], None, 0.0
    for m in K6_TOKEN.finditer(text):
        if m.group("sleep"):
            gap += float(m.group("secs"))
        elif m.group("url"):
            url = m.group("u")
        else:
            target = m.group("target").strip()
            if target.startswith("`") and "${url}" in target.replace(" ", "") or target == "url":
                this_url = url
            elif target[:1] in "`'\"":
                this_url = _unquote(target)
            else:
                this_url = url
            if not this_url:
                raise ConvertError("http.request() found without a URL. The block was probably half-deleted.")
            body = m.group("body")
            body = None if body in ("null", "undefined") else _unquote(body)
            out.append({"method": m.group("m"), "url": this_url, "body": body, "gap": gap})
            gap, url = 0.0, None
    if not out:
        raise ConvertError("No http.request() calls found. Expected a script saved by k6 Studio (Generate script).")
    return out


def load_entries(path):
    raw = Path(path).read_text(encoding="utf-8-sig")
    if str(path).lower().endswith(".har"):
        return entries_from_har(json.loads(raw))
    return entries_from_k6_script(raw)


def convert(entries, api_prefix, auth_prefix, step_gap):
    report = {"recorded": len(entries), "dropped_prefix": 0, "dropped_auth": 0, "dropped_dup": 0, "warnings": []}
    ranges, steps = [], []
    pending = 0.0  # silence seen since the last kept request, including dropped requests

    for e in entries:
        method = e["method"].upper()
        pending = max(pending, e["gap"])
        parts = urlsplit(e["url"])
        if not parts.path.startswith(api_prefix):
            report["dropped_prefix"] += 1
            continue
        path = parts.path[len(api_prefix):] or "/"
        if path.startswith(auth_prefix):
            report["dropped_auth"] += 1
            continue

        query = parts.query
        if DATE_RE.search(query):
            report["warnings"].append(f"UNRESOLVED date in query string of {method} {path}; not templated")
        full_path = path + (f"?{query}" if query else "")

        body = None
        text = e.get("body")
        if text:
            try:
                body = clean_body(json.loads(text), ranges)
            except json.JSONDecodeError:
                raise ConvertError(f"Body of {method} {path} is not JSON; extend the converter for this shape.")

        key = (method, full_path, json.dumps(body, sort_keys=True))
        if not steps or pending >= step_gap:
            steps.append([])
        pending = 0.0

        if any(x["_key"] == key for x in steps[-1]):
            report["dropped_dup"] += 1
            continue
        steps[-1].append({
            "_key": key,
            "name": f"{method} {path}",
            "method": method,
            "path": full_path,
            "body": body,
            "headers": {"Content-Type": "application/json"} if body is not None else None,
        })

    steps = [s for s in steps if s]
    if not steps:
        raise ConvertError(f"No requests left under prefix {api_prefix}. Check --api-prefix.")
    return steps, ranges, report


def js_literal(value):
    return json.dumps(value, indent=None, ensure_ascii=False)


def render_catalog(name, steps):
    lines = [
        f"// Generated by /k6-recording-to-lib for catalog '{name}'. Do not edit by hand; re-run the skill.",
        "export const requests = [",
    ]
    for i, step in enumerate(steps):
        for r in step:
            fields = [f"step: {i}", f"name: {js_literal(r['name'])}", f"method: {js_literal(r['method'])}",
                      f"path: {js_literal(r['path'])}", f"body: {js_literal(r['body'])}"]
            if r["headers"]:
                fields.append(f"headers: {js_literal(r['headers'])}")
            lines.append("  { " + ", ".join(fields) + " },")
    lines.append("];")
    return "\n".join(lines) + "\n"


def unique_ranges(recorded, extra):
    out = []
    for r in list(dict.fromkeys(recorded)) + extra:
        if r not in out:
            out.append(r)
    return out


def parse_extra(text):
    if not text or text.strip().lower() == "none":
        return []
    extra = []
    for chunk in text.split(","):
        m = RANGE_RE.match(chunk.strip())
        if not m:
            raise ConvertError(f"Bad range '{chunk.strip()}'. Use start:end like 2026-07-01:2026-07-31.")
        extra.append((m.group(1), m.group(2)))
    return extra


def render_csv(ranges):
    rows = ranges or [("2026-01-01", "2026-01-31")]
    return "start_date,end_date\n" + "".join(f"{a},{b}\n" for a, b in rows)


def register(catalogs_path, name):
    text = catalogs_path.read_text(encoding="utf-8")
    ident = "c_" + name.replace("-", "_")
    imp = f'import * as {ident} from "./pages/requests-{name}.js";\n'
    entry = f'  "{name}": {ident}.requests,\n'
    if imp in text:
        return False
    for marker, line in (("// <k6-recording-to-lib:imports>", imp), ("// <k6-recording-to-lib:entries>", entry)):
        idx = text.find(marker)
        if idx < 0:
            raise ConvertError(f"Marker '{marker}' missing in {catalogs_path}")
        start = text.rfind("\n", 0, idx) + 1
        text = text[:start] + line + text[start:]
    catalogs_path.write_text(text, encoding="utf-8")
    return True


def verify(js_text):
    problems = []
    if SECRET_RE.search(js_text):
        problems.append("possible token/password text in generated catalog")
    if DATE_RE.search(js_text):
        problems.append("literal date found in generated catalog (should be placeholders)")
    return problems


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--har", "--recording", dest="recording", required=True, help="final copy of the k6 Studio script (.js); .har also works")
    p.add_argument("--name", required=True, help="catalog name: lowercase letters, digits, dashes")
    p.add_argument("--api-prefix", default="/api/v1", help="only requests under this path are kept (default /api/v1)")
    p.add_argument("--auth-prefix", default="/auth/", help="paths (after the prefix) to skip (default /auth/)")
    p.add_argument("--extra-ranges", default="none", help="extra date ranges 'start:end,start:end' or 'none'")
    p.add_argument("--step-gap", type=float, default=2.0, help="seconds of silence that start a new step (default 2)")
    p.add_argument("--root", default="performance", help="performance folder (default ./performance)")
    p.add_argument("--force", action="store_true", help="overwrite an existing catalog of the same name")
    p.add_argument("--dry-run", action="store_true", help="print the report; write nothing")
    a = p.parse_args(argv)

    try:
        if not NAME_RE.match(a.name):
            raise ConvertError("Name must be lowercase letters, digits and dashes only (no spaces or '&').")
        steps, recorded, rep = convert(load_entries(a.recording), a.api_prefix, a.auth_prefix, a.step_gap)
        ranges = unique_ranges(recorded, parse_extra(a.extra_ranges))
        catalog = render_catalog(a.name, steps)
        kept = sum(len(s) for s in steps)

        print(f"recorded -> kept: {rep['recorded']} -> {kept} "
              f"(outside prefix {rep['dropped_prefix']}, auth {rep['dropped_auth']}, duplicates {rep['dropped_dup']})")
        for i, s in enumerate(steps):
            print(f"step {i}: {len(s)} requests")
        print(f"Date ranges found: {len(set(recorded))} recorded, {len(ranges)} total")
        for w in rep["warnings"]:
            print(w)

        problems = verify(catalog)
        if problems:
            print("VERIFY FAILED: " + "; ".join(problems), file=sys.stderr)
            return 3
        if a.dry_run:
            print("dry run: nothing written")
            return 0

        root = Path(a.root)
        page = root / "k6" / "lib" / "pages" / f"requests-{a.name}.js"
        csv_path = root / "shared" / "inputs" / f"{a.name}.csv"
        if page.exists() and not a.force:
            raise ConvertError(f"{page} already exists. Re-run with --force to overwrite.")
        page.parent.mkdir(parents=True, exist_ok=True)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(catalog, encoding="utf-8", newline="\n")
        csv_path.write_text(render_csv(ranges), encoding="utf-8", newline="\n")
        added = register(root / "k6" / "lib" / "catalogs.js", a.name)
        print(f"wrote {page}\nwrote {csv_path}\n{'registered' if added else 'already registered'} in catalogs.js")
        return 0
    except ConvertError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
