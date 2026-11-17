"""Tests for convert.py. Run: python -I -B .claude/skills/k6-recording-to-lib/scripts/test_convert.py"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import convert  # noqa: E402

CATALOGS = """import * as sample from "./pages/requests-sample.js";
// <k6-recording-to-lib:imports>

export const catalogs = {
  sample: sample.requests,
  // <k6-recording-to-lib:entries>
};
"""

API = "https://dev.example.com/api/v1"
RANGE = {"date_range": {"start_date": "2026-06-01", "end_date": "2026-06-30"}, "query_id": "abc", "occurred_at": "x"}


def entry(method, url, body=None, gap=0.0):
    return {"method": method, "url": url, "body": json.dumps(body) if body is not None else None, "gap": gap}


def k6_block(method, url, body=None):
    """One call as k6 Studio writes it: params, http.url, http.request, check."""
    b = "null" if body is None else "`" + json.dumps(body) + "`"
    return (f"  params = {{ headers: {{ 'content-type': 'application/json' }}, cookies: {{}} }}\n"
            f"  url = http.url`{url}`\n"
            f"  resp = http.request('{method}', `${{url}}`, {b}, params)\n"
            f"  check(resp, {{ 'status equals 200': (r) => r.status.toString() === '200' }})\n")


def k6_script(*parts):
    return "import http from 'k6/http'\nexport default function main() {\n let params, resp, url\n" + "".join(parts) + "}\n"


class ConvertTests(unittest.TestCase):
    def run_convert(self, entries):
        return convert.convert(entries, "/api/v1", "/auth/", 2.0)

    def test_drops_outside_prefix_auth_and_duplicates(self):
        steps, _, rep = self.run_convert([
            entry("GET", "https://dev.example.com/static/app.js"),
            entry("POST", f"{API}/auth/login", {"email": "a", "password": "b"}),
            entry("GET", f"{API}/things"),
            entry("GET", f"{API}/things"),
        ])
        self.assertEqual([len(s) for s in steps], [1])
        self.assertEqual((rep["dropped_prefix"], rep["dropped_auth"], rep["dropped_dup"]), (1, 1, 1))

    def test_dates_become_placeholders_and_volatile_keys_removed(self):
        steps, ranges, _ = self.run_convert([entry("POST", f"{API}/q", RANGE)])
        body = steps[0][0]["body"]
        self.assertEqual(body["date_range"], {"start_date": "{{START_DATE}}", "end_date": "{{END_DATE}}"})
        self.assertNotIn("query_id", body)
        self.assertNotIn("occurred_at", body)
        self.assertEqual(ranges, [("2026-06-01", "2026-06-30")])
        self.assertEqual(convert.verify(convert.render_catalog("x", steps)), [])

    def test_gap_starts_new_step_even_across_dropped_requests(self):
        steps, _, _ = self.run_convert([
            entry("GET", f"{API}/a"),
            entry("GET", f"{API}/b", gap=0.5),
            entry("GET", "https://other.example.com/x", gap=3.0),
            entry("GET", f"{API}/a", gap=0.1),
        ])
        self.assertEqual([len(s) for s in steps], [2, 1])

    def test_empty_and_wrong_prefix_are_errors(self):
        with self.assertRaises(convert.ConvertError):
            convert.entries_from_har({"log": {"entries": []}})
        with self.assertRaises(convert.ConvertError):
            self.run_convert([entry("GET", "https://x.com/other")])

    def test_non_json_body_is_error(self):
        with self.assertRaises(convert.ConvertError):
            self.run_convert([{"method": "POST", "url": f"{API}/a", "body": "a=b", "gap": 0}])

    def test_verify_catches_leaks(self):
        self.assertTrue(convert.verify('{ body: {"password": "x"} }'))
        self.assertTrue(convert.verify('{ body: {"d": "2026-07-01"} }'))

    def test_extra_ranges(self):
        self.assertEqual(convert.parse_extra("2026-07-01:2026-07-31"), [("2026-07-01", "2026-07-31")])
        self.assertEqual(convert.parse_extra("none"), [])
        with self.assertRaises(convert.ConvertError):
            convert.parse_extra("july")

    def test_parses_k6_studio_script(self):
        script = k6_script(
            k6_block("POST", f"{API}/auth/login", {"email": "a", "password": "b"}),
            "  sleep(0.5)\n",
            k6_block("GET", f"{API}/things?x=1"),
            "  sleep(4.2)\n",
            k6_block("POST", f"{API}/q", RANGE),
        )
        entries = convert.entries_from_k6_script(script)
        self.assertEqual([e["method"] for e in entries], ["POST", "GET", "POST"])
        self.assertEqual(entries[2]["gap"], 4.2)
        steps, ranges, rep = self.run_convert(entries)
        self.assertEqual([len(s) for s in steps], [1, 1])
        self.assertEqual(steps[0][0]["path"], "/things?x=1")
        self.assertEqual(ranges, [("2026-06-01", "2026-06-30")])
        self.assertEqual(rep["dropped_auth"], 1)

    def test_half_deleted_k6_block_is_error(self):
        broken = "export default function () {\n  resp = http.request('GET', `${url}`, null, params)\n}\n"
        with self.assertRaises(convert.ConvertError):
            convert.entries_from_k6_script(broken)
        with self.assertRaises(convert.ConvertError):
            convert.entries_from_k6_script("export default function () {}\n")

    def test_end_to_end_writes_files_registers_once_and_needs_force(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "performance"
            (root / "k6" / "lib").mkdir(parents=True)
            (root / "k6" / "lib" / "catalogs.js").write_text(CATALOGS, encoding="utf-8")
            rec = Path(d) / "my-page.js"
            rec.write_text(k6_script(k6_block("POST", f"{API}/q", RANGE)), encoding="utf-8")
            args = ["--recording", str(rec), "--name", "my-page", "--root", str(root),
                    "--extra-ranges", "2026-07-01:2026-07-31"]
            self.assertEqual(convert.main(args), 0)
            self.assertEqual(convert.main(args), 2)  # exists, needs --force
            self.assertEqual(convert.main(args + ["--force"]), 0)
            cat = (root / "k6" / "lib" / "catalogs.js").read_text(encoding="utf-8")
            self.assertEqual(cat.count('"my-page": c_my_page.requests'), 1)
            self.assertEqual(cat.count("requests-my-page.js"), 1)
            csv = (root / "shared" / "inputs" / "my-page.csv").read_text(encoding="utf-8")
            self.assertEqual(csv.splitlines(), ["start_date,end_date", "2026-06-01,2026-06-30", "2026-07-01,2026-07-31"])

    def test_har_input_still_works_dry_run_and_bad_name(self):
        with tempfile.TemporaryDirectory() as d:
            rec = Path(d) / "rec.har"
            har = {"log": {"entries": [{"startedDateTime": "2026-07-01T10:00:00.000Z",
                                        "request": {"method": "GET", "url": f"{API}/a"}}]}}
            rec.write_text(json.dumps(har), encoding="utf-8")
            self.assertEqual(convert.main(["--recording", str(rec), "--name", "a", "--root", d, "--dry-run"]), 0)
            self.assertFalse((Path(d) / "k6").exists())
            self.assertEqual(convert.main(["--recording", str(rec), "--name", "Bad & Name", "--root", d]), 2)


if __name__ == "__main__":
    unittest.main()
