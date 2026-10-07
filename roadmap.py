#!/usr/bin/env python3
"""Study Roadmap Generator: turn any course outline into a roadmap + study timetable.

Usage:
    python roadmap.py init my-course.md
    python roadmap.py build my-course.md --start 2026-10-12 --hours 3 --exam 2026-12-10
    python roadmap.py progress out/ROADMAP.md
"""
import argparse
import csv
import json
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
STEP = 0.25  # all hours are rounded to quarter-hours

TEMPLATE = """# My Course Name
## Module 1: Basics
- First topic (2h)
- Second topic (3h)
## Module 2: Going deeper
- Third topic (4h)
- Fourth topic (2.5h)
"""


def snap(h):
    return max(STEP, round(h / STEP) * STEP)


# ---------------------------------------------------------------- input
def parse_outline(text):
    """Markdown outline: '# Course', '## Module', '- Topic (2h)'."""
    course, mod = {"name": "Untitled course", "modules": []}, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            mod = {"name": line[3:].strip(), "topics": []}
            course["modules"].append(mod)
        elif line.startswith("# "):
            course["name"] = line[2:].strip()
        elif re.match(r"^[-*]\s+", line):
            if mod is None:
                mod = {"name": "Module 1", "topics": []}
                course["modules"].append(mod)
            body = re.sub(r"^[-*]\s+", "", line)
            h = re.search(r"\(\s*(\d+(?:\.\d+)?)\s*h\s*\)\s*$", body)
            mod["topics"].append({
                "name": body[:h.start()].strip() if h else body,
                "hours": float(h.group(1)) if h else 1.0,
            })
    return course


def load_course(path):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    course = json.loads(text) if p.suffix.lower() == ".json" else parse_outline(text)
    if not course.get("modules"):
        raise ValueError("course has no modules (use '## Module name' lines)")
    for m in course["modules"]:
        if not m.get("topics"):
            raise ValueError(f"module '{m.get('name')}' has no topics")
        for t in m["topics"]:
            t["hours"] = float(t.get("hours", 1))
            if t["hours"] <= 0:
                raise ValueError(f"topic '{t.get('name')}' must have hours > 0")
    course.setdefault("name", p.stem)
    return course


def parse_days(s):
    s = s.lower().strip()
    presets = {"weekdays": DAYS[:5], "weekends": DAYS[5:], "all": DAYS, "daily": DAYS}
    if s in presets:
        return set(presets[s])
    days = {d.strip()[:3] for d in s.split(",") if d.strip()}
    bad = days - set(DAYS)
    if bad or not days:
        raise ValueError(f"invalid --days value: {s!r} (use e.g. mon,wed,fri or weekdays/all)")
    return days


# ---------------------------------------------------------------- planning
def build_tasks(course, rev_ratio=0.25, scale=1.0):
    tasks = []
    for mi, m in enumerate(course["modules"]):
        mod_hours = 0.0
        for t in m["topics"]:
            h = snap(t["hours"] * scale)
            mod_hours += h
            tasks.append(dict(module=mi, mname=m["name"], name=t["name"], key=t["name"],
                              hours=h, kind="study"))
        rname = f"Revise: {m['name']}"
        tasks.append(dict(module=mi, mname=m["name"], name=rname, key=rname,
                          hours=snap(mod_hours * rev_ratio), kind="revision"))
    total = sum(t["hours"] for t in tasks)
    tasks.append(dict(module=len(course["modules"]), mname="Final review",
                      name="Mock test + weak-spot revision", key="Mock test + weak-spot revision",
                      hours=snap(total * rev_ratio), kind="final"))
    return tasks


def schedule(tasks, start, days, hpd, start_time="18:00", brk=10, block=2.0):
    hh, mm = (int(x) for x in start_time.split(":"))

    def roll(d, inclusive):
        if not inclusive:
            d += timedelta(days=1)
        while DAYS[d.weekday()] not in days:
            d += timedelta(days=1)
        return d

    day, used, n, out = roll(start, True), 0.0, 0, []
    for t in tasks:
        remaining, first = t["hours"], True
        while remaining > 1e-9:
            free = hpd - used
            if free <= 1e-9 or (used > 0 and free < min(0.5, remaining)):
                day, used, n = roll(day, False), 0.0, 0
                continue
            chunk = min(remaining, free, block)
            s = datetime.combine(day, time(hh, mm)) + timedelta(hours=used, minutes=brk * n)
            out.append({**t, "name": t["name"] + ("" if first else " (cont.)"),
                        "hours": chunk, "start": s, "end": s + timedelta(hours=chunk), "date": day})
            used, n, remaining, first = used + chunk, n + 1, remaining - chunk, False
    return out


def count_slots(start, end, days):
    n, d = 0, start
    while d <= end:
        n += DAYS[d.weekday()] in days
        d += timedelta(days=1)
    return n


def make_plan(course, start, days, hpd, block=2.0, rev_ratio=0.25, exam=None, start_time="18:00"):
    notes, scale = [], 1.0
    tasks = build_tasks(course, rev_ratio)
    need = sum(t["hours"] for t in tasks)
    if exam:
        last = exam - timedelta(days=1)
        slots = count_slots(start, last, days)
        if slots == 0:
            raise ValueError("no study days available between --start and --exam")
        cap = slots * hpd
        if need > cap:
            orig = need
            scale = cap / need
            for _ in range(80):
                tasks = build_tasks(course, rev_ratio, scale)
                need = sum(t["hours"] for t in tasks)
                if need <= cap + 1e-9:
                    break
                scale *= 0.97
            notes.append(f"Needs {orig:g}h but only {cap:g}h are available before the exam "
                         f"({slots} study days x {hpd:g}h). Topic hours were compressed to "
                         f"{scale:.0%}. To keep full depth, study ~{orig / slots:.1f}h/day or add days.")
    sessions = schedule(tasks, start, days, hpd, start_time, block=block)
    end = sessions[-1]["date"]
    if exam:
        if end >= exam:
            notes.append(f"Plan still runs past the exam date (ends {end:%d %b}). Add study days or hours.")
        else:
            spare = count_slots(end + timedelta(days=1), exam - timedelta(days=1), days)
            notes.append(f"Plan finishes {end:%a %d %b %Y}, with {spare} spare study day(s) before the exam."
                         if spare else f"Plan finishes {end:%a %d %b %Y}, just before the exam.")
    return dict(tasks=tasks, sessions=sessions, notes=notes, scale=scale,
                total=sum(t["hours"] for t in tasks), start=sessions[0]["date"], end=end)


# ---------------------------------------------------------------- rendering
def fh(h):
    return f"{h:g}h"


def render_roadmap(course, plan, days, hpd):
    ss = plan["sessions"]
    names = [m["name"] for m in course["modules"]] + ["Final review"]
    L = [f"# {course['name']} - Roadmap", "",
         f"**{fh(plan['total'])}** in total | **{plan['start']:%d %b %Y}** to **{plan['end']:%d %b %Y}** | "
         f"{', '.join(d.title() for d in DAYS if d in days)}, {fh(hpd)}/day", ""]
    for n in plan["notes"]:
        L += [f"> Note: {n}", ""]
    L += ["```mermaid", "gantt", f"    title {re.sub(r'[:;,#]', ' ', course['name'])}",
          "    dateFormat YYYY-MM-DD", "    section Plan"]
    for mi, name in enumerate(names):
        ms = [s for s in ss if s["module"] == mi]
        if ms:
            a, b = ms[0]["date"], ms[-1]["date"]
            L.append(f"    {re.sub(r'[:;,#]', ' ', name)} :{a:%Y-%m-%d}, {(b - a).days + 1}d")
    L += ["```", "", "Tick the boxes as you go, then run `python roadmap.py progress ROADMAP.md`.", ""]
    for mi, name in enumerate(names):
        ms = [s for s in ss if s["module"] == mi]
        if not ms:
            continue
        items = {}
        for s in ms:
            it = items.setdefault(s["key"], dict(hours=0.0, date=s["date"], kind=s["kind"]))
            it["hours"] += s["hours"]
        head = f"Module {mi + 1}: {name}" if mi < len(course["modules"]) else name
        L += [f"## {head}",
              f"*{fh(sum(s['hours'] for s in ms))} | {ms[0]['date']:%d %b} - {ms[-1]['date']:%d %b}*", ""]
        for key, it in items.items():
            icon = "" if it["kind"] == "study" else "(review) "
            L.append(f"- [ ] {icon}**{key}**: {fh(it['hours'])}, starts {it['date']:%a %d %b}")
        if mi < len(course["modules"]):
            L += ["", "> Checkpoint: close your notes, explain each topic aloud in your own words, "
                      "then solve 5+ past-paper or textbook problems."]
        L.append("")
    return "\n".join(L)


def render_timetable(course, plan):
    weeks = {}
    for s in plan["sessions"]:
        weeks.setdefault(s["date"] - timedelta(days=s["date"].weekday()), []).append(s)
    L = [f"# {course['name']} - Study Timetable", ""]
    for i, (mon, ss) in enumerate(sorted(weeks.items()), 1):
        L += [f"## Week {i} ({mon:%d %b} - {mon + timedelta(days=6):%d %b %Y})", "",
              "| Date | Time | Task | Module | Hours | Done |", "|---|---|---|---|---|---|"]
        for s in ss:
            L.append(f"| {s['date']:%a %d %b} | {s['start']:%H:%M}-{s['end']:%H:%M} | {s['name']} "
                     f"| {s['mname']} | {fh(s['hours'])} | [ ] |")
        L += ["", f"**Week total:** {fh(sum(s['hours'] for s in ss))}", ""]
    return "\n".join(L)


def ics_escape(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def render_ics(course, sessions):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//study-roadmap//EN", "CALSCALE:GREGORIAN"]
    for i, s in enumerate(sessions):
        L += ["BEGIN:VEVENT", f"UID:{i}-{s['start']:%Y%m%dT%H%M}@study-roadmap", f"DTSTAMP:{stamp}",
              f"DTSTART:{s['start']:%Y%m%dT%H%M%S}", f"DTEND:{s['end']:%Y%m%dT%H%M%S}",
              "SUMMARY:" + ics_escape(s["name"]),
              "DESCRIPTION:" + ics_escape(f"{course['name']} / {s['mname']}"), "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def write_csv(path, sessions):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "day", "start", "end", "module", "task", "type", "hours"])
        for s in sessions:
            w.writerow([s["date"], f"{s['date']:%a}", f"{s['start']:%H:%M}", f"{s['end']:%H:%M}",
                        s["mname"], s["name"], s["kind"], s["hours"]])


# ---------------------------------------------------------------- commands
def cmd_build(a):
    course = load_course(a.course)
    days = parse_days(a.days)
    start = date.fromisoformat(a.start) if a.start else date.today()
    exam = date.fromisoformat(a.exam) if a.exam else None
    plan = make_plan(course, start, days, a.hours, a.block, a.revision, exam, a.time)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ROADMAP.md").write_text(render_roadmap(course, plan, days, a.hours), encoding="utf-8")
    (out / "TIMETABLE.md").write_text(render_timetable(course, plan), encoding="utf-8")
    (out / "timetable.ics").write_text(render_ics(course, plan["sessions"]), encoding="utf-8", newline="")
    write_csv(out / "timetable.csv", plan["sessions"])
    print(f"{course['name']}: {fh(plan['total'])} over {len(plan['sessions'])} sessions, "
          f"{plan['start']:%d %b %Y} -> {plan['end']:%d %b %Y}")
    for n in plan["notes"]:
        print("  NOTE:", n)
    print(f"Wrote ROADMAP.md, TIMETABLE.md, timetable.ics, timetable.csv to {out}/")


def cmd_init(a):
    p = Path(a.path)
    if p.exists():
        sys.exit(f"{p} already exists")
    p.write_text(TEMPLATE, encoding="utf-8")
    print(f"Created {p}. Edit it, then run: python roadmap.py build {p}")


def cmd_progress(a):
    text = Path(a.file).read_text(encoding="utf-8")
    done = len(re.findall(r"^\s*- \[[xX]\]", text, re.M))
    todo = len(re.findall(r"^\s*- \[ \]", text, re.M))
    if done + todo == 0:
        sys.exit("no checkboxes found")
    pct = done / (done + todo)
    print(f"[{'#' * round(pct * 30):<30}] {pct:.0%}  ({done}/{done + todo} items done)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="roadmap", description="Course roadmap + study timetable generator")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="generate roadmap and timetable from a course file")
    b.add_argument("course", help="outline (.md/.txt) or .json file")
    b.add_argument("--start", help="start date YYYY-MM-DD (default: today)")
    b.add_argument("--exam", help="exam/deadline date YYYY-MM-DD (plan is fitted before it)")
    b.add_argument("--hours", type=float, default=2.0, help="study hours per day (default 2)")
    b.add_argument("--days", default="weekdays", help="mon,tue,... or weekdays/weekends/all")
    b.add_argument("--time", default="18:00", help="daily start time HH:MM (default 18:00)")
    b.add_argument("--block", type=float, default=2.0, help="max hours per topic session (default 2)")
    b.add_argument("--revision", type=float, default=0.25, help="revision share per module (default 0.25)")
    b.add_argument("--out", default="out", help="output folder (default out)")
    b.set_defaults(fn=cmd_build)
    i = sub.add_parser("init", help="create a starter course outline")
    i.add_argument("path", nargs="?", default="my-course.md")
    i.set_defaults(fn=cmd_init)
    p = sub.add_parser("progress", help="show completion % from ticked checkboxes")
    p.add_argument("file")
    p.set_defaults(fn=cmd_progress)
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (ValueError, OSError) as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
