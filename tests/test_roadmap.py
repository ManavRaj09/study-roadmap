import json, sys, tempfile, unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import roadmap as r

OUTLINE = "# C\n## M1\n- A (3h)\n- B\n## M2\n- C (4.5h)\n"
START = date(2026, 10, 12)  # a Monday


def course():
    return r.parse_outline(OUTLINE)


class T(unittest.TestCase):
    def test_parse(self):
        c = course()
        self.assertEqual(c["name"], "C")
        self.assertEqual([m["name"] for m in c["modules"]], ["M1", "M2"])
        self.assertEqual([t["hours"] for t in c["modules"][0]["topics"]], [3.0, 1.0])

    def test_json_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "c.json")
            p.write_text(json.dumps({"name": "J", "modules": [{"name": "m", "topics": [{"name": "t"}]}]}))
            self.assertEqual(r.load_course(p)["modules"][0]["topics"][0]["hours"], 1.0)
            q = Path(d, "bad.md")
            q.write_text("# nothing")
            with self.assertRaises(ValueError):
                r.load_course(q)

    def test_days_respected_and_capacity(self):
        days = r.parse_days("mon,wed")
        plan = r.make_plan(course(), START, days, 2.0)
        per_day = {}
        for s in plan["sessions"]:
            self.assertIn(r.DAYS[s["date"].weekday()], days)
            per_day[s["date"]] = per_day.get(s["date"], 0) + s["hours"]
        self.assertTrue(all(h <= 2.0 + 1e-9 for h in per_day.values()))
        self.assertAlmostEqual(sum(s["hours"] for s in plan["sessions"]), plan["total"])

    def test_exam_compression(self):
        exam = START + timedelta(days=5)
        plan = r.make_plan(course(), START, r.parse_days("weekdays"), 1.0, exam=exam)
        self.assertLess(plan["scale"], 1.0)
        self.assertLess(plan["end"], exam)
        self.assertTrue(plan["notes"])

    def test_exam_with_spare_time(self):
        exam = START + timedelta(days=60)
        plan = r.make_plan(course(), START, r.parse_days("all"), 3.0, exam=exam)
        self.assertEqual(plan["scale"], 1.0)
        self.assertIn("spare", plan["notes"][0])

    def test_outputs_and_progress(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d, "c.md")
            c.write_text(OUTLINE)
            out = Path(d, "o")
            r.main(["build", str(c), "--start", "2026-10-12", "--out", str(out)])
            for f in ("ROADMAP.md", "TIMETABLE.md", "timetable.ics", "timetable.csv"):
                self.assertTrue((out / f).exists(), f)
            ics = (out / "timetable.ics").read_text()
            self.assertEqual(ics.count("BEGIN:VEVENT"), ics.count("END:VEVENT"))
            self.assertGreater(ics.count("BEGIN:VEVENT"), 3)
            road = (out / "ROADMAP.md").read_text()
            self.assertIn("```mermaid", road)
            (out / "ROADMAP.md").write_text(road.replace("- [ ]", "- [x]", 1))
            r.main(["progress", str(out / "ROADMAP.md")])


if __name__ == "__main__":
    unittest.main()
