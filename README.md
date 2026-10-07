# Study Roadmap Generator

Turn **any course** (a syllabus, a skill, a book) into a **roadmap** and a **day-by-day study timetable** in seconds.
No dependencies. Just Python 3.8+.

## What you get

| File | Purpose |
|---|---|
| `ROADMAP.md` | Modules, topics with hours and start dates, a Gantt chart (renders on GitHub), tickable checkboxes |
| `TIMETABLE.md` | Week-by-week tables with exact times |
| `timetable.ics` | Import into Google Calendar, Apple Calendar or Outlook |
| `timetable.csv` | Open in Excel or Google Sheets |

## Quick start

```bash
git clone https://github.com/<you>/study-roadmap && cd study-roadmap

python roadmap.py init my-course.md          # creates a starter outline
# edit my-course.md, then:
python roadmap.py build my-course.md --start 2026-10-12 --hours 3 --exam 2026-12-10
python roadmap.py progress out/ROADMAP.md    # % complete after you tick boxes
```

Try the examples: `python roadmap.py build examples/engineering-mathematics-1.md --hours 3`

## Course file format

Plain Markdown. `#` = course, `##` = module, `-` = topic with estimated hours.

```markdown
# C Programming
## Loops and Arrays
- for, while, do-while loops (3h)
- 1D and 2D arrays (3h)
```

A topic without `(Nh)` counts as 1h. JSON also works:
`{"name": "...", "modules": [{"name": "...", "topics": [{"name": "...", "hours": 2}]}]}`

## Options (`build`)

| Option | Default | Meaning |
|---|---|---|
| `--start` | today | First study day |
| `--exam` | none | Deadline. The plan is fitted before it |
| `--hours` | 2 | Study hours per day |
| `--days` | weekdays | `mon,wed,sat` or `weekdays` / `weekends` / `all` |
| `--time` | 18:00 | Daily start time |
| `--block` | 2 | Max hours in one unbroken session |
| `--revision` | 0.25 | Revision time per module (25% of its study hours) |
| `--out` | out | Output folder |

## How it plans

1. Topics are scheduled in order, packed into your available days.
2. After each module a **revision** slot is added, and a **mock test** at the end.
3. Sessions have a 10-minute break between them.
4. With `--exam`, if the course needs more hours than you have, topics are scaled down and you get a note with the hours/day you would need to keep full depth. If you have extra time, it tells you how many spare days remain.

## Tests

```bash
python -m unittest discover tests -v
```

## Contributing

Add a course outline to `examples/` (one `.md` file) and open a pull request.

## License

MIT
