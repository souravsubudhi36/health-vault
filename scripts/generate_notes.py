"""
generate_notes.py
-----------------
Reads parsed JSON files from health/apple-health/parsed/ and generates
one Obsidian markdown note per day in vault/Health/YYYY-MM-DD.md.

Each note has:
  - YAML frontmatter  (queryable by Dataview)
  - Human-readable sections for Sleep, Heart, Activity, Body
  - 7-day average for HRV as context
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

PARSED_DIR = Path("health/apple-health/parsed")
VAULT_HEALTH_DIR = Path("vault/Health")

# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load(name: str) -> list:
    path = PARSED_DIR / f"{name}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def by_date(records: list, field: str = "value", agg: str = "sum") -> dict:
    """Aggregate records into {date: value} using the chosen aggregation."""
    grouped: dict = defaultdict(list)
    for r in records:
        date = r.get("date")
        val = r.get(field)
        if date and isinstance(val, (int, float)):
            grouped[date].append(val)

    result = {}
    for date, vals in grouped.items():
        if not vals:
            continue
        if agg == "sum":
            result[date] = round(sum(vals), 1)
        elif agg == "avg":
            result[date] = round(sum(vals) / len(vals), 1)
        elif agg == "max":
            result[date] = round(max(vals), 1)
        elif agg == "last":
            result[date] = round(vals[-1], 1)
    return result


def sleep_by_date(records: list) -> dict:
    result = {}
    for r in records:
        date = r.get("date")
        if not date:
            continue
        hours = round(r.get("total_min", 0) / 60, 1)
        stages = r.get("stages", {})
        result[date] = {
            "hours": hours,
            "deep_min": int(stages.get("Deep", 0)),
            "rem_min": int(stages.get("REM", 0)),
            "core_min": int(stages.get("Core", 0)),
            "start": r.get("start", ""),
            "end": r.get("end", ""),
        }
    return result


# ---------------------------------------------------------------------------
# 7-day rolling average helper
# ---------------------------------------------------------------------------

def rolling_avg(daily: dict, date_str: str, days: int = 7) -> str:
    date = datetime.fromisoformat(date_str)
    vals = []
    for i in range(days):
        d = (date - timedelta(days=i)).date().isoformat()
        v = daily.get(d)
        if isinstance(v, (int, float)):
            vals.append(v)
    if not vals:
        return "—"
    return str(round(sum(vals) / len(vals), 1))


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def fmt(val, suffix: str = "", fmt_str: str = "") -> str:
    if val is None or val == "":
        return "—"
    if fmt_str and isinstance(val, (int, float)):
        return f"{val:{fmt_str}}{suffix}"
    return f"{val}{suffix}"


def fmt_steps(val) -> str:
    if isinstance(val, float) and val > 0:
        return f"{int(val):,}"
    if isinstance(val, int) and val > 0:
        return f"{val:,}"
    return "—"


def fmt_time(iso: str) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%I:%M %p")
    except ValueError:
        return "—"


# ---------------------------------------------------------------------------
# Note generator
# ---------------------------------------------------------------------------

def generate_note(
    date_str: str,
    sleep: dict,
    hrv: dict,
    rhr: dict,
    steps: dict,
    weight: dict,
    active_energy: dict,
    blood_oxygen: dict,
    exercise_min: dict,
    respiratory_rate: dict,
    resting_energy: dict,
) -> str:
    date = datetime.fromisoformat(date_str)
    display_date = date.strftime("%B %d, %Y")

    # Sleep
    sl = sleep.get(date_str, {})
    sleep_hours = sl.get("hours", "")
    deep_min = sl.get("deep_min", 0)
    rem_min = sl.get("rem_min", 0)
    core_min = sl.get("core_min", 0)
    sleep_start = fmt_time(sl.get("start", ""))
    sleep_end = fmt_time(sl.get("end", ""))
    sleep_times = f"{sleep_start} → {sleep_end}" if sl else "—"

    # Metrics
    hrv_val = hrv.get(date_str, "")
    hrv_avg = rolling_avg(hrv, date_str)
    rhr_val = rhr.get(date_str, "")
    steps_val = steps.get(date_str, "")
    weight_val = weight.get(date_str, "")
    energy_val = active_energy.get(date_str, "")
    o2_val = blood_oxygen.get(date_str, "")
    exercise_val = exercise_min.get(date_str, "")
    resp_val = respiratory_rate.get(date_str, "")
    rest_energy_val = resting_energy.get(date_str, "")

    # YAML frontmatter — empty string for missing values (Dataview handles null)
    frontmatter_lines = [
        "---",
        f"date: {date_str}",
        f"sleep_hours: {sleep_hours if sleep_hours != '' else 'null'}",
        f"hrv: {hrv_val if hrv_val != '' else 'null'}",
        f"resting_hr: {rhr_val if rhr_val != '' else 'null'}",
        f"steps: {int(steps_val) if isinstance(steps_val, float) else (steps_val if steps_val != '' else 'null')}",
        f"weight: {weight_val if weight_val != '' else 'null'}",
        f"active_energy: {int(energy_val) if isinstance(energy_val, float) else (energy_val if energy_val != '' else 'null')}",
        f"blood_oxygen: {o2_val if o2_val != '' else 'null'}",
        f"exercise_min: {int(exercise_val) if isinstance(exercise_val, float) else (exercise_val if exercise_val != '' else 'null')}",
        f"respiratory_rate: {resp_val if resp_val != '' else 'null'}",
        f"resting_energy: {int(rest_energy_val) if isinstance(rest_energy_val, float) else (rest_energy_val if rest_energy_val != '' else 'null')}",
        "---",
    ]

    body_lines = [
        "",
        f"# Health — {display_date}",
        "",
        "## Sleep",
        f"- **Total:** {fmt(sleep_hours, 'h')}",
        f"- Deep: {deep_min}m | REM: {rem_min}m | Core: {core_min}m",
        f"- {sleep_times}",
        "",
        "## Heart",
        f"- **HRV:** {fmt(hrv_val, ' ms')} _(7-day avg: {hrv_avg} ms)_",
        f"- **Resting HR:** {fmt(rhr_val, ' bpm')}",
        f"- **Respiratory Rate:** {fmt(resp_val, ' brpm')}",
        "",
        "## Activity",
        f"- **Steps:** {fmt_steps(steps_val)}",
        f"- **Active Energy:** {fmt(int(energy_val) if isinstance(energy_val, float) else energy_val, ' kcal')}",
        f"- **Resting Energy:** {fmt(int(rest_energy_val) if isinstance(rest_energy_val, float) else rest_energy_val, ' kcal')}",
        f"- **Exercise:** {fmt(int(exercise_val) if isinstance(exercise_val, float) else exercise_val, ' min')}",
        "",
        "## Body",
        f"- **Weight:** {fmt(weight_val, ' kg')}",
        f"- **Blood Oxygen:** {fmt(o2_val, '%')}",
        "",
    ]

    return "\n".join(frontmatter_lines + body_lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading parsed data…")
    sleep = sleep_by_date(load("sleep_data"))
    hrv = by_date(load("heartratevariabilitysdnn"), agg="avg")
    rhr = by_date(load("restingheartrate"), agg="avg")
    steps = by_date(load("step_count"), agg="sum")
    weight = by_date(load("bodymass"), agg="last")
    active_energy = by_date(load("activeenergyburned"), agg="sum")
    blood_oxygen = by_date(load("oxygensaturation"), agg="avg")
    exercise_min = by_date(load("appleexercisetime"), agg="sum")
    respiratory_rate = by_date(load("respiratoryrate"), agg="avg")
    resting_energy = by_date(load("basalenergyburned"), agg="sum")

    # Collect all dates across all data types
    all_dates = set(
        list(sleep.keys())
        + list(hrv.keys())
        + list(rhr.keys())
        + list(steps.keys())
        + list(weight.keys())
        + list(active_energy.keys())
        + list(blood_oxygen.keys())
        + list(exercise_min.keys())
    )

    if not all_dates:
        print("No data found. Run parse_health.py first.")
        return

    VAULT_HEALTH_DIR.mkdir(parents=True, exist_ok=True)

    for date_str in sorted(all_dates):
        note = generate_note(
            date_str,
            sleep, hrv, rhr, steps, weight,
            active_energy, blood_oxygen, exercise_min,
            respiratory_rate, resting_energy,
        )
        out_path = VAULT_HEALTH_DIR / f"{date_str}.md"
        out_path.write_text(note, encoding="utf-8")

    print(f"Generated {len(all_dates)} notes in {VAULT_HEALTH_DIR}/")


if __name__ == "__main__":
    main()
